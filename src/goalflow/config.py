"""
Configuration management for goalflow workflow.
Supports environment variables and configuration files.
"""

import os
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
import yaml
import json
from pathlib import Path
import structlog
import logging
import sys

from contextvars import  ContextVar

from langchain_core.runnables.config import var_child_runnable_config

request_id: ContextVar[str] = ContextVar(
    "request_id", default=None
)

# Used for telemetry reporting
trace_info: ContextVar[Dict[str, Any]] = ContextVar(
    "trace_info", default={}
)

# trace context information (trace_id and parent_span_id)
# Format: {"trace_id": "xxx", "parent_span_id": "xxx"}
trace_context: ContextVar[Dict[str, Optional[str]]] = ContextVar(
    "trace_context", default={}
)


class LoggingConfig(BaseModel):
    """Logging configuration model."""
    level: str = Field(default="INFO", description="Log level")
    format: str = Field(
        default="%(asctime)s - %(request_id)s - %(levelname)s - %(message)s",
        description="Log format"
    )
    file_path: Optional[str] = Field(default=None, description="Log file path")
    max_file_size: int = Field(default=10485760, description="Max log file size (10MB)")
    backup_count: int = Field(default=5, description="Number of backup files")
    enable_console: bool = Field(default=True, description="Enable console logging")


class ServerConfig(BaseModel):
    """Server configuration model."""
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")
    workers: int = Field(default=1, description="Number of workers")
    reload: bool = Field(default=False, description="Enable auto-reload")
    debug: bool = Field(default=False, description="Enable debug mode")
    cors_origins: list[str] = Field(default=["*"], description="CORS allowed origins")



class Settings(BaseModel):
    """Main settings class using Pydantic BaseSettings."""
    
    # Environment
    environment: str = Field(default="development", description="Environment (development, production)")
    
    # Logging Configuration
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    
    # Server Configuration
    server: ServerConfig = Field(default_factory=ServerConfig)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        env_nested_delimiter = "__"
        case_sensitive = False


class ConfigManager:
    """Configuration manager for loading and managing settings."""
    
    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file
        self._settings: Optional[Settings] = None
        
    def load_settings(self) -> Settings:
        """Load settings from environment variables and config file."""
        if self._settings is not None:
            return self._settings
            
        # Load from config file if provided
        config_data = {}
        if self.config_file and Path(self.config_file).exists():
            config_data = self._load_config_file(self.config_file)
        
        # Create settings with config file data as defaults
        if config_data:
            # Override environment variables with config file data
            for key, value in config_data.items():
                if isinstance(value, dict):
                    for sub_key, sub_value in value.items():
                        env_key = f"{key.upper()}__{sub_key.upper()}"
                        if env_key not in os.environ:
                            os.environ[env_key] = str(sub_value)
                else:
                    env_key = key.upper()
                    if env_key not in os.environ:
                        os.environ[env_key] = str(value)
        
        self._settings = Settings()
        return self._settings
    
    def _load_config_file(self, config_file: str) -> Dict[str, Any]:
        """Load configuration from file (YAML or JSON)."""
        config_path = Path(config_file)
        
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_file}")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            if config_path.suffix.lower() in ['.yml', '.yaml']:
                return yaml.safe_load(f) or {}
            elif config_path.suffix.lower() == '.json':
                return json.load(f)
            else:
                raise ValueError(f"Unsupported configuration file format: {config_path.suffix}")
    
    def get_settings(self) -> Settings:
        """Get current settings."""
        if self._settings is None:
            return self.load_settings()
        return self._settings
    
    def reload_settings(self) -> Settings:
        """Reload settings from sources."""
        self._settings = None
        return self.load_settings()


# Global configuration manager instance
config_manager = ConfigManager()

def get_settings() -> Settings:
    """Get global settings instance."""
    return config_manager.get_settings()

def load_config_from_file(config_file: str) -> Settings:
    """Load configuration from specific file."""
    global config_manager
    config_manager = ConfigManager(config_file)
    return config_manager.load_settings()



from structlog.contextvars import  get_contextvars
def merge_context_vars(logger, method_name, event_dict) :
    # var_child_runnable_config is the contextvars of langgraph,
    # it is used to pass contextvars from langgraph to langchain
    context = var_child_runnable_config.get() or {}

    metadata = context.get("metadata",{})
    context_keys = ["message_id","conversation_id","user_id"]
    
    for key in context_keys:
        if key in metadata:
            event_dict[key] = metadata[key]
    return event_dict


class RequestIdFilter(logging.Filter):
    """Logging filter that retrieves request_id from contextvars and injects it into log records."""
    def filter(self, record):
        _request_id = request_id.get()

        # pregel task was executed in other different context,so use below part
        if not _request_id:
            context = var_child_runnable_config.get() or {}
            metadata = context.get("metadata",{})
            _request_id = metadata.get("request_id","")
            
        record.request_id = _request_id
        return True

from functools import partial

def setup_logging(
    log_level: Optional[str] = None,
    log_file: Optional[str] = None,
    enable_console: Optional[bool] = None
) -> None:
    """
    Setup logging configuration.
    
    Args:
        log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (optional)
        enable_console: Enable console logging
    """
    settings = get_settings()
    logging_config = settings.logging
    
    # Use provided parameters or fall back to config
    level = log_level or logging_config.level
    file_path = log_file or logging_config.file_path
    console_enabled = enable_console if enable_console is not None else logging_config.enable_console
    
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.processors.EventRenamer("msg"),
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            #structlog.stdlib.add_log_level,
            #structlog.contextvars.merge_contextvars,
            merge_context_vars,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso",utc=False),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            #merge_context_vars,
            structlog.processors.JSONRenderer(serializer=partial(json.dumps, ensure_ascii=False))
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Create formatter
    formatter = logging.Formatter(
        fmt=logging_config.format,
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Console handler
    if console_enabled:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, level.upper()))
        console_handler.setFormatter(formatter)
        console_handler.addFilter(RequestIdFilter())
        console_handler.encoding = 'utf-8'
        #console_handler.setEncoding('utf-8')
        root_logger.addHandler(console_handler)
    
    # File handler
    if file_path:
        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.handlers.RotatingFileHandler(
            filename=file_path,
            maxBytes=logging_config.max_file_size,
            backupCount=logging_config.backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(getattr(logging, level.upper()))
        file_handler.setFormatter(formatter)
        file_handler.addFilter(RequestIdFilter())
        root_logger.addHandler(file_handler)
    
    # Set specific logger levels
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("fastapi").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.BoundLogger:
    """
    Get a structured logger instance.
    
    Args:
        name: Logger name (usually __name__)
        
    Returns:
        Structured logger instance
    """
    return structlog.get_logger(name)


class LoggerMixin:
    """Mixin class to add logging capabilities to any class."""
    
    @property
    def logger(self) -> structlog.BoundLogger:
        """Get logger for this class."""
        if not hasattr(self, '_logger'):
            self._logger = get_logger(self.__class__.__name__)
        return self._logger


# Initialize logging on import
setup_logging()



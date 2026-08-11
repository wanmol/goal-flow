"""
Checkpointer connection pool manager (singleton)

All workflows share the same checkpointer connection pool, isolated from the Service-layer connection pool.

Usage:
    from goalflow.infra.checkpointer_manager import CheckpointerManager

    checkpointer = CheckpointerManager.get_checkpointer()
"""

import os
import threading
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver

from goalflow.config import get_logger

logger = get_logger(__name__)


class CheckpointerManager:
    """
    Checkpointer connection pool manager (singleton)

    Features:
    - All workflows share the same checkpointer instance
    - Uses an independent connection pool, isolated from the Service layer
    - Thread-safe singleton pattern
    - Connection pool config optimized for the checkpointer scenario
    """

    _lock = threading.Lock()
    _engine: Optional[Engine] = None
    _checkpointer: Optional[PyMySQLSaver] = None
    _initialized: bool = False

    # Checkpointer-dedicated connection pool config
    POOL_SIZE = 100           # Smaller pool, checkpointer operations are infrequent
    MAX_OVERFLOW = 100        # Allowed extra connections
    POOL_RECYCLE = 600      # Recycle after 5 minutes, reducing the risk of dropped connections
    POOL_TIMEOUT = 30       # Connection acquisition timeout
    POOL_PRE_PING = True    # Check connection validity before checkout
    
    @classmethod
    def get_checkpointer(cls) -> PyMySQLSaver:
        """
        Get the shared checkpointer instance

        Returns:
            PyMySQLSaver: the shared checkpointer instance
        """
        if cls._checkpointer is None:
            with cls._lock:
                if cls._checkpointer is None:
                    cls._init_checkpointer()
        return cls._checkpointer
    
    @classmethod
    def get_engine(cls) -> Engine:
        """
        Get the checkpointer-dedicated database engine

        Returns:
            Engine: the SQLAlchemy Engine instance
        """
        if cls._engine is None:
            with cls._lock:
                if cls._engine is None:
                    cls._init_checkpointer()
        return cls._engine
    
    @classmethod
    def _init_checkpointer(cls):
        """Initialize the checkpointer connection pool"""
        from goalflow.infra.connection_wrapper import SQLAlchemyConnectionWrapper

        # Get database config from environment variables
        mysql_user = os.getenv("MYSQL_USER", "root")
        mysql_password = os.getenv("MYSQL_PASSWORD", "")
        mysql_host = os.getenv("MYSQL_HOST", "localhost")
        mysql_port = os.getenv("MYSQL_PORT", "3306")
        mysql_db = os.getenv("MYSQL_DB", "aira")
        
        pool_size = int(os.getenv("POOL_SIZE", cls.POOL_SIZE))
        max_overflow = int(os.getenv("MAX_OVERFLOW", cls.MAX_OVERFLOW))
        pool_recycle = int(os.getenv("POOL_RECYCLE", cls.POOL_RECYCLE))
        pool_timeout = int(os.getenv("POOL_TIMEOUT", cls.POOL_TIMEOUT))
        
        conn_url = f"mysql+pymysql://{mysql_user}:{mysql_password}@{mysql_host}:{mysql_port}/{mysql_db}"
        
        # Create an independent connection pool
        cls._engine = create_engine(
            conn_url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_recycle=pool_recycle,
            pool_timeout=pool_timeout,
            pool_pre_ping=cls.POOL_PRE_PING,
            # Add connection parameters
            connect_args={
                "connect_timeout": 10,
                "read_timeout": 30,
                "write_timeout": 30,
            }
        )

        # Create the connection wrapper
        conn = SQLAlchemyConnectionWrapper(cls._engine)

        # Create the PyMySQLSaver
        cls._checkpointer = PyMySQLSaver(conn)
        cls._initialized = True
        
        logger.info(
            f"CheckpointerManager initialized with dedicated connection pool "
            f"(pool_size={pool_size}, pool_recycle={pool_recycle}s)"
        )
    
    @classmethod
    def is_initialized(cls) -> bool:
        """Check whether it has been initialized"""
        return cls._initialized

    @classmethod
    def dispose(cls):
        """
        Release resources (typically called on application shutdown)
        """
        with cls._lock:
            if cls._engine is not None:
                try:
                    cls._engine.dispose()
                    logger.info("CheckpointerManager connection pool disposed")
                except Exception as e:
                    logger.warning(f"Error disposing checkpointer engine: {e}")
                finally:
                    cls._engine = None
                    cls._checkpointer = None
                    cls._initialized = False


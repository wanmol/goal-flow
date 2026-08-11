"""
Checkpointer 连接池管理器（单例）

所有 workflow 共享同一个 checkpointer 连接池，与 Service 层连接池隔离。

使用方式：
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
    Checkpointer 连接池管理器（单例）
    
    特性：
    - 所有 workflow 共享同一个 checkpointer 实例
    - 使用独立的连接池，与 Service 层隔离
    - 线程安全的单例模式
    - 连接池配置针对 checkpointer 场景优化
    """
    
    _lock = threading.Lock()
    _engine: Optional[Engine] = None
    _checkpointer: Optional[PyMySQLSaver] = None
    _initialized: bool = False
    
    # Checkpointer 专用连接池配置
    POOL_SIZE = 100           # 较小的池，checkpointer 操作不频繁
    MAX_OVERFLOW = 100        # 允许的额外连接
    POOL_RECYCLE = 600      # 5分钟回收，减少连接断开风险
    POOL_TIMEOUT = 30       # 获取连接超时
    POOL_PRE_PING = True    # 借出前检测连接有效性
    
    @classmethod
    def get_checkpointer(cls) -> PyMySQLSaver:
        """
        获取共享的 checkpointer 实例
        
        Returns:
            PyMySQLSaver: 共享的 checkpointer 实例
        """
        if cls._checkpointer is None:
            with cls._lock:
                if cls._checkpointer is None:
                    cls._init_checkpointer()
        return cls._checkpointer
    
    @classmethod
    def get_engine(cls) -> Engine:
        """
        获取 checkpointer 专用的数据库引擎
        
        Returns:
            Engine: SQLAlchemy Engine 实例
        """
        if cls._engine is None:
            with cls._lock:
                if cls._engine is None:
                    cls._init_checkpointer()
        return cls._engine
    
    @classmethod
    def _init_checkpointer(cls):
        """初始化 checkpointer 连接池"""
        from goalflow.infra.connection_wrapper import SQLAlchemyConnectionWrapper
        
        # 从环境变量获取数据库配置
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
        
        # 创建独立的连接池
        cls._engine = create_engine(
            conn_url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_recycle=pool_recycle,
            pool_timeout=pool_timeout,
            pool_pre_ping=cls.POOL_PRE_PING,
            # 添加连接参数
            connect_args={
                "connect_timeout": 10,
                "read_timeout": 30,
                "write_timeout": 30,
            }
        )
        
        # 创建连接包装器
        conn = SQLAlchemyConnectionWrapper(cls._engine)
        
        # 创建 PyMySQLSaver
        cls._checkpointer = PyMySQLSaver(conn)
        cls._initialized = True
        
        logger.info(
            f"CheckpointerManager initialized with dedicated connection pool "
            f"(pool_size={pool_size}, pool_recycle={pool_recycle}s)"
        )
    
    @classmethod
    def is_initialized(cls) -> bool:
        """检查是否已初始化"""
        return cls._initialized
    
    @classmethod
    def dispose(cls):
        """
        释放资源（通常在应用关闭时调用）
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


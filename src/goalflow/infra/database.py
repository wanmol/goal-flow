import os
from contextlib import contextmanager

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, scoped_session
from goalflow.config import get_logger

logger = get_logger(__name__)

# 环境配置
class Config:
    def __init__(self):
        self.load_config()

    def load_config(self):
        self.MYSQL_HOST = os.getenv("MYSQL_HOST")
        self.MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
        self.MYSQL_USER = os.getenv("MYSQL_USER")
        self.MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
        self.MYSQL_DB = os.getenv("MYSQL_DB")

        # 连接池配置
        self.POOL_SIZE = int(os.getenv("POOL_SIZE", 10))
        self.MAX_OVERFLOW = int(os.getenv("MAX_OVERFLOW", 20))
        self.POOL_RECYCLE = int(os.getenv("POOL_RECYCLE", 3600))
        self.POOL_PRE_PING = os.getenv("POOL_PRE_PING", "True") == "True"
        self.POOL_TIMEOUT = int(os.getenv("POOL_TIMEOUT", 30))

        # 新增Redis配置
        self.REDIS_ENABLED = os.getenv("REDIS_ENABLED", "False") == "True"
        self.REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
        self.REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
        self.REDIS_USERNAME = os.getenv("REDIS_USERNAME", "")
        self.REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
        self.REDIS_DB = int(os.getenv("REDIS_DB", 0))
        self.REDIS_POOL_SIZE = int(os.getenv("REDIS_POOL_SIZE", 500))
        self.REDIS_POOL_TIMEOUT = int(os.getenv("REDIS_POOL_TIMEOUT", 10))
        self.REDIS_SOCKET_TIMEOUT = int(os.getenv("REDIS_SOCKET_TIMEOUT", 10))
        self.REDIS_CONNECT_TIMEOUT = int(os.getenv("REDIS_CONNECT_TIMEOUT", 10))
        self.CACHE_DEFAULT_TIMEOUT = int(os.getenv("CACHE_DEFAULT_TIMEOUT", 300))
        self.REDIS_CLUSTERS = os.getenv("REDIS_CLUSTERS")
        self.REDIS_MODEL = os.getenv("REDIS_MODEL")

        # 业务
        self.MESSAGES_PER_PAGE = int(os.getenv("MESSAGES_PER_PAGE", 25))


# 数据库引擎管理
class Database:
    _engine = None
    _session_factory = None
    _url = None

    @classmethod
    def init(cls):
        config = Config()
        conn_url = f"mysql+pymysql://{config.MYSQL_USER}:{config.MYSQL_PASSWORD}@{config.MYSQL_HOST}:{config.MYSQL_PORT}/{config.MYSQL_DB}"
        cls._url = conn_url
        
        cls._engine = create_engine(
            conn_url,
            pool_size=config.POOL_SIZE,
            max_overflow=config.MAX_OVERFLOW,
            pool_recycle=config.POOL_RECYCLE,
            pool_pre_ping=config.POOL_PRE_PING,
            pool_timeout=config.POOL_TIMEOUT,
        )
        cls._session_factory = sessionmaker(bind=cls._engine)
        
    @classmethod
    def get_url(cls) -> str:
        if not cls._url:
            cls.init()
        return cls._url

    @classmethod
    @contextmanager
    def get_session(cls):
        if not cls._engine:
            cls.init()

        session = scoped_session(cls._session_factory)()
        try:
            yield session
            session.commit()
        except Exception as e:
            logger.error(f"get_session 失败: {e}")
            session.rollback()
            raise
        finally:
            session.close()

    @classmethod
    def close(cls):
        if cls._engine:
            cls._engine.dispose()

    @classmethod
    def health_check(cls) -> bool:
        """
        数据库健康检查

        Returns:
            dict: 健康检查结果
        """
        try:
            if not cls._engine:
                cls.init()

            # 测试数据库连接
            with cls.get_session() as session:
                # 执行简单的查询来测试连接
                result = session.execute(text("SELECT 1 as health_check"))
                row = result.fetchone()

                if row and row[0] == 1:
                    return True
                else:
                    return False

        except Exception as e:
            logger.error(f"health_check失败: {e}")
            return False
    
    @classmethod
    def get_engine(cls):
        """
        获取 SQLAlchemy 引擎（包含连接池）
        
        这个方法提供对底层 SQLAlchemy 引擎的访问，主要用于：
        - LangGraph checkpoint 连接
        - 需要原始连接的场景
        - 连接池监控和管理
        
        Returns:
            Engine: SQLAlchemy 引擎实例（包含连接池配置）
        """
        if cls._engine is None:
            cls.init()
        return cls._engine
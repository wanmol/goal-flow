"""
SQLAlchemy Connection Wrapper for PyMySQLSaver

为 LangGraph PyMySQLSaver 提供兼容接口。
"""


import time
import threading
from goalflow.config import get_logger

logger = get_logger(__name__)

# 重试配置
MAX_RETRIES = 3
RETRY_DELAY = 0.5  # 秒


class SQLAlchemyConnectionWrapper:
    """
    包装 SQLAlchemy 引擎，提供 PyMySQLSaver 兼容的连接接口
    
    特性：
    - 使用独立的连接池（与 Service 层隔离）
    - 线程本地存储，确保线程安全
    - 自动重试机制
    - 失效连接自动丢弃
    
    使用方式：
        engine = create_engine(...)
        conn = SQLAlchemyConnectionWrapper(engine)
        checkpointer = PyMySQLSaver(conn)
    """
    
    def __init__(self, engine):
        """
        初始化连接包装器
        
        Args:
            engine: SQLAlchemy Engine 实例（已配置连接池）
        """
        self.engine = engine
        self._local = threading.local()  # 线程本地存储
        
        try:
            pool_size = engine.pool.size()
            logger.info(
                f"SQLAlchemyConnectionWrapper initialized "
                f"(pool_size={pool_size}, thread-safe mode)"
            )
        except Exception:
            logger.info("SQLAlchemyConnectionWrapper initialized")
    
    def _get_connection(self, retries: int = MAX_RETRIES):
        """
        从连接池获取连接（线程安全，带重试）
        
        Args:
            retries: 重试次数
        
        Returns:
            pymysql.Connection: 底层 PyMySQL 连接对象
        """
        last_error = None
        
        for attempt in range(retries):
            try:
                conn = self.engine.raw_connection()
                
                # 验证连接有效性
                try:
                    conn.ping(reconnect=False)
                except Exception:
                    try:
                        conn.close()
                    except:
                        pass
                    continue
                
                logger.debug(f"Acquired connection (thread: {threading.current_thread().name})")
                return conn
                
            except Exception as e:
                last_error = e
                logger.warning(f"Failed to get connection (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
        
        logger.error(f"Failed to get connection after {retries} attempts")
        raise last_error or Exception("Failed to get database connection")
    
    def cursor(self, *args, **kwargs):
        """获取游标（每次获取新连接，带重试）"""
        last_error = None
        
        for attempt in range(MAX_RETRIES):
            try:
                conn = self._get_connection()
                self._local.conn = conn
                return conn.cursor(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt == 0:
                    logger.debug(f"Connection lost when getting cursor, retrying... ({e})")
                else:
                    logger.warning(f"Failed to get cursor (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                self._close_local_conn(invalidate=True)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
        
        logger.error(f"Failed to get cursor after {MAX_RETRIES} attempts")
        raise last_error or Exception("Failed to get cursor")
    
    def begin(self):
        """开始事务（PyMySQLSaver 需要此方法）"""
        conn = getattr(self._local, 'conn', None)
        if conn is None:
            conn = self._get_connection()
            self._local.conn = conn
        
        for attempt in range(MAX_RETRIES):
            try:
                conn.begin()
                return
            except Exception as e:
                # 只在非首次尝试时记录 WARNING，首次用 DEBUG
                if attempt == 0:
                    logger.debug(f"Connection lost, retrying... ({e})")
                else:
                    logger.warning(f"Failed to begin transaction (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                self._close_local_conn(invalidate=True)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                    conn = self._get_connection()
                    self._local.conn = conn
                else:
                    logger.error(f"Failed to begin transaction after {MAX_RETRIES} attempts")
                    raise
    
    def commit(self):
        """提交事务"""
        conn = getattr(self._local, 'conn', None)
        if conn:
            try:
                conn.commit()
            finally:
                self._close_local_conn()
    
    def rollback(self):
        """回滚事务"""
        conn = getattr(self._local, 'conn', None)
        if conn:
            try:
                conn.rollback()
            except Exception as e:
                logger.warning(f"Rollback failed: {e}")
            finally:
                self._close_local_conn(invalidate=True)
    
    def _close_local_conn(self, invalidate: bool = False):
        """
        关闭线程本地连接
        
        Args:
            invalidate: 如果为 True，标记连接为无效（不归还到池中）
        """
        conn = getattr(self._local, 'conn', None)
        if conn:
            try:
                if invalidate:
                    try:
                        conn.invalidate()
                    except Exception:
                        pass
                else:
                    conn.close()
            except Exception as e:
                logger.debug(f"Error closing connection: {e}")
            finally:
                self._local.conn = None
    
    def __getattr__(self, name):
        """代理其他属性访问到当前连接"""
        conn = getattr(self._local, 'conn', None)
        if conn is None:
            conn = self._get_connection()
            self._local.conn = conn
        return getattr(conn, name)
    
    # mysqlsaver 中没有使用到close，这里保留为了兼容
    def close(self):
        """关闭连接（归还到池）"""
        self._close_local_conn()
    
    def __del__(self):
        """析构函数：确保连接被归还"""
        self._close_local_conn()

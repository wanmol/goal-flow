"""
SQLAlchemy Connection Wrapper for PyMySQLSaver

Provides a compatible interface for LangGraph PyMySQLSaver.
"""


import time
import threading
from goalflow.config import get_logger

logger = get_logger(__name__)

# Retry config
MAX_RETRIES = 3
RETRY_DELAY = 0.5  # seconds


class SQLAlchemyConnectionWrapper:
    """
    Wraps a SQLAlchemy engine to provide a PyMySQLSaver-compatible connection interface

    Features:
    - Uses an independent connection pool (isolated from the Service layer)
    - Thread-local storage to ensure thread safety
    - Automatic retry mechanism
    - Invalid connections are automatically discarded

    Usage:
        engine = create_engine(...)
        conn = SQLAlchemyConnectionWrapper(engine)
        checkpointer = PyMySQLSaver(conn)
    """

    def __init__(self, engine):
        """
        Initialize the connection wrapper

        Args:
            engine: SQLAlchemy Engine instance (connection pool already configured)
        """
        self.engine = engine
        self._local = threading.local()  # Thread-local storage
        
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
        Get a connection from the connection pool (thread-safe, with retry)

        Args:
            retries: number of retries

        Returns:
            pymysql.Connection: the underlying PyMySQL connection object
        """
        last_error = None

        for attempt in range(retries):
            try:
                conn = self.engine.raw_connection()

                # Verify connection validity
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
        """Get a cursor (obtains a new connection each time, with retry)"""
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
        """Begin a transaction (PyMySQLSaver requires this method)"""
        conn = getattr(self._local, 'conn', None)
        if conn is None:
            conn = self._get_connection()
            self._local.conn = conn

        for attempt in range(MAX_RETRIES):
            try:
                conn.begin()
                return
            except Exception as e:
                # Only log WARNING on non-first attempts; use DEBUG for the first
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
        """Commit the transaction"""
        conn = getattr(self._local, 'conn', None)
        if conn:
            try:
                conn.commit()
            finally:
                self._close_local_conn()

    def rollback(self):
        """Roll back the transaction"""
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
        Close the thread-local connection

        Args:
            invalidate: if True, mark the connection as invalid (do not return it to the pool)
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
        """Proxy other attribute access to the current connection"""
        conn = getattr(self._local, 'conn', None)
        if conn is None:
            conn = self._get_connection()
            self._local.conn = conn
        return getattr(conn, name)

    # close is not used in mysqlsaver; kept here for compatibility
    def close(self):
        """Close the connection (return it to the pool)"""
        self._close_local_conn()

    def __del__(self):
        """Destructor: ensure the connection is returned"""
        self._close_local_conn()

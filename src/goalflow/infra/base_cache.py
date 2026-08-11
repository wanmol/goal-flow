from .redis_manager import redis_client
from goalflow.config import get_logger

logger = get_logger(__name__)

class BaseCache:
    """
    Base cache class
    """

    @staticmethod
    def has_key(*, key: str) -> bool:
        """
        Determine whether the cache key exists
        """
        try:
            return redis_client.exists(key)
        except Exception as e:
            logger.error(f"判断缓存键是否存在失败: {e}")
            return False

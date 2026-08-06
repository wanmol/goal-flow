from .redis_manager import redis_client
from goalflow.config import get_logger

logger = get_logger(__name__)

class BaseCache:
    """
    基础缓存类
    """

    @staticmethod
    def has_key(*, key: str) -> bool:
        """
        判断缓存键是否存在
        """
        try:
            return redis_client.exists(key)
        except Exception as e:
            logger.error(f"判断缓存键是否存在失败: {e}")
            return False

import functools
import json
from collections.abc import Callable
from typing import Any, Optional

import redis
from redis import RedisError
from redis.cache import CacheConfig
from redis.cluster import ClusterNode, RedisCluster

from goalflow.config import get_logger
from goalflow.infra.database import Config

# 移除错误的导入，使用本文件定义的redis_fallback

logger = get_logger(__name__)


def redis_fallback(default_return: Any = None):
    """
    Redis操作异常处理装饰器，当Redis不可用时返回默认值

    Args:
        default_return: Redis操作失败时的默认返回值
    """

    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except RedisError as e:
                logger.error(
                    f"Redis集群操作失败 - 函数: {func.__name__}, 错误: {str(e)}"
                )
                return default_return
            except Exception as e:
                # 区分Redis相关错误和其他错误
                if "Redis" in str(e) or "redis" in str(e).lower():
                    logger.error(
                        f"Redis相关错误 - 函数: {func.__name__}, 错误: {str(e)}"
                    )
                else:
                    logger.error(
                        f"Redis集群操作异常 - 函数: {func.__name__}, 错误: {str(e)}"
                    )
                return default_return

        return wrapper

    return decorator


class RedisClusterClientWrapper:
    """
    Redis集群客户端包装器，用于处理集群模式下的Redis连接管理。

    该类提供了延迟初始化功能，允许在需要时重新初始化Redis客户端实例。
    特别适用于Redis集群环境中节点可能动态变化的场景。

    Attributes:
        _client (redis.RedisCluster): 实际的Redis集群客户端实例
    """

    def __init__(self):
        self._client = None

    def initialize(self, client: RedisCluster):
        """初始化Redis集群客户端"""
        if self._client is None:
            self._client = client
            # logger.info("Redis cluster client initialized successfully.")

    def reinitialize(self, client: RedisCluster):
        """重新初始化Redis集群客户端（用于故障转移）"""
        self._client = client
        logger.info("Redis cluster client reinitialized successfully")

    def __getattr__(self, item):
        if self._client is None:
            raise RuntimeError("Redis集群客户端未初始化，请先调用初始化方法")
        return getattr(self._client, item)


class RedisClusterManager:
    """
    FastAPI Redis集群管理器

    提供Redis集群的连接管理、缓存操作和故障处理功能。
    支持Redis 7.0.15集群模式的所有特性。
    """

    _instance = None
    _client_wrapper = None
    _config = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # 确保_client_wrapper只初始化一次
        if (
            not hasattr(self.__class__, "_client_wrapper")
            or self.__class__._client_wrapper is None
        ):
            self.__class__._client_wrapper = RedisClusterClientWrapper()

    @classmethod
    def init_cluster(cls, config: Optional[Config] = None):
        """
        初始化Redis集群连接

        Args:
            config: 配置对象，如果为None则使用默认配置
        """
        if config is None:
            config = Config()

        cls._config = config

        if not hasattr(config, "REDIS_MODEL") or not config.REDIS_MODEL:
            logger.error("Redis集群节点配置未设置")
            return False

        try:
            # 解析集群节点
            cluster_nodes = []
            for node in config.REDIS_CLUSTERS.split(","):
                host, port = node.strip().split(":")
                cluster_nodes.append(ClusterNode(host=host, port=int(port)))

            # Redis连接参数
            redis_params = {
                "startup_nodes": cluster_nodes,
                "password": getattr(config, "REDIS_PASSWORD", None),
                "username": getattr(config, "REDIS_USERNAME", None),
                "decode_responses": True,
                "encoding": "utf-8",
                "encoding_errors": "strict",
                "skip_full_coverage_check": True,  # 跳过完整覆盖检查
                "max_connections_per_node": getattr(
                    config, "REDIS_MAX_CONNECTIONS_PER_NODE", 20
                ),
                "socket_timeout": getattr(config, "REDIS_SOCKET_TIMEOUT", 5.0),
                "socket_connect_timeout": getattr(config, "REDIS_CONNECT_TIMEOUT", 5.0),
                "retry_on_timeout": True,
                "retry_on_error": [ConnectionError, TimeoutError],
            }

            # 如果支持SSL连接
            if getattr(config, "REDIS_USE_SSL", False):
                redis_params["ssl"] = True
                redis_params["ssl_cert_reqs"] = None

            # 如果支持客户端缓存（Redis 7.0+特性）
            if getattr(config, "REDIS_ENABLE_CLIENT_SIDE_CACHE", False):
                redis_params["cache_config"] = CacheConfig()

            # 创建Redis集群客户端
            cluster_client = RedisCluster(**redis_params)

            # 测试连接
            cluster_client.ping()

            # 确保包装器已初始化
            if cls._client_wrapper is None:
                cls._client_wrapper = RedisClusterClientWrapper()

            # 初始化包装器
            cls._client_wrapper.initialize(cluster_client)

            # logger.info(f"Redis cluster connected successfully, number of nodes: {len(cluster_nodes)}")
            return True

        except Exception as e:
            logger.error(f"Redis集群连接失败: {str(e)}")
            return False

    @classmethod
    def get_client(cls) -> Optional[RedisCluster]:
        """获取Redis集群客户端"""
        if cls._client_wrapper is None:
            logger.error("Redis集群客户端未初始化")
            return None

        try:
            return cls._client_wrapper
        except RuntimeError as e:
            logger.error(f"获取Redis集群客户端失败: {str(e)}")
            return None

    @classmethod
    def is_enabled(cls) -> bool:
        """检查Redis集群是否启用并可用"""
        try:
            client = cls.get_client()
            if client is None:
                return False
            client.ping()
            return True
        except Exception as e:
            logger.error(f"Redis集群健康检查失败: {str(e)}")
            return False

    @classmethod
    def get_cluster_info(cls) -> dict:
        """获取集群信息"""
        try:
            client = cls.get_client()
            if client is None:
                return {}
            return client.cluster_info()
        except Exception as e:
            logger.error(f"获取集群信息失败: {str(e)}")
            return {}

    @classmethod
    def get_cluster_nodes(cls) -> dict:
        """获取集群节点信息"""
        try:
            client = cls.get_client()
            if client is None:
                return {}
            return client.cluster_nodes()
        except Exception as e:
            logger.error(f"获取集群节点信息失败: {str(e)}")
            return {}

    @classmethod
    def close(cls):
        """关闭Redis集群连接"""
        try:
            if cls._client_wrapper and cls._client_wrapper._client:
                cls._client_wrapper._client.close()
                cls._client_wrapper._client = None
                logger.info("Redis集群连接已关闭")
        except Exception as e:
            logger.error(f"关闭Redis集群连接失败: {str(e)}")

    @staticmethod
    @redis_fallback(default_return=False)
    def set(key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        设置缓存值

        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒），None表示使用默认超时

        Returns:
            bool: 设置成功返回True，失败返回False
        """
        client = RedisClusterManager.get_client()
        if client is None:
            return False

        # 序列化值
        if isinstance(value, (dict, list, tuple)):
            # serialized_value = json.dumps(value, ensure_ascii=False)
            serialized_value = str(value)
        elif isinstance(value, (int, float, bool)):
            serialized_value = str(value)
        else:
            serialized_value = str(value)

        # 设置过期时间
        if ttl is not None:
            return client.setex(key, ttl, serialized_value)
        else:
            default_ttl = getattr(
                RedisClusterManager._config, "CACHE_DEFAULT_TIMEOUT", 3600
            )
            return client.setex(key, default_ttl, serialized_value)

    @staticmethod
    @redis_fallback(default_return=None)
    def get(key: str) -> Any:
        """
        获取缓存值

        Args:
            key: 缓存键

        Returns:
            Any: 缓存值，不存在或失败返回None
        """
        client = RedisClusterManager.get_client()
        if client is None:
            return None

        value = client.get(key)
        if value is None:
            return None

        # 尝试JSON反序列化
        # try:
        #     return json.loads(value)
        # except (json.JSONDecodeError, TypeError):
        return value

    @staticmethod
    @redis_fallback(default_return=False)
    def delete(key: str) -> bool:
        """
        删除缓存值

        Args:
            key: 缓存键

        Returns:
            bool: 删除成功返回True，失败返回False
        """
        client = RedisClusterManager.get_client()
        if client is None:
            return False

        result = client.delete(key)
        return result > 0

    @staticmethod
    @redis_fallback(default_return=False)
    def exists(key: str) -> bool:
        """
        检查键是否存在

        Args:
            key: 缓存键

        Returns:
            bool: 存在返回True，不存在或失败返回False
        """
        client = RedisClusterManager.get_client()
        if client is None:
            return False

        return client.exists(key) > 0

    @staticmethod
    @redis_fallback(default_return=-2)
    def ttl(key: str) -> int:
        """
        获取键的剩余过期时间

        Args:
            key: 缓存键

        Returns:
            int: 剩余过期时间（秒），-1表示永不过期，-2表示键不存在
        """
        client = RedisClusterManager.get_client()
        if client is None:
            return -2

        return client.ttl(key)

    @staticmethod
    @redis_fallback(default_return=False)
    def expire(key: str, seconds: int) -> bool:
        """
        设置键的过期时间

        Args:
            key: 缓存键
            seconds: 过期时间（秒）

        Returns:
            bool: 设置成功返回True，失败返回False
        """
        client = RedisClusterManager.get_client()
        if client is None:
            return False

        return client.expire(key, seconds)

    @staticmethod
    @redis_fallback(default_return={})
    def mget(keys: list) -> dict:
        """
        批量获取多个键的值

        Args:
            keys: 键列表

        Returns:
            dict: 键值对字典
        """
        client = RedisClusterManager.get_client()
        if client is None or not keys:
            return {}

        # Redis集群模式下，mget可能需要特殊处理
        result = {}
        for key in keys:
            try:
                value = client.get(key)
                if value is not None:
                    try:
                        result[key] = json.loads(value)
                    except (json.JSONDecodeError, TypeError):
                        result[key] = value
            except Exception:
                continue  # 跳过失败的键

        return result

    @staticmethod
    @redis_fallback(default_return=False)
    def mset(mapping: dict, ttl: Optional[int] = None) -> bool:
        """
        批量设置多个键值对

        Args:
            mapping: 键值对字典
            ttl: 过期时间（秒）

        Returns:
            bool: 设置成功返回True
        """
        client = RedisClusterManager.get_client()
        if client is None or not mapping:
            return False

        # 序列化所有值
        serialized_mapping = {}
        for key, value in mapping.items():
            if isinstance(value, (dict, list, tuple)):
                serialized_mapping[key] = json.dumps(value, ensure_ascii=False)
            elif isinstance(value, (int, float, bool)):
                serialized_mapping[key] = str(value)
            else:
                serialized_mapping[key] = str(value)

        # 批量设置
        success = client.mset(serialized_mapping)

        # 如果需要设置过期时间
        if success and ttl is not None:
            for key in mapping.keys():
                try:
                    client.expire(key, ttl)
                except Exception:
                    continue  # 忽略过期时间设置失败

        return success

    @classmethod
    def pipeline(cls, transaction: bool = True):
        """
        获取Redis管道对象

        Args:
            transaction: 是否启用事务模式

        Returns:
            Redis管道对象，如果客户端未初始化则返回None
        """
        client = cls.get_client()
        if client is None:
            return None
        return client.pipeline(transaction=transaction)

    @classmethod
    def lrange(cls, key: str, start: int, end: int) -> list:
        """
        获取列表的指定范围的值
        """
        client = cls.get_client()
        if client is None:
            return []
        return client.lrange(key, start, end)


# 全局Redis集群管理器实例
redis_client = RedisClusterManager()

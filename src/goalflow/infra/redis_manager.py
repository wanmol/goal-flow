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

# Removed the incorrect import; use the redis_fallback defined in this file

logger = get_logger(__name__)


def redis_fallback(default_return: Any = None):
    """
    Redis operation exception-handling decorator; returns a default value when Redis is unavailable

    Args:
        default_return: the default return value when the Redis operation fails
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
                # Distinguish Redis-related errors from other errors
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
    Redis cluster client wrapper, used to handle Redis connection management in cluster mode.

    This class provides lazy initialization, allowing the Redis client instance to be reinitialized when needed.
    Especially suitable for scenarios where nodes may change dynamically in a Redis cluster environment.

    Attributes:
        _client (redis.RedisCluster): the actual Redis cluster client instance
    """

    def __init__(self):
        self._client = None

    def initialize(self, client: RedisCluster):
        """Initialize the Redis cluster client"""
        if self._client is None:
            self._client = client
            # logger.info("Redis cluster client initialized successfully.")

    def reinitialize(self, client: RedisCluster):
        """Reinitialize the Redis cluster client (used for failover)"""
        self._client = client
        logger.info("Redis cluster client reinitialized successfully")

    def __getattr__(self, item):
        if self._client is None:
            raise RuntimeError("Redis集群客户端未初始化，请先调用初始化方法")
        return getattr(self._client, item)


class RedisClusterManager:
    """
    FastAPI Redis cluster manager

    Provides connection management, cache operations, and fault handling for Redis clusters.
    Supports all features of Redis 7.0.15 cluster mode.
    """

    _instance = None
    _client_wrapper = None
    _config = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # Ensure _client_wrapper is initialized only once
        if (
            not hasattr(self.__class__, "_client_wrapper")
            or self.__class__._client_wrapper is None
        ):
            self.__class__._client_wrapper = RedisClusterClientWrapper()

    @classmethod
    def init_cluster(cls, config: Optional[Config] = None):
        """
        Initialize the Redis cluster connection

        Args:
            config: config object; if None, the default config is used
        """
        if config is None:
            config = Config()

        cls._config = config

        if not hasattr(config, "REDIS_MODEL") or not config.REDIS_MODEL:
            logger.error("Redis集群节点配置未设置")
            return False

        try:
            # Parse cluster nodes
            cluster_nodes = []
            for node in config.REDIS_CLUSTERS.split(","):
                host, port = node.strip().split(":")
                cluster_nodes.append(ClusterNode(host=host, port=int(port)))

            # Redis connection parameters
            redis_params = {
                "startup_nodes": cluster_nodes,
                "password": getattr(config, "REDIS_PASSWORD", None),
                "username": getattr(config, "REDIS_USERNAME", None),
                "decode_responses": True,
                "encoding": "utf-8",
                "encoding_errors": "strict",
                "skip_full_coverage_check": True,  # Skip full coverage check
                "max_connections_per_node": getattr(
                    config, "REDIS_MAX_CONNECTIONS_PER_NODE", 20
                ),
                "socket_timeout": getattr(config, "REDIS_SOCKET_TIMEOUT", 5.0),
                "socket_connect_timeout": getattr(config, "REDIS_CONNECT_TIMEOUT", 5.0),
                "retry_on_timeout": True,
                "retry_on_error": [ConnectionError, TimeoutError],
            }

            # If SSL connections are supported
            if getattr(config, "REDIS_USE_SSL", False):
                redis_params["ssl"] = True
                redis_params["ssl_cert_reqs"] = None

            # If client-side caching is supported (Redis 7.0+ feature)
            if getattr(config, "REDIS_ENABLE_CLIENT_SIDE_CACHE", False):
                redis_params["cache_config"] = CacheConfig()

            # Create the Redis cluster client
            cluster_client = RedisCluster(**redis_params)

            # Test the connection
            cluster_client.ping()

            # Ensure the wrapper is initialized
            if cls._client_wrapper is None:
                cls._client_wrapper = RedisClusterClientWrapper()

            # Initialize the wrapper
            cls._client_wrapper.initialize(cluster_client)

            # logger.info(f"Redis cluster connected successfully, number of nodes: {len(cluster_nodes)}")
            return True

        except Exception as e:
            logger.error(f"Redis集群连接失败: {str(e)}")
            return False

    @classmethod
    def get_client(cls) -> Optional[RedisCluster]:
        """Get the Redis cluster client"""
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
        """Check whether the Redis cluster is enabled and available"""
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
        """Get cluster information"""
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
        """Get cluster node information"""
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
        """Close the Redis cluster connection"""
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
        Set a cache value

        Args:
            key: cache key
            value: cache value
            ttl: expiration time (seconds); None means use the default timeout

        Returns:
            bool: True if set successfully, False on failure
        """
        client = RedisClusterManager.get_client()
        if client is None:
            return False

        # Serialize the value
        if isinstance(value, (dict, list, tuple)):
            # serialized_value = json.dumps(value, ensure_ascii=False)
            serialized_value = str(value)
        elif isinstance(value, (int, float, bool)):
            serialized_value = str(value)
        else:
            serialized_value = str(value)

        # Set the expiration time
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
        Get a cache value

        Args:
            key: cache key

        Returns:
            Any: the cache value; returns None if it does not exist or on failure
        """
        client = RedisClusterManager.get_client()
        if client is None:
            return None

        value = client.get(key)
        if value is None:
            return None

        # Try JSON deserialization
        # try:
        #     return json.loads(value)
        # except (json.JSONDecodeError, TypeError):
        return value

    @staticmethod
    @redis_fallback(default_return=False)
    def delete(key: str) -> bool:
        """
        Delete a cache value

        Args:
            key: cache key

        Returns:
            bool: True if deleted successfully, False on failure
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
        Check whether a key exists

        Args:
            key: cache key

        Returns:
            bool: True if it exists, False if it does not exist or on failure
        """
        client = RedisClusterManager.get_client()
        if client is None:
            return False

        return client.exists(key) > 0

    @staticmethod
    @redis_fallback(default_return=-2)
    def ttl(key: str) -> int:
        """
        Get the remaining expiration time of a key

        Args:
            key: cache key

        Returns:
            int: remaining expiration time (seconds); -1 means never expires, -2 means the key does not exist
        """
        client = RedisClusterManager.get_client()
        if client is None:
            return -2

        return client.ttl(key)

    @staticmethod
    @redis_fallback(default_return=False)
    def expire(key: str, seconds: int) -> bool:
        """
        Set the expiration time of a key

        Args:
            key: cache key
            seconds: expiration time (seconds)

        Returns:
            bool: True if set successfully, False on failure
        """
        client = RedisClusterManager.get_client()
        if client is None:
            return False

        return client.expire(key, seconds)

    @staticmethod
    @redis_fallback(default_return={})
    def mget(keys: list) -> dict:
        """
        Get the values of multiple keys in batch

        Args:
            keys: list of keys

        Returns:
            dict: dictionary of key-value pairs
        """
        client = RedisClusterManager.get_client()
        if client is None or not keys:
            return {}

        # In Redis cluster mode, mget may need special handling
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
                continue  # Skip failed keys

        return result

    @staticmethod
    @redis_fallback(default_return=False)
    def mset(mapping: dict, ttl: Optional[int] = None) -> bool:
        """
        Set multiple key-value pairs in batch

        Args:
            mapping: dictionary of key-value pairs
            ttl: expiration time (seconds)

        Returns:
            bool: True if set successfully
        """
        client = RedisClusterManager.get_client()
        if client is None or not mapping:
            return False

        # Serialize all values
        serialized_mapping = {}
        for key, value in mapping.items():
            if isinstance(value, (dict, list, tuple)):
                serialized_mapping[key] = json.dumps(value, ensure_ascii=False)
            elif isinstance(value, (int, float, bool)):
                serialized_mapping[key] = str(value)
            else:
                serialized_mapping[key] = str(value)

        # Set in batch
        success = client.mset(serialized_mapping)

        # If the expiration time needs to be set
        if success and ttl is not None:
            for key in mapping.keys():
                try:
                    client.expire(key, ttl)
                except Exception:
                    continue  # Ignore failures to set the expiration time

        return success

    @classmethod
    def pipeline(cls, transaction: bool = True):
        """
        Get a Redis pipeline object

        Args:
            transaction: whether to enable transaction mode

        Returns:
            Redis pipeline object; returns None if the client is not initialized
        """
        client = cls.get_client()
        if client is None:
            return None
        return client.pipeline(transaction=transaction)

    @classmethod
    def lrange(cls, key: str, start: int, end: int) -> list:
        """
        Get values in the specified range of a list
        """
        client = cls.get_client()
        if client is None:
            return []
        return client.lrange(key, start, end)


# Global Redis cluster manager instance
redis_client = RedisClusterManager()

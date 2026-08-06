from goalflow.constants import (
    CHAT_COMPLETION_REQUEST_REDIS_KEY_FMT,
)
from goalflow.cache import RedisClusterManager
from goalflow.state import BaseState
import json
from goalflow.api.base_types import ChatCompletionRequest, ChatCompletionRequestMessagePart
from goalflow.config import (
    get_logger,
)

logger = get_logger(__name__)

class ChatCompletionRequestCache:
    """缓 completion请求缓存"""
    
    @staticmethod
    def cache_chat_completion_request(
        *,
        state: BaseState, 
        request: ChatCompletionRequest):
        """缓存chat completion请求"""
        redis_key = CHAT_COMPLETION_REQUEST_REDIS_KEY_FMT.format(state.get("sys_workflow_run_id"))
        # json_str = json.dumps(request.model_dump(), ensure_ascii=False)
        json_str = request.model_dump_json()
        
        success: bool = RedisClusterManager.set(redis_key, json_str, 60 * 5)
        if not success:
            logger.warning(f"set chat completion request cache failed, redis_key: {redis_key}")
        
    @staticmethod
    def get_chat_completion_request(
        *,
        state: BaseState) -> ChatCompletionRequest:
        """获取chat completion请求"""
        redis_key = CHAT_COMPLETION_REQUEST_REDIS_KEY_FMT.format(state.get("sys_workflow_run_id"))
        json_str = RedisClusterManager.get(redis_key)
        if json_str is None:
            return None
        
        return ChatCompletionRequest.model_validate_json(json_str)

    @staticmethod
    def delete_request_cache(
        *,
        state: BaseState):
        """删除chat completion请求"""
        sys_openai_param :bool = state.get("sys_openai_param", False)
        if not sys_openai_param:
            return
        
        redis_key = CHAT_COMPLETION_REQUEST_REDIS_KEY_FMT.format(state.get("sys_workflow_run_id"))
        success: bool = RedisClusterManager.delete(redis_key)
        if not success:
            logger.warning(f"delete chat completion request cache failed, redis_key: {redis_key}")
        
    @staticmethod
    def perpetuate_request_cache(
        *,
        state: BaseState):
        """持久化chat completion请求"""
        redis_key = CHAT_COMPLETION_REQUEST_REDIS_KEY_FMT.format(state.get("sys_workflow_run_id"))
        success: bool = RedisClusterManager.expire(redis_key, 60 * 5)
        if not success:
            logger.warning(f"expire chat completion request cache failed, redis_key: {redis_key}")
 

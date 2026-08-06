from langchain_core.messages import AIMessageChunk 
from langgraph.config import get_stream_writer
import json
import re

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from goalflow.workflow.stream.types import (
    LANGGRAPH_STREAM_MODE_UPDATES,
    LANGGRAPH_STREAM_MODE_MESSAGES,
    WF_NODE_CONTROL_EVENT_NAME,
    CUSTOM_STREAM_MODE_PASSTHROUGH
)

from goalflow.config import get_logger

logger = get_logger(__name__)

def metaso_message_callback(data,*,node_id):
    """
    处理密塔搜索的消息回调
    """
    stream_writer = get_stream_writer()
    if data.startswith('{') and data.endswith('}'):
            json_data = json.loads(data)
            if 'choices' in json_data:
                metadata = {'langgraph_node': node_id}
                choice = json_data['choices'][0]
                
                if 'delta' in choice:
                    delta = choice['delta']
                    if 'content' in delta:
                        content = delta['content']
                        chunk = AIMessageChunk(content=content)
                        stream_writer((LANGGRAPH_STREAM_MODE_MESSAGES, (chunk, metadata)))
                            
                        return content
                    elif 'reasoning_content' in delta:
                        reasoning_content = delta['reasoning_content']
                        chunk = AIMessageChunk(content="",additional_kwargs={'reasoning_content': reasoning_content})
                        stream_writer((LANGGRAPH_STREAM_MODE_MESSAGES, (chunk, metadata)))
                            
                        return reasoning_content
                    elif 'highlights' in delta or 'citations' in delta:
                        #highlights = delta['highlights']
                        stream_writer((LANGGRAPH_STREAM_MODE_UPDATES, {WF_NODE_CONTROL_EVENT_NAME:delta}))
                    
                    if choice.get('finish_reason','') == 'stop':
                        usage = json_data['usage']
                        token_usage = {"input_tokens": usage['prompt_tokens'], "output_tokens": usage['completion_tokens'], "total_tokens": usage['total_tokens']}
                        chunk = AIMessageChunk(content="",response_metadata={'finish_reason': "stop", 'token_usage': token_usage})
                        stream_writer((LANGGRAPH_STREAM_MODE_MESSAGES, (chunk, metadata)))
                            
            else:
                logger.error(f"未知响应格式: {json_data}")
    else:
        logger.info(f"metaso数据: {data}")
        

def internal_forward(data, *, node_id):
    """
    内部代理转发
    """
    stream_writer = get_stream_writer()
    stream_writer((CUSTOM_STREAM_MODE_PASSTHROUGH, data))
    
    return data


message_cb_list = {
    "https://metaso.cn/api/v1/chat/completions": metaso_message_callback,

}

# 正则表达式映射列表（支持更灵活的URL匹配）
message_cb_regex_list = [
    # 匹配metaso API的所有变体
    (re.compile(r"https?://metaso\.cn/api/v1/chat/completions.*"), metaso_message_callback),
    
    # 匹配内部服务API，支持不同端口（服务名）
    (re.compile(r"https?://aira-workflow-a2a:\d+/a2a/v1/tasks.*"), internal_forward),

    (re.compile(r"https?://10.3.18.217:\d+/a2a/v1/tasks.*"), internal_forward),

    # 可以添加更多正则表达式匹配规则
    # (re.compile(r"https?://example\.com/api/v1/.*"), example_callback),
]

def get_callback_by_url(url):
    """
    根据URL获取对应的回调函数，支持精确匹配和正则表达式匹配
    
    Args:
        url: 请求的URL
        
    Returns:
        对应的回调函数，如果没有匹配则返回None
    """
    # 优先尝试精确匹配
    if url in message_cb_list:
        logger.info(f"URL精确匹配: {url}")
        return message_cb_list[url]
    
    # 然后尝试正则表达式匹配
    for pattern, callback in message_cb_regex_list:
        if pattern.match(url):
            logger.info(f"URL正则匹配: {url} (模式: {pattern.pattern})")
            return callback
    
    logger.warning(f"没有找到URL对应的回调函数: {url}")
    
    # internal_forward 作为默认回调返回（内部转发）
    return internal_forward

# 示例使用
if __name__ == "__main__":
    test_urls = [
        "https://metaso.cn/api/v1/chat/completions",
        "https://metaso.cn/api/v1/chat/completions?param=123",
        "http://aira-workflow-a2a:8006/a2a/v1/tasks",
        "https://aira-workflow-a2a:8007/a2a/v1/tasks/subtask/123",
        "http://unknown.example.com/api/v1/test"
    ]
    
    for url in test_urls:
        callback = get_callback_by_url(url)
        print(f"URL: {url} -> 回调函数: {callback.__name__ if callback else 'None'}")





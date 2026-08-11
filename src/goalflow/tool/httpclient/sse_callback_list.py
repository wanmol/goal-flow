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
    Handle message callbacks from Metaso search
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
    Internal proxy forwarding
    """
    stream_writer = get_stream_writer()
    stream_writer((CUSTOM_STREAM_MODE_PASSTHROUGH, data))
    
    return data


message_cb_list = {
    "https://metaso.cn/api/v1/chat/completions": metaso_message_callback,

}

# Regex mapping list (supports more flexible URL matching)
message_cb_regex_list = [
    # Match all variants of the metaso API
    (re.compile(r"https?://metaso\.cn/api/v1/chat/completions.*"), metaso_message_callback),

    # Match internal service APIs, supporting different ports (service names)
    (re.compile(r"https?://aira-workflow-a2a:\d+/a2a/v1/tasks.*"), internal_forward),

    (re.compile(r"https?://10.3.18.217:\d+/a2a/v1/tasks.*"), internal_forward),

    # More regex matching rules can be added here
    # (re.compile(r"https?://example\.com/api/v1/.*"), example_callback),
]

def get_callback_by_url(url):
    """
    Get the corresponding callback function by URL, supporting exact matching and regex matching

    Args:
        url: The requested URL

    Returns:
        The corresponding callback function, or None if no match is found
    """
    # Try exact match first
    if url in message_cb_list:
        logger.info(f"URL精确匹配: {url}")
        return message_cb_list[url]

    # Then try regex matching
    for pattern, callback in message_cb_regex_list:
        if pattern.match(url):
            logger.info(f"URL正则匹配: {url} (模式: {pattern.pattern})")
            return callback

    logger.warning(f"没有找到URL对应的回调函数: {url}")

    # internal_forward is returned as the default callback (internal forwarding)
    return internal_forward

# Example usage
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





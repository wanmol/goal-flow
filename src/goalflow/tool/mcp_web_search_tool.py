"""
MCP Web Search Tool - 基于 MCP 协议的联网搜索工具

使用 JSON-RPC over HTTP 协议连接远程 MCP 服务

这是一个公共工具，可以被任何节点或 Agent 使用
"""

import asyncio
import json
import threading
from typing import List, Dict, Any, Optional
import httpx
from goalflow.config import get_logger

logger = get_logger(__name__)


class MCPWebSearchTool:
    """MCP 联网搜索工具（远程 HTTP 模式）"""
    
    def __init__(
        self,
        remote_url: str,
        api_key: Optional[str] = None,
        timeout: int = 120,
        max_results: int = 10,
        debug: bool = False,
        tool_name: Optional[str] = None
    ):
        """
        初始化 MCP 搜索工具
        
        Args:
            remote_url: 远程 MCP 服务的 URL（例如：http://localhost:9001）
            api_key: 远程服务的 API Key（必需，用于 Bearer Token 认证）
            timeout: 请求超时时间（秒）
            max_results: 最大返回结果数
            debug: 是否启用调试模式
            tool_name: 要使用的工具名称（如果不指定，使用第一个可用工具）
        """
        if not remote_url:
            raise ValueError("remote_url is required")
        
        if not api_key:
            raise ValueError("api_key is required for Bearer Token authentication")
        
        self.remote_url = remote_url.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout
        self.max_results = max_results
        self.debug = debug
        self.tool_name = tool_name
        
        self._lock = threading.Lock()
        self._msg_id = 0
        
        logger.info(f"Initialized MCP HTTP client: url={remote_url}, timeout={timeout}s, auth=Bearer")
    
    def _get_next_msg_id(self) -> int:
        """获取下一个消息 ID"""
        self._msg_id += 1
        return self._msg_id
    
    async def _http_jsonrpc_request(self, method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        通过 HTTP 发送 JSON-RPC 请求
        
        Args:
            method: MCP 方法名（如 "tools/list", "tools/call"）
            params: 方法参数
            
        Returns:
            JSON-RPC 响应
        """
        msg_id = self._get_next_msg_id()
        
        request_data = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": method,
            "params": params or {}
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"  # 始终添加 Bearer Token
        }
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                url = f"{self.remote_url}/mcp/jsonrpc"
                
                if self.debug:
                    logger.debug(f"Sending JSON-RPC request to {url}: method={method}, params={params}")
                
                response = await client.post(url, json=request_data, headers=headers)
                response.raise_for_status()
                
                response_data = response.json()
                
                if "error" in response_data:
                    error = response_data["error"]
                    raise Exception(f"JSON-RPC Error [{error.get('code')}]: {error.get('message', 'Unknown error')}")
                
                return response_data
                
            except httpx.TimeoutException:
                raise Exception(f"Request timeout after {self.timeout}s")
            except httpx.HTTPStatusError as e:
                raise Exception(f"HTTP {e.response.status_code}: {e.response.text}")
            except httpx.HTTPError as e:
                raise Exception(f"HTTP error: {e}")
            except Exception as e:
                logger.error(f"Error in HTTP JSON-RPC request: {e}", exc_info=True)
                raise
    
    async def _async_list_tools(self) -> List[Dict[str, Any]]:
        """异步获取 MCP Server 中所有可用的工具"""
        try:
            with self._lock:
                response = await self._http_jsonrpc_request("tools/list")
                
                if "result" in response and "tools" in response["result"]:
                    tools = response["result"]["tools"]
                    tool_names = [t['name'] for t in tools]
                    logger.info(f"Found {len(tools)} MCP tools: {tool_names}")
                    return tools
                else:
                    logger.warning("No tools found in response")
                    return []
        
        except Exception as e:
            logger.error(f"Failed to list MCP tools: {e}", exc_info=True)
            return []
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """获取 MCP Server 中所有可用的工具"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                tools = loop.run_until_complete(self._async_list_tools())
                return tools
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Failed to list MCP tools: {e}", exc_info=True)
            return []
    
    async def _async_call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """异步调用指定的 MCP 工具"""
        try:
            with self._lock:
                response = await self._http_jsonrpc_request(
                    "tools/call",
                    params={"name": tool_name, "arguments": arguments}
                )
                
                # 模拟 MCP 客户端的返回格式
                class Result:
                    def __init__(self, content):
                        self.content = content
                
                class ContentItem:
                    def __init__(self, text):
                        self.text = text
                
                content_items = []
                if "result" in response and "content" in response["result"]:
                    for item in response["result"]["content"]:
                        if item.get("type") == "text":
                            content_items.append(ContentItem(item["text"]))
                
                return Result(content_items)
        
        except Exception as e:
            logger.error(f"Failed to call MCP tool {tool_name}: {e}", exc_info=True)
            raise
    
    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """调用指定的 MCP 工具"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    self._async_call_tool(tool_name, arguments)
                )
                return result
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Failed to call MCP tool {tool_name}: {e}", exc_info=True)
            return None
    
    def search(self, query: str, tool_name: Optional[str] = None, count: int = 10) -> str:
        """
        执行搜索并返回标准格式的 JSON 字符串
        
        Args:
            query: 搜索查询
            tool_name: 工具名称（如果不指定，使用 self.tool_name 或第一个可用工具）
            count: 返回结果数量
            
        Returns:
            JSON 字符串，格式：
            {
                "data_type": "web_search",
                "success": true,
                "data": [...],
                "metadata": {...}
            }
        """
        def _sanitize_text_for_json(text: str, max_length: int = 500) -> str:
            """清理文本，移除控制字符和限制长度"""
            if not text:
                return ""
            import re
            text = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', str(text))
            if len(text) > max_length:
                return text[:max_length] + "..."
            return text
        
        # 确定使用哪个工具
        tool_name = tool_name or self.tool_name
        
        # 如果没有指定工具，获取第一个可用工具
        if not tool_name:
            tools = self.list_tools()
            if not tools:
                logger.error("No tools available from MCP server")
                return json.dumps({
                    "data_type": "web_search",
                    "success": False,
                    "data": [],
                    "error": "No tools available from MCP server"
                }, ensure_ascii=False)
            tool_name = tools[0]['name']
            logger.info(f"No tool specified, using first available: {tool_name}")
        
        # 构建参数
        arguments = {"query": query, "num": count}
        
        logger.info(f"Using MCP tool: {tool_name} with query: {query[:50]}...")
        
        # 调用工具
        result = self.call_tool(tool_name, arguments)
        
        if not result or not hasattr(result, 'content'):
            return json.dumps({
                "data_type": "web_search",
                "success": False,
                "data": [],
                "error": "No results from MCP server"
            }, ensure_ascii=False)
        
        # 解析并标准化结果
        data = []
        for content_item in result.content:
            if hasattr(content_item, "text"):
                try:
                    # 尝试解析 JSON
                    parsed_content = json.loads(content_item.text)
                    
                    # 处理 MCP 返回的不同格式
                    if isinstance(parsed_content, dict) and "results" in parsed_content:
                        # 格式 1: {"results": [...]}
                        results = parsed_content["results"]
                    elif isinstance(parsed_content, list):
                        # 格式 2: [...]
                        results = parsed_content
                    else:
                        # 格式 3: {...}
                        results = [parsed_content]
                    
                    # 标准化每个结果的格式
                    for item in results:
                        if isinstance(item, dict):
                            raw_title = item.get("title", "")
                            raw_snippet = item.get("snippet", item.get("summary", item.get("content", "")))
                            
                            data.append({
                                "title": _sanitize_text_for_json(raw_title, 100),
                                "url": item.get("url", ""),
                                "snippet": _sanitize_text_for_json(raw_snippet, 1000),
                                "source": "外部信息来源",
                                "source_id": "20",
                                "score": item.get("score", 0.0)
                            })
                            
                except json.JSONDecodeError as e:
                    # 如果不是 JSON，作为纯文本处理
                    logger.warning(f"Failed to parse MCP response as JSON: {e}")
                    data.append({
                        "title": f"Result from {tool_name}",
                        "url": "",
                        "snippet": _sanitize_text_for_json(content_item.text, 500),
                        "source": "外部信息来源",
                        "source_id": "20",
                        "score": None
                    })
        
        if not data:
            return json.dumps({
                "data_type": "web_search",
                "success": False,
                "data": [],
                "error": "No search results found."
            }, ensure_ascii=False)
        
        # 返回标准格式
        return json.dumps({
            "data_type": "web_search",
            "success": True,
            "data": data,
            "metadata": {
                "count": len(data),
                "query": _sanitize_text_for_json(query, 200),
                "provider": f"mcp-{tool_name}"
            }
        }, ensure_ascii=False)

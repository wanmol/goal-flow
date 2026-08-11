"""
MCP Web Search Tool - web search tool based on the MCP protocol

Connects to a remote MCP service using the JSON-RPC over HTTP protocol

This is a public tool that can be used by any node or Agent
"""

import asyncio
import json
import threading
from typing import List, Dict, Any, Optional
import httpx
from goalflow.config import get_logger

logger = get_logger(__name__)


class MCPWebSearchTool:
    """MCP web search tool (remote HTTP mode)"""
    
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
        Initialize the MCP search tool

        Args:
            remote_url: URL of the remote MCP service (e.g. http://localhost:9001)
            api_key: API Key of the remote service (required, used for Bearer Token authentication)
            timeout: Request timeout (seconds)
            max_results: Maximum number of results to return
            debug: Whether to enable debug mode
            tool_name: Name of the tool to use (if not specified, the first available tool is used)
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
        """Get the next message ID"""
        self._msg_id += 1
        return self._msg_id
    
    async def _http_jsonrpc_request(self, method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Send a JSON-RPC request over HTTP

        Args:
            method: MCP method name (e.g. "tools/list", "tools/call")
            params: Method parameters

        Returns:
            JSON-RPC response
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
            "Authorization": f"Bearer {self.api_key}"  # Always add the Bearer Token
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
        """Asynchronously get all available tools from the MCP Server"""
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
        """Get all available tools from the MCP Server"""
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
        """Asynchronously call the specified MCP tool"""
        try:
            with self._lock:
                response = await self._http_jsonrpc_request(
                    "tools/call",
                    params={"name": tool_name, "arguments": arguments}
                )
                
                # Mimic the return format of the MCP client
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
        """Call the specified MCP tool"""
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
        Execute a search and return a JSON string in the standard format

        Args:
            query: Search query
            tool_name: Tool name (if not specified, uses self.tool_name or the first available tool)
            count: Number of results to return

        Returns:
            JSON string, in the format:
            {
                "data_type": "web_search",
                "success": true,
                "data": [...],
                "metadata": {...}
            }
        """
        def _sanitize_text_for_json(text: str, max_length: int = 500) -> str:
            """Clean text, removing control characters and limiting length"""
            if not text:
                return ""
            import re
            text = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', str(text))
            if len(text) > max_length:
                return text[:max_length] + "..."
            return text

        # Determine which tool to use
        tool_name = tool_name or self.tool_name

        # If no tool is specified, get the first available tool
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
        
        # Build the parameters
        arguments = {"query": query, "num": count}

        logger.info(f"Using MCP tool: {tool_name} with query: {query[:50]}...")

        # Call the tool
        result = self.call_tool(tool_name, arguments)
        
        if not result or not hasattr(result, 'content'):
            return json.dumps({
                "data_type": "web_search",
                "success": False,
                "data": [],
                "error": "No results from MCP server"
            }, ensure_ascii=False)
        
        # Parse and normalize the results
        data = []
        for content_item in result.content:
            if hasattr(content_item, "text"):
                try:
                    # Try to parse JSON
                    parsed_content = json.loads(content_item.text)

                    # Handle the different formats returned by MCP
                    if isinstance(parsed_content, dict) and "results" in parsed_content:
                        # Format 1: {"results": [...]}
                        results = parsed_content["results"]
                    elif isinstance(parsed_content, list):
                        # Format 2: [...]
                        results = parsed_content
                    else:
                        # Format 3: {...}
                        results = [parsed_content]

                    # Normalize the format of each result
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
                    # If it is not JSON, handle it as plain text
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
        
        # Return the standard format
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

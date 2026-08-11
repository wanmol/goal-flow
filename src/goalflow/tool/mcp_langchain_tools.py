"""MCP LangChain Tools - LangChain tool wrapper layer

Create LangChain Tools from a remote MCP Server

Configuration is read from environment variables (loaded by Database.init() at app startup):
- MCP_REMOTE_URL: URL of the MCP service (required)
- MCP_API_KEY: API authentication key (optional)
- MCP_TIMEOUT: Request timeout (seconds), default 120
- MCP_DEBUG: Debug mode, default false
"""
import os
import json
from typing import List, Optional
from langchain_core.tools import Tool, StructuredTool
from pydantic import BaseModel, Field
from goalflow.tool.mcp_web_search_tool import MCPWebSearchTool
from goalflow.config import get_logger

logger = get_logger(__name__)


class MCPToolInput(BaseModel):
    """MCP tool input model"""
    query: str = Field(description="搜索查询内容")
    count: int = Field(default=10, description="返回结果数量")


def create_mcp_tools(
    remote_url: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: Optional[int] = None,
    debug: Optional[bool] = None
) -> List[Tool]:
    """
    Create LangChain Tools from a remote MCP Server

    Configuration priority:
    1. Function arguments (if provided)
    2. Environment variables
    3. Default values

    Args:
        remote_url: URL of the MCP service (optional, defaults to reading from env var MCP_REMOTE_URL)
        api_key: API authentication key (optional, defaults to reading from env var MCP_API_KEY)
        timeout: Request timeout (optional, defaults to reading from env var MCP_TIMEOUT, ultimately 120)
        debug: Debug mode (optional, defaults to reading from env var MCP_DEBUG, ultimately False)

    Returns:
        List of LangChain Tools
    """


    # Read configuration from environment variables (if arguments not provided)
    remote_url = remote_url or os.getenv("MCP_REMOTE_URL")
    api_key = api_key or os.getenv("MCP_API_KEY") or None

    if timeout is None:
        timeout_str = os.getenv("MCP_TIMEOUT", "120")
        timeout = int(timeout_str)

    if debug is None:
        debug_str = os.getenv("MCP_DEBUG", "false").lower()
        debug = debug_str in ("true", "1", "yes")


    # Validate required parameters
    if not remote_url:
        logger.error("ERROR: MCP_REMOTE_URL is required")
        return []



    try:
        # Initialize the MCP client
        mcp_client = MCPWebSearchTool(
            remote_url=remote_url,
            api_key=api_key,
            timeout=timeout,
            debug=debug
        )

        # Get all tools from the MCP Server
        mcp_tools = mcp_client.list_tools()
        if not mcp_tools:
            logger.warning("NO_TOOLS_FROM_MCP_SERVER")
            return []



        # Create a LangChain Tool for each MCP tool
        langchain_tools = []
        for mcp_tool in mcp_tools:
            tool_name = mcp_tool['name']
            tool_description = mcp_tool.get('description', f'MCP {tool_name} tool')

            # Create the tool function (closure captures tool_name)
            def make_tool_func(captured_tool_name: str):
                def tool_func(query: str, count: int = 10) -> str:
                    """
                    LangChain tool wrapper function

                    Calls the underlying search method directly; all data formatting is done by the underlying layer
                    """
                    try:
                        logger.info(f"Calling MCP tool: {captured_tool_name} with query: {query[:50]}...")

                        # Call the underlying search method directly (formatting already done)
                        result = mcp_client.search(
                            query=query,
                            tool_name=captured_tool_name,
                            count=count
                        )

                        # Record result statistics
                        try:
                            result_data = json.loads(result)
                            data_count = len(result_data.get("data", []))
                            logger.info(f"MCP tool {captured_tool_name} returned {data_count} results")
                        except:
                            pass

                        return result

                    except Exception as e:
                        logger.error(f"Error calling MCP tool {captured_tool_name}: {e}", exc_info=True)
                        return json.dumps({
                            "data_type": "web_search",
                            "success": False,
                            "data": [],
                            "error": str(e)
                        }, ensure_ascii=False)

                return tool_func

            # Create the LangChain Tool
            langchain_tool = StructuredTool(
                name=tool_name,
                description=tool_description,
                func=make_tool_func(tool_name),
                args_schema=MCPToolInput
            )
            
            langchain_tools.append(langchain_tool)

        
        logger.info(f"TOTAL_TOOLS_CREATED: {len(langchain_tools)}")
        return langchain_tools
    
    except Exception as e:
        logger.error(f"FAILED_TO_CREATE_MCP_TOOLS: {e}", exc_info=True)
        return []

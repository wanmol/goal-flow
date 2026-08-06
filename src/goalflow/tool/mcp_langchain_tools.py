"""MCP LangChain Tools - LangChain 工具包装层

从远程 MCP Server 创建 LangChain Tools

配置从环境变量读取（由 Database.init() 在 app 启动时加载）：
- MCP_REMOTE_URL: MCP 服务的 URL（必需）
- MCP_API_KEY: API 认证密钥（可选）
- MCP_TIMEOUT: 请求超时时间（秒），默认 120
- MCP_DEBUG: 调试模式，默认 false
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
    """MCP 工具输入模型"""
    query: str = Field(description="搜索查询内容")
    count: int = Field(default=10, description="返回结果数量")


def create_mcp_tools(
    remote_url: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: Optional[int] = None,
    debug: Optional[bool] = None
) -> List[Tool]:
    """
    从远程 MCP Server 创建 LangChain Tools
    
    配置优先级：
    1. 函数参数（如果提供）
    2. 环境变量
    3. 默认值
    
    Args:
        remote_url: MCP 服务的 URL（可选，默认从环境变量 MCP_REMOTE_URL 读取）
        api_key: API 认证密钥（可选，默认从环境变量 MCP_API_KEY 读取）
        timeout: 请求超时时间（可选，默认从环境变量 MCP_TIMEOUT 读取，最终默认 120）
        debug: 调试模式（可选，默认从环境变量 MCP_DEBUG 读取，最终默认 False）
        
    Returns:
        LangChain Tool 列表
    """

    
    # 从环境变量读取配置（如果参数未提供）
    remote_url = remote_url or os.getenv("MCP_REMOTE_URL")
    api_key = api_key or os.getenv("MCP_API_KEY") or None
    
    if timeout is None:
        timeout_str = os.getenv("MCP_TIMEOUT", "120")
        timeout = int(timeout_str)
    
    if debug is None:
        debug_str = os.getenv("MCP_DEBUG", "false").lower()
        debug = debug_str in ("true", "1", "yes")

    
    # 验证必需参数
    if not remote_url:
        logger.error("ERROR: MCP_REMOTE_URL is required")
        return []
    

    
    try:
        # 初始化 MCP 客户端
        mcp_client = MCPWebSearchTool(
            remote_url=remote_url,
            api_key=api_key,
            timeout=timeout,
            debug=debug
        )
        
        # 获取 MCP Server 的所有工具
        mcp_tools = mcp_client.list_tools()
        if not mcp_tools:
            logger.warning("NO_TOOLS_FROM_MCP_SERVER")
            return []
        

        
        # 为每个 MCP 工具创建一个 LangChain Tool
        langchain_tools = []
        for mcp_tool in mcp_tools:
            tool_name = mcp_tool['name']
            tool_description = mcp_tool.get('description', f'MCP {tool_name} tool')
            
            # 创建工具函数（闭包捕获 tool_name）
            def make_tool_func(captured_tool_name: str):
                def tool_func(query: str, count: int = 10) -> str:
                    """
                    LangChain 工具包装函数
                    
                    直接调用底层的 search 方法，所有数据格式化由底层完成
                    """
                    try:
                        logger.info(f"Calling MCP tool: {captured_tool_name} with query: {query[:50]}...")
                        
                        # 直接调用底层的 search 方法（已经完成所有格式化）
                        result = mcp_client.search(
                            query=query,
                            tool_name=captured_tool_name,
                            count=count
                        )
                        
                        # 记录结果统计
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
            
            # 创建 LangChain Tool
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

import math
import json
import datetime
import time
import calendar
import dateutil
import os
from typing import Any
from jsonpath_ng import parse
from goalflow.constants import WF_TYPE_WORKFLOW, WF_TYPE_CHATFLOW
from goalflow.tool.utils import VariableResolver

from langchain_tavily import TavilySearch

from goalflow.config import get_logger
logger = get_logger(__name__)

def json_parse(
    tool_parameters: dict[str, Any],
    variable_pool: dict[str, Any],
):
    content = tool_parameters.get("content", "")
    if not content:
        raise ValueError("content cannot be None")

    json_filter = tool_parameters.get("json_filter", "")
    if not json_filter:
        raise ValueError("json_filter cannot be None")
    ensure_ascii = tool_parameters.get("ensure_ascii", True)

    content_str = VariableResolver.replace_template(
        template=content["value"], variables=variable_pool
    )
    logger.info(f"json_parse",content=content,content_str=content_str,json_filter=json_filter)
    try:
        input_data = json.loads(content_str)
        expr = parse(json_filter["value"])
        result = [match.value for match in expr.find(input_data)]
        if not result:
            return ""
        if len(result) == 1:
            result = result[0]
        if isinstance(result, dict | list):
            return json.dumps(result, ensure_ascii=ensure_ascii)
        elif isinstance(result, str | int | float | bool) or result is None:
            return str(result)
        else:
            return repr(result)
    except Exception as e:
        logger.error(f"json_parse error: {e}", exc_info=True)
        raise e
        #return str(e)


def tavily_search_adapter(tool_parameters: dict[str, Any], variable_pool: dict[str, Any]):
    """
    Tavily 搜索工具适配器

    Args:
        tool_parameters: 工具参数字典，包含 query, max_results 等
        variable_pool: 变量池（状态字典）

    Returns:
        搜索结果字符串（JSON 格式）
    """
    # 提取必需参数 query，并处理模板字符串
    query_dic = tool_parameters.get("query", {})
    if not query_dic.get("value"):
        raise ValueError("query parameter is required for Tavily search")

    query=query_dic["value"]
    # 如果 query 是字符串且包含模板变量，进行模板替换
    if isinstance(query, str) and ("{{" in query or "#" in query):
        query = VariableResolver.replace_template(query, variable_pool)
    else:
        logger.error("tavily_search query default:",tavily_search_query=query)

    include_domains_str =""
    include_domains_dic = tool_parameters.get("include_domains", {})
    if isinstance(include_domains_dic, dict) and include_domains_dic["value"] and ("{{" in include_domains_dic["value"] or "#" in include_domains_dic["value"]):
        include_domains_str = VariableResolver.replace_template(include_domains_dic["value"], variable_pool)

    include_domains_list =[]
    if include_domains_str and len(include_domains_str) > 0:
        include_domains_str_no_space = include_domains_str.replace(" ", "")
        include_domains_list=include_domains_str_no_space.split(",")

    # 提取可选参数
    exclude_domains_list=[]
    exclude_domains = tool_parameters.get("exclude_domains", {})
    if isinstance(exclude_domains, dict) and exclude_domains["value"] and len(exclude_domains["value"]) > 0:
        exclude_domains_list=exclude_domains["value"].split(", ")

    search_depth_val = ""
    search_depth = tool_parameters.get("search_depth", {})
    if isinstance(search_depth, dict) and search_depth["value"]:
        search_depth_val = search_depth["value"]

    time_range_val="month"
    time_range = tool_parameters.get("time_range", {})
    if isinstance(time_range, dict) and time_range["value"]:
        time_range_val=time_range["value"]
    if time_range_val == "not_specified":
        time_range_val = "month"

    topic_val="general"
    topic = tool_parameters.get("topic", {})
    if isinstance(topic,dict) and topic["value"]:
        topic_val = topic["value"]

    country_val = "china"
    country = tool_parameters.get("country", {})
    if isinstance(country,dict) and country["value"]:
        country_val = country["value"]

    days_val = 10000
    days = tool_parameters.get("days", {})
    if isinstance(days,dict) and days["value"]:
        days_val = days["value"]

    max_results = tool_parameters.get("max_results", 5)
    max_results = max(1, min(20, max_results))

    tavily_api_key = os.getenv("TAVILY_API_KEY")
    if not tavily_api_key:
        raise ValueError("TAVILY_API_KEY 环境变量未设置")

    search = TavilySearch(
        tavily_api_key=tavily_api_key,  # 从环境变量 TAVILY_API_KEY 读取
        search_depth=search_depth_val,  # 搜索深度：basic（基础，快）/advanced（高级，全量结果）
        max_results=max_results,        # 返回最大结果数，默认5，范围1-10
        include_answer=True,            # 可选：是否返回直接答案（而非仅网页片段，默认False）
        include_images=False,           # 可选：是否返回图片结果（默认False）
        days=days_val,                  # Tavily 支持的 days 上限较小，建议合理范围
        country=country_val,
        exclude_domains=exclude_domains_list,      # 需为 list
        include_domains=include_domains_list,      # 需为 list
        topic=topic_val,
        time_range=time_range_val,       # 只能是 day/week/month/year
    )

    try:
        logger.info("TavilySearch  request: ",TavilySearch=search)
        results = search.invoke(query)
        logger.info("The TavilySearch  results : " ,TavilySearch_results=results)
        # 将结果格式化为 JSON 字符串
        return json.dumps(results, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Tavily search error: {e}", exc_info=True)
        raise e


def mcp_tool_adapter(
    *,
    tool_name: str,
    tool_parameters: dict[str, Any],
    variable_pool: dict[str, Any],
    provider_config: Any = None,
):
    from goalflow.tool.mcp_web_search_tool import MCPWebSearchTool

    remote_url = variable_pool.get("mcp_server_url") or os.getenv("MCP_REMOTE_URL")
    api_key = os.getenv("MCP_API_KEY") or None
    timeout = int(os.getenv("MCP_TIMEOUT", "120"))
    debug = os.getenv("MCP_DEBUG", "false").lower() in ("true", "1", "yes")

    if not remote_url:
        raise ValueError("MCP remote url is required")

    client = MCPWebSearchTool(
        remote_url=remote_url,
        api_key=api_key,
        timeout=timeout,
        debug=debug,
        tool_name=tool_name,
    )
    result = client.call_tool(tool_name, tool_parameters)
    if not result or not hasattr(result, "content"):
        raise ValueError(f"MCP tool {tool_name} returned empty result")

    texts = [
        item.text
        for item in result.content
        if hasattr(item, "text") and item.text is not None
    ]
    if not texts:
        return ""
    if len(texts) == 1:
        return texts[0]
    return json.dumps(texts, ensure_ascii=False)


def simple_code(language: str, code: str):
    # 安全模块白名单
    ALLOWED_MODULES = {
        "math",
        "json",
        "datetime",
        "time",
        "calendar",
        "timedelta",
        "timezone",
        "dateutil",
        "dateutil.parser",
        "dateutil.relativedelta",
        "dateutil.tz",
        "_strptime",
        "_datetime",  # 添加这个内部模块
        "locale",  # strftime 可能需要这个模块
    }

    def safe_import(name, globals=None, locals=None, from_list=(), level=0):
        if name in ALLOWED_MODULES:
            return __import__(name, globals, locals, from_list, level)
        raise ImportError(f"导入模块 {name} 被禁止")

    # 创建安全环境
    safe_globals = {
        "__builtins__": {
            # 安全的内置函数
            "len": len,
            "sum": sum,
            "max": max,
            "min": min,
            "abs": abs,
            "round": round,
            "sorted": sorted,
            "range": range,
            "enumerate": enumerate,
            "zip": zip,
            "list": list,
            "dict": dict,
            "set": set,
            "tuple": tuple,
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "isinstance": isinstance,
            "type": type,
            "hasattr": hasattr,
            "print": print,
            "repr": repr,
            "hash": hash,
            "any": any,
            "all": all,
            "filter": filter,
            "map": map,
            "iter": iter,
            "next": next,
            # 安全异常类
            "Exception": Exception,
            "ValueError": ValueError,
            "TypeError": TypeError,
            "KeyError": KeyError,
            "IndexError": IndexError,
            "AttributeError": AttributeError,
            "NameError": NameError,
            "ZeroDivisionError": ZeroDivisionError,
            "RuntimeError": RuntimeError,
            "ImportError": ImportError,
            # 安全的导入函数
            "__import__": safe_import,
        },
        # 允许的模块
        "math": math,
        "json": json,
        "time": time,
        "calendar": calendar,
        "dateutil": dateutil,
        "datetime": datetime,
        "date": datetime.date,
        "datetime_class": datetime.datetime,
        "timedelta": datetime.timedelta,
        "timezone": datetime.timezone,
        "relativedelta": dateutil.relativedelta.relativedelta,
        # 常量
        "True": True,
        "False": False,
        "None": None,
    }

    safe_locals = {}
    try:
        exec(code, safe_globals, safe_locals)
        return safe_locals
    except Exception as e:
        import traceback

        error_trace = traceback.format_exc()
        print(f"代码执行错误详情:\n{error_trace}")
        raise RuntimeError(f"代码执行错误: {str(e)}") from e

# def onto_guess_question(args: dict[str, any]):
#     return workflow_onto_guess_question.execute(initial_state=args)

# key=provider_id (tool_workflow_providers表主键)
tool_list = {
    "langgenius/json_process/json_process": {
        "type": "builtin",
        "name": "json_process",
        "func": json_parse,
    },
    "langgenius/tavily/tavily": {
        "type": "builtin",
        "name": "tavily_search",
        "func": tavily_search_adapter,
    },
    "industry-agent-mcp": {
        "type": "mcp",
        "name": "industry_agent_mcp",
        "func": mcp_tool_adapter,
    },
    
    "simple_code": {"type": "builtin", "name": "simple_code", "func": simple_code},
}

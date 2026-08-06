"""
Research 相关的流式事件定义

用于输出研究过程的中间数据
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass


@dataclass
class ResearchProgressEvent:
    """研究进度事件"""
    node_id: str
    stage: str  # background/framework/planning/execution/reporting
    progress: Dict[str, Any]
    timestamp: str


@dataclass
class ToolCallEvent:
    """工具调用事件"""
    node_id: str
    task_id: str
    tool_name: str  # web_search/web_crawler/knowledge_base/python_executor
    input: Dict[str, Any]
    output: Optional[Dict[str, Any]] = None
    status: str = "started"  # started/completed/failed
    timestamp: Optional[str] = None


@dataclass
class TaskExecutionEvent:
    """任务执行事件"""
    node_id: str
    task_id: str
    task_title: str
    agent_type: str  # researcher/coder
    status: str  # started/in_progress/completed/failed
    progress: Dict[str, Any]
    timestamp: str


@dataclass
class SearchResultEvent:
    """搜索结果事件"""
    node_id: str
    task_id: str
    query: str
    results: List[Dict[str, Any]]  # 前5个结果
    total_count: int
    provider: str  # qianfan/tavily/serper
    timestamp: str


@dataclass
class CrawlerResultEvent:
    """爬虫结果事件"""
    node_id: str
    task_id: str
    url: str
    content_length: int
    key_points: List[str]
    status: str
    timestamp: str


@dataclass
class CodeExecutionEvent:
    """代码执行事件"""
    node_id: str
    task_id: str
    code_snippet: str  # 前500字符
    output: str
    execution_time: float
    status: str
    timestamp: str


@dataclass
class KnowledgeBaseResultEvent:
    """知识库检索结果事件"""
    node_id: str
    task_id: str
    query: str
    collection_type: str  # single/multi
    collection_name: Optional[str] = None  # 单表查询时的表名
    path_config_name: Optional[str] = None  # 多表查询时的配置名
    results: List[Dict[str, Any]] = None  # 检索结果（前5个）
    total_count: int = 0
    search_type: str = "hybrid"  # vector/keyword/hybrid
    avg_score: float = 0.0  # 平均相关性分数
    status: str = "completed"
    timestamp: str = ""


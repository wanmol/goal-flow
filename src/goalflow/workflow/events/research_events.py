"""
Research-related streaming event definitions

Used to output intermediate data of the research process
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass


@dataclass
class ResearchProgressEvent:
    """Research progress event"""
    node_id: str
    stage: str  # background/framework/planning/execution/reporting
    progress: Dict[str, Any]
    timestamp: str


@dataclass
class ToolCallEvent:
    """Tool call event"""
    node_id: str
    task_id: str
    tool_name: str  # web_search/web_crawler/knowledge_base/python_executor
    input: Dict[str, Any]
    output: Optional[Dict[str, Any]] = None
    status: str = "started"  # started/completed/failed
    timestamp: Optional[str] = None


@dataclass
class TaskExecutionEvent:
    """Task execution event"""
    node_id: str
    task_id: str
    task_title: str
    agent_type: str  # researcher/coder
    status: str  # started/in_progress/completed/failed
    progress: Dict[str, Any]
    timestamp: str


@dataclass
class SearchResultEvent:
    """Search result event"""
    node_id: str
    task_id: str
    query: str
    results: List[Dict[str, Any]]  # top 5 results
    total_count: int
    provider: str  # qianfan/tavily/serper
    timestamp: str


@dataclass
class CrawlerResultEvent:
    """Crawler result event"""
    node_id: str
    task_id: str
    url: str
    content_length: int
    key_points: List[str]
    status: str
    timestamp: str


@dataclass
class CodeExecutionEvent:
    """Code execution event"""
    node_id: str
    task_id: str
    code_snippet: str  # first 500 characters
    output: str
    execution_time: float
    status: str
    timestamp: str


@dataclass
class KnowledgeBaseResultEvent:
    """Knowledge base retrieval result event"""
    node_id: str
    task_id: str
    query: str
    collection_type: str  # single/multi
    collection_name: Optional[str] = None  # table name for single-table query
    path_config_name: Optional[str] = None  # config name for multi-table query
    results: List[Dict[str, Any]] = None  # retrieval results (top 5)
    total_count: int = 0
    search_type: str = "hybrid"  # vector/keyword/hybrid
    avg_score: float = 0.0  # average relevance score
    status: str = "completed"
    timestamp: str = ""


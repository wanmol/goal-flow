from goalflow.state import GenericState,BaseState
from goalflow.node import (
    BaseNode,
    IterationNode,
    LoopNode,
    ToolNode,
    AgentNode
)
from goalflow.trace.langfuse import TruncatedCallbackHandler
from langfuse.langchain import CallbackHandler
from typing import List,Iterator,Any,Optional,get_args,Iterable
from langgraph.graph import StateGraph,START
from langgraph.types import Checkpointer,Command
from abc import ABC, abstractmethod
from typing import Generic,cast
from langchain_core.runnables.config import RunnableConfig
from collections import defaultdict
from langfuse import get_client
from goalflow.constants import (
    WfNodeType,
    WF_TYPE_CHATFLOW,
    WF_TYPE_WORKFLOW,
    ErrorStrategy,
    ToolProviderType,
    UPSTREAM_TRACE_ID_HEADER_NAME,
    UPSTREAM_SPAN_ID_HEADER_NAME,
)
from goalflow.config import trace_info as trace_info_ctx
from goalflow.workflow.stream.chatflow_stream_out_decision_route import (
    AnswerEndStreamOutRouter,
    AnswerStreamGenerateRoute
)
from goalflow.workflow.stream.workflow_stream_out_decision_route import (
    EndStreamGenerateRoute,
    NormalEndStreamOutRouter
)
import uuid
import sys
from goalflow.workflow_types import  AgentToolValueConfig,EnvironmentVariable,ConversationVar
import threading
from goalflow.config import get_logger

logger = get_logger(__name__)


def _iter_langfuse_handlers(callbacks: Any) -> Iterable[Any]:
    """规范化 config["callbacks"]，yield 每一个 callback handler 实例。

    config["callbacks"] 可能是：
    - None / 空：什么都不 yield
    - list[BaseCallbackHandler]：直接 yield 每个元素
    - CallbackManager：yield 其 .handlers 列表
    - 单个 handler：直接 yield
    - 嵌套 list（包含 CallbackManager）：递归展开
    """
    if not callbacks:
        return
    if hasattr(callbacks, "handlers") and not isinstance(callbacks, list):
        for h in callbacks.handlers:
            yield h
        return
    try:
        for item in callbacks:
            if hasattr(item, "handlers") and not isinstance(item, list):
                for h in item.handlers:
                    yield h
            else:
                yield item
    except TypeError:
        yield callbacks


class GraphEdge:

    def __init__(
        self, 
        * ,
        id : Optional[str], 
        source : str, 
        source_handle : str, 
        target : str,
        target_handle : str, 
        source_type : Optional[str] = None, 
        target_type : Optional[str] = None, 
        is_in_iteration : Optional[bool] = None,
        is_in_loop : Optional[bool] = None
    ) -> None:
        self.id = id
        self.source = source
        self.source_handle = source_handle
        self.target = target
        self.target_handle = target_handle
        self.source_type = source_type
        self.target_type = target_type
        self.is_in_iteration = is_in_iteration
        self.is_in_loop = is_in_loop
        
        
        
class BaseWorkflow(Generic[GenericState],ABC):
    
    def __init__(
        self, 
        config_schema: type[Any] | None = None,
        workflow_type: str = WF_TYPE_CHATFLOW,
        /,
        *,
        iter_state_schema : type[Any] | None = None,
        loop_state_schema : type[Any] | None = None,
        checkpointer: Checkpointer = None
    ):
        self.workflow_type = workflow_type
        
        self.state_schema = get_args(self.__orig_bases__[0])[0]
        self.iter_state_schema = iter_state_schema or self.state_schema
        self.loop_state_schema = loop_state_schema or self.state_schema
        
        self.graph = StateGraph(self.state_schema,config_schema)

        self.nodes : list[BaseNode] = []
        self.edges : list[GraphEdge] = []
        self._setup_nodes()
        self._setup_edges()
        
        #self.environment_variables = []
        self._setup_environment_variables()
        
        self._setup_conversation_variables()
        
        self.init_graph_data()
        
        self._proc_end_stream_routes()
        
        # 处理迭代节点
        self._proc_iteration_nodes()
        #处理循环节点
        self._proc_loop_nodes()
        
        self._analysis_node_level()
        
        self.init_subwffunc = False

        self.compiled_graph = self.graph.compile(checkpointer=checkpointer)
        
        self.lock = threading.Lock()
    
    # for auto generated
    @abstractmethod
    def _setup_nodes(self):
        pass
    
    # for auto generated
    @abstractmethod
    def _setup_edges(self):
        pass
    
    # for auto generated
    @abstractmethod
    def _setup_environment_variables(self):
        pass
    
    # for auto generated 
    @abstractmethod
    def _setup_conversation_variables(self):
        pass
    
    # for manual 
    def append_environment_variable(self, environment_list : list[EnvironmentVariable]):
        self.environment_list = environment_list
        
    # for manual
    def append_conversation_variable(self, conversation_list : list[ConversationVar]):
        self.conversation_list = conversation_list
    
    # for manual 
    def append_edge(self, edge : GraphEdge):
        self.edges.append(edge)

    # for manual 
    def set_edges(self, edges : list[GraphEdge]):
        self.edges = edges
        
    def get_node(self, node_id : str) -> Optional[BaseNode]:
        if self.node_map is None:
            return None
        return self.node_map.get(node_id, None)
    
    def init_graph_data(self):
        self.node_map : dict[str, BaseNode] = {}
        self.parent_children_node_map : dict[str, list[str]] = defaultdict(list)
        self.parent_child_start_node_map : dict[str, str] = {}
        self.start_node_id : str = None

        for node in self.nodes:
            if node.type == WfNodeType.START.value:
                if self.start_node_id is not None:
                    raise ValueError("multi start not supported")
                self.start_node_id = node.id
            
            if node.parent_node_id is not None:
                self.parent_children_node_map[node.parent_node_id].append(node.id)
                
                if any([node.type == WfNodeType.ITERATION_START.value ,
                       node.type == WfNodeType.LOOP_START.value]):
                    self.parent_child_start_node_map[node.parent_node_id] = node.id
                    
            self.node_map[node.id] = node
        
        if self.start_node_id is None:
            raise ValueError("start node not found")
         
        for parent_id, _ in self.parent_children_node_map.items():
            if parent_id not in self.parent_child_start_node_map:
                raise ValueError(f"subgraph {parent_id} start node not found")
            
        self._edge_source_target_map : dict[str, list[GraphEdge]] = defaultdict(list)
        self._edge_target_source_map : dict[str, list[GraphEdge]] = defaultdict(list)
        for edge in self.edges:
            self._edge_source_target_map[edge.source].append(edge)
            self._edge_target_source_map[edge.target].append(edge)
        
        wf_name = type(self).__name__     
        for node in self.nodes:
            source_edges = self._edge_target_source_map[node.id]
            pre_node_ids = [edge.source for edge in source_edges]
            if pre_node_ids:
                node.pre_node_ids = pre_node_ids
            
            node.wf_name = wf_name


    @property
    def all_nodes(self) -> Optional[list[BaseNode]]:
        return self.nodes
    
    @property
    def all_edges(self) -> Optional[list[GraphEdge]]:
        return self.edges
    
    @property
    def start_node(self) -> Optional[BaseNode]:
        if self.start_node_id is None:
            return None
        return self.get_node(self.start_node_id)
    
    @property
    def edge_target_source_map(self) -> dict[str, list[GraphEdge]]:
        return self._edge_target_source_map

    @property
    def edge_source_target_map(self) -> dict[str, list[GraphEdge]]:
        return self._edge_source_target_map
    
    def _proc_end_stream_routes(self):
        
        # init answer stream generate routes
        answer_stream_generate_routes = AnswerEndStreamOutRouter.init(
            node_id_object_mapping=self.node_map, reverse_edge_mapping=self.edge_target_source_map
        )
        
        end_stream_generate_routes = NormalEndStreamOutRouter.init(
            node_id_object_mapping=self.node_map, reverse_edge_mapping=self.edge_target_source_map
        )
        
        self.answer_stream_generate_routes :AnswerStreamGenerateRoute = answer_stream_generate_routes

        self.end_stream_generate_routes : EndStreamGenerateRoute = end_stream_generate_routes
        # init end stream param
        #end_stream_param = EndStreamGeneratorRouter.init(
        #    node_id_config_mapping=node_id_config_mapping,
        #    reverse_edge_mapping=reverse_edge_mapping,
        #    node_parallel_mapping=node_parallel_mapping,
        #)
 
    def _proc_iteration_nodes(self):
        iteration_node_map : dict[str,list[BaseNode]] = defaultdict(list)
        for node in self.all_nodes:
            if node.isInIteration:
                if node.parent_node_id is None:
                    raise ValueError("iteration node must have parent node")

                iteration_node_map[node.parent_node_id].append(node)

        for parent_id, children in iteration_node_map.items():
            parent = self.get_node(parent_id)
            self._init_iteration_node(parent, children)

    
    def _init_iteration_node(self, parent : BaseNode, children : list[BaseNode]):
        
        if parent.type != WfNodeType.ITERATION.value:
            raise ValueError("parent node must be iteration node")

        parent = cast(IterationNode, parent)

        start_child = next(
            item for item in children if item.type == WfNodeType.ITERATION_START.value 
        )

        if start_child is None:
            raise ValueError("iteration node must have start child node")
        
        self._analysis_node_level(start_child)

        #leaf_node = None
        builder = StateGraph(self.iter_state_schema)
        for child in children:
            builder.add_node(child.id, child)
        
        builder.add_edge(START, start_child.id)
        
        #self._recursive_proc_iteration_children(start_child.id, builder)
        graph = builder.compile()

        parent.subgraph = graph


    def _recursive_proc_iteration_children(self, source_id : str, graph : StateGraph):
        source_node = self.get_node(source_id)
        
        if source_node is None:
            raise ValueError(f"node {source_id} not found")

        edges = self.edge_source_target_map[source_id]
         
        if edges == None or len(edges) == 0:
            return
        
        source_type = source_node.type
        
        # 分支节点没有办法静态定义边，约定如果是分支节点需要在节点内部进行路由处理
        if_branch_node = (
            source_type == WfNodeType.IF_ELSE.value or
            source_type == WfNodeType.QUESTION_CLASSIFIER.value
            or (source_node.error_strategy is not None 
                and source_node.error_strategy == ErrorStrategy.IF_ELSE.value
            )
        )
        
        if not if_branch_node:
            for edge in edges:
                graph.add_edge(edge.source, edge.target)
                
        for edge in edges:       
            self._recursive_proc_iteration_children(edge.target, graph)    



    def _proc_loop_nodes(self):
        loop_node_map : dict[str,list[BaseNode]] = defaultdict(list)
        for node in self.all_nodes:
            if node.isInLoop:
                if node.parent_node_id is None:
                    raise ValueError(f"loop child node {node.title} must have parent node")

                loop_node_map[node.parent_node_id].append(node)

        for parent_id, children in loop_node_map.items():
            parent = self.get_node(parent_id)
            self._init_loop_node(parent, children)

    
    def _init_loop_node(self, parent : BaseNode, children : list[BaseNode]):
        
        if parent.type != WfNodeType.LOOP.value:
            raise ValueError("parent node must be loop node")

        parent = cast(LoopNode, parent)

        start_child = next(
            item for item in children if item.type == WfNodeType.LOOP_START.value 
        )

        if start_child is None:
            raise ValueError("loop node must have start child node")
        
        self._analysis_node_level(start_child)

        #leaf_node = None
        builder = StateGraph(self.loop_state_schema)
        for child in children:
            builder.add_node(child.id, child)
        
        builder.add_edge(START, start_child.id)
        
        #self._recursive_proc_iteration_children(start_child.id, builder)
        graph = builder.compile()

        parent.subgraph = graph



    def execute(self,
        *,
        initial_state: GenericState,
        config: Optional[RunnableConfig] = {"recursion_limit": 500,"max_concurrency":6},
        ) -> GenericState:
        """Execute the workflow"""

        if self.environment_list is None:
            self.environment_list = []

        if "environment_variables" not in initial_state:
            initial_state["environment_variables"] = {}

        for item in self.environment_list:
            initial_state["environment_variables"][item.name] = item.value

        if self.conversation_list is None:
            self.conversation_list = []

        if "conversation_variables" not in initial_state:
            initial_state["conversation_variables"] = {}

        for item in self.conversation_list:
            initial_state["conversation_variables"][item.name] = item.value

        configurable = config.get("configurable",{})
        # used for checkpoint
        configurable["thread_id"] = uuid.uuid4()
        config["configurable"] = configurable
        initial_state["rt_thread_id"] = configurable["thread_id"]

        # Setup langfuse callback for tracing (errors logged,不影响主流程)
        self._setup_langfuse_callback(config)

        return self.compiled_graph.invoke(
            initial_state,
            config
        )
    
    def stream(self,
        initial_state: GenericState,
        config: Optional[RunnableConfig] = {"recursion_limit": 500,"max_concurrency":6},
        *,
        stream_mode : List[str] = ["messages","updates"]
    ) -> Iterator[Any]:
        """Execute the workflow"""

        if self.environment_list is None:
            self.environment_list = []

        if "environment_variables" not in initial_state:
            initial_state["environment_variables"] = {}

        for item in self.environment_list:
            initial_state["environment_variables"][item.name] = item.value

        if self.conversation_list is None:
            self.conversation_list = []

        if "conversation_variables" not in initial_state:
            initial_state["conversation_variables"] = {}

        for item in self.conversation_list:
            initial_state["conversation_variables"][item.name] = item.value

        configurable = config.get("configurable",{})
        # used for checkpoint
        configurable["thread_id"] = uuid.uuid4()
        config["configurable"] = configurable
        initial_state["rt_thread_id"] = configurable["thread_id"]

        # Setup langfuse callback for tracing (errors logged,不影响主流程)
        self._setup_langfuse_callback(config)

        yield from self.compiled_graph.stream(
            initial_state,
            config,
            stream_mode=stream_mode
        )
        
    def resume(
        self,
        resume_data: dict,
        config: RunnableConfig,
        *,
        stream_mode : List[str] = ["messages","updates"]
    )-> Iterator[Any]:

        if "interrupt_id" in resume_data and resume_data["interrupt_id"]:
            interrupt_id = resume_data["interrupt_id"]
            resume_data = {interrupt_id: resume_data}

        # Setup langfuse callback for tracing (errors logged,不影响主流程)
        self._setup_langfuse_callback(config)

        yield from self.compiled_graph.stream(
            Command(resume=resume_data),
            config,
            stream_mode=stream_mode
        )
        
    def resume_with_blocking_mode(
        self,
        resume_data: dict,
        config: RunnableConfig,
    )-> Any:

        # Setup langfuse callback for tracing (errors logged,不影响主流程)
        self._setup_langfuse_callback(config)

        return self.compiled_graph.invoke(
            Command(resume=resume_data),
            config
        )
        
    def _setup_langfuse_callback(self, config: RunnableConfig) -> None:
        """
        Setup langfuse callback handler for tracing.
        Errors are logged but do not affect the main workflow execution.

        Args:
            config: RunnableConfig to add callbacks and metadata to
        """
        # 如果 config 里已经有 langfuse CallbackHandler（含 TruncatedCallbackHandler），
        # 说明父级已经通过 var_child_runnable_config 把 handler 透传下来了
        # （典型场景：子工作流 execute() 进入时继承父级 callbacks），
        # 此时**不要**再创建一个新的 TruncatedCallbackHandler——
        # 否则会出现两个独立 _runs 字典、各自建 span，导致子工作流节点重复上报。
        if config and config.get("callbacks"):
            for h in _iter_langfuse_handlers(config.get("callbacks")):
                if isinstance(h, CallbackHandler):
                    logger.info(
                        f"Langfuse callback already set up, skip setup for {type(self).__name__}",
                        agent_name=type(self).__name__,
                    )
                    return

        try:
            # Get trace_id from config
            trace_id = config.get(UPSTREAM_TRACE_ID_HEADER_NAME)

            # Get conversation_id and user_id from config
            conversation_id = config.get("conversation_id")
            user_id = config.get("user_id")

            # Create trace context for langfuse handler
            trace_context = {"trace_id": trace_id} if trace_id else None

            # Create langfuse callback handler with truncation to prevent OOM
            langfuse_handler = TruncatedCallbackHandler(
                trace_context=trace_context,
            )

            # Prepare metadata for langfuse callback (user_id, conversation_id, agent_name)
            _langfuse_metadata = {}
            if conversation_id:
                _langfuse_metadata["langfuse_session_id"] = conversation_id
            if user_id:
                _langfuse_metadata["langfuse_user_id"] = user_id
            _langfuse_metadata["agent_name"] = type(self).__name__

            # Add handler to callbacks
            callbacks = list(config.get("callbacks", []))
            callbacks.append(langfuse_handler)
            config["callbacks"] = callbacks

            # Add metadata to config for langfuse handler to use
            metadata = config.get("metadata",{})
            if _langfuse_metadata:
                metadata.update(_langfuse_metadata)
                config["metadata"] = metadata

            logger.info(
                f"Langfuse callback setup success, agent_name: {type(self).__name__}, "
                f"conversation_id: {conversation_id}, user_id: {user_id}, trace_id: {trace_id}"
            )

        except Exception as e:
            # Log error but do not affect main flow
            logger.error(
                f"Failed to setup langfuse callback: {e}",
                exc_info=True,
            )

    def bind_subworkflows(self):
        
        if  self.init_subwffunc:
            return

        with self.lock:
            # safecheck
            if self.init_subwffunc:
                return
            
            self.init_subwffunc = True
            self._bind_subworkflows()
                        
    def _bind_subworkflows(self):
        from goalflow.workflow.tool_list import tool_list
        for node in self.nodes:
            if node.type == WfNodeType.TOOL.value:
                node = cast(ToolNode, node)
                
                provider_config = node.tool_provider_config
                provider_id = provider_config.provider_id
                tool_info = tool_list.get(provider_id)
                if tool_info is None:
                    raise ValueError(f"tool {provider_id} not found in {self.__class__.__name__} {node.formatted_name}")
                
                provider_type = provider_config.provider_type
                
                node.func = tool_info["func"]
                
                # 递归初始化工具节点要执行的函数
                if provider_type == ToolProviderType.WORKFLOW :
                    
                    subworkflow = tool_info["workflow_instance"]
                    subworkflow = cast(BaseWorkflow, subworkflow)
                    
                    if not subworkflow.init_subwffunc:
                        subworkflow.bind_subworkflows()
                    
                    
            if node.type == WfNodeType.AGENT.value:
                node = cast(AgentNode, node)
                agent_tools_config = node.tools
                if (agent_tools_config is None 
                    or agent_tools_config.value is None
                ):
                    continue
                
                tool_value_configs:list[AgentToolValueConfig] = agent_tools_config.value
                for item in tool_value_configs:
                    tool_info = tool_list.get(item.tool_name)
                    if tool_info is None:
                        raise ValueError(f"tool {item.tool_name} not found")
                    
                    item.func = tool_info["func"]
                    # TODO
                    node.tool_dict[item.tool_name] = item.func
                    tool_type = item.type
                    if tool_type == ToolProviderType.WORKFLOW.value :
                        
                        # 递归初始化工具节点要执行的函数
                        subworkflow = tool_info["workflow_instance"]
                        subworkflow = cast(BaseWorkflow, subworkflow)
                        
                        if not subworkflow.init_subwffunc:
                            subworkflow.bind_subworkflows()

    def _analysis_node_level(self,start_node:Optional[BaseNode] = None):
        if start_node is None:
            start_node = self.start_node
        curr_level = 1
        start_node.node_level = curr_level
        
        next_node_ids  = start_node.next_node_ids 
        
        self._recursive_assign_level(next_node_ids, curr_level+1)
        
    def _recursive_assign_level(self, node_ids : list[str], curr_level : int):
        for node_id in node_ids:
            node = self.get_node(node_id)
            #safeguard
            if curr_level > node.node_level:
                node.node_level = curr_level
            
            next_node_ids = node.next_node_ids or []
            # use copy, avoid modify original list
            next_node_ids = next_node_ids.copy()
            if node.fail_branch_node_ids:
                next_node_ids.extend(node.fail_branch_node_ids)
                
            if next_node_ids:
                self._recursive_assign_level(next_node_ids, curr_level+1)
        
        
                        


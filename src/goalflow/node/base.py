from typing import Generic,Optional,List,Union,TypedDict,Dict,Sequence,Any,Callable
from goalflow.workflow_types import NodeVarConfig,DefaultValue
from goalflow.constants import ErrorStrategy,WfNodeType
from langgraph.types import Command,Send
from pydantic import BaseModel
from goalflow.state import GenericState
from abc import ABC, abstractmethod
import time, copy
from goalflow.config import get_logger

from goalflow.tool.utils import VariableResolver

logger = get_logger(__name__)

NodeOutput = Union[
    TypedDict,  # outputs JSON-format changed content
    Dict,   # outputs JSON-format changed content
    List[str],  # mainly for branch nodes (ifelse, question-classifier)
    Command,  # for nodes with fail-branch operations
    Sequence[Send],  # for a node executed multiple times in parallel, like a map-reduce operation
    None  # neither an update operation nor a dynamic routing operation
]


class BaseNode(ABC,Generic[GenericState]):
    id: str
    desc : str
    selected : bool
    title : str
    type : str
    variables : Optional[List[NodeVarConfig]] = None
    
    isInIteration: Optional[bool] = False
    """Whether it is inside an iteration node"""

    isInLoop: Optional[bool] = False
    """Whether it is inside a loop node"""

    iteration_id: Optional[str] = None

    loop_id: Optional[str] = None

    pre_node_ids: Optional[list[str]] = None
    """Predecessor node id"""

    next_node_ids: Optional[list[str]] = None
    """Successor node id"""

    fail_branch_node_ids: Optional[list[str]] = None
    """Fail-branch node id"""

    parent_node_id: Optional[str] = None
    """Parent node id, the loop node or iteration node id"""

    wf_name: Optional[str] = None
    
    error_strategy: Optional[ErrorStrategy] = None
    default_value: Optional[list[DefaultValue]] = None
    
    def __init__(
        self, 
        * , 
        desc : str, 
        selected : bool, 
        title : str,
        isInIteration : Optional[bool] = None,
        isInLoop : Optional[bool] = None,
        iteration_id : Optional[str] = None,
        loop_id : Optional[str] = None,
        type : str, variables : Optional[List[NodeVarConfig]] = None,
        error_strategy : Optional[ErrorStrategy] = None,
        default_value : Optional[list[DefaultValue]] = None,
        fail_branch_node_ids : Optional[list[str]] = None,
        next_node_ids : Optional[list[str]] = None,
        id : Optional[str] = None,
        parent_node_id: Optional[str] = None,
        node_level: Optional[int] = 1,
        wf_name: Optional[str] = None
    ) -> None:

        self.desc = desc
        self.selected = selected
        self.title = title
        self.type = type
        self.id = id
        self.parent_node_id = parent_node_id
        self.node_level = node_level
        self.wf_name = wf_name
        
        if isInIteration is not None:
            self.isInIteration = isInIteration
        if isInLoop is not None:
            self.isInLoop = isInLoop
        if iteration_id is not None:
            self.iteration_id = iteration_id
        if loop_id is not None:
            self.loop_id = loop_id
            
        self.next_node_ids = next_node_ids
        
        self.fail_branch_node_ids = fail_branch_node_ids
        
        if variables is not None:
            self.variables = variables
            
        if error_strategy is not None:
            self.error_strategy = error_strategy

        if default_value is not None:
            self.default_value = default_value
            
    def to_json(self) -> dict:
        return {
            "id": self.id,
            "desc": self.desc,
            "selected": self.selected,
            "title": self.title,
            "type": self.type,
            "variables": self.variables,
            "error_strategy": self.error_strategy,
            "default_value": self.default_value,
            "fail_branch_node_ids": self.fail_branch_node_ids,
            "next_node_ids": self.next_node_ids,
            "pre_node_ids": self.pre_node_ids,
            "parent_node_id": self.parent_node_id,
            "isInIteration": self.isInIteration,
            "isInLoop": self.isInLoop,
            "iteration_id": self.iteration_id,
            "loop_id": self.loop_id
        }
        
    @abstractmethod
    def call(self,state:GenericState) -> NodeOutput:
        pass
    
    def pre_call(self,state:GenericState) -> Any:

        # fast return
        if self.pre_node_ids is None or len(self.pre_node_ids) <= 1:
            return None
        
        if (self.type == WfNodeType.END.value
            or self.type == WfNodeType.ANSWER.value):
            return None
        
        step = state.get("step",0)
        if self.node_level >= step + 1 :
            print("pre_call",self.id,self.title,self.node_level,step)
            return Command(
                update={"step":step+1},
                goto=[self.id]
            )
        else:
            return None
    
    def __call__(self,state:GenericState) -> NodeOutput:
        """implements protocol _StateNode"""
        
        start_time = time.perf_counter()

        if self.isInIteration:
            logger.info(f"{self.formatted_name} node started!, start_time:{start_time}",
                step=state.get("step",0),
                node_level=self.node_level,
                wf_name=self.wf_name,
                node_type=self.type,
                node_id=self.id,
                node_title=self.title,
                node_started=True,
                iteration_round=state.get("iteration_round", 0)
            )
        else:
            logger.info(f"{self.formatted_name} node started!, start_time:{start_time}",
                step=state.get("step",0),
                node_level=self.node_level,
                wf_name=self.wf_name,
                node_type=self.type,
                node_id=self.id,
                node_title=self.title,
                node_started=True,
            )

        # Preprocessing
        value = self.pre_call(state)
        if value is not None:
            return value

        try:
            # Execute the business logic
            value: Command = self.call(state)

            next_node_ids =  []
            output = value
            if value is not None and isinstance(value,Command):
                next_node_ids = value.goto or []
                output = value.update or {}
                
            output = self.truncate_output_value(output)
            
            cost_time = time.perf_counter() - start_time
            
            # def recursive_truncate(data):
            #     if isinstance(data, dict):
            #         result = data.copy()
            #         for key, value in list(result.items()):
            #             # Check whether this is a field that needs truncation
            #             if key == "financial_data" or "start_001_financial_data" == key:
            #                 result[key] = "<truncated_large_data>"
            #             elif key.startswith("start_001_financial_data"):
            #                 del result[key]
            #             elif key in ["company_info_str", "core_view_data", "operating_condition_data", "asset_quality_data", "liability_situation_data"]:
            #                 result[key] = value[:30] + "..." if len(value) > 30 else value
            #             else:
            #                 # Recursively process nested dicts
            #                 result[key] = recursive_truncate(value)
            #         return result
            #     elif isinstance(data, list):
            #         # Recursively process each element in the list
            #         return [recursive_truncate(item) for item in data]
            #     return data

            # # Recursively truncate the output data
            # log_output = recursive_truncate(copy.deepcopy(output))
            if self.isInIteration:
                iteration_item = VariableResolver.resolve_value_selector([self.parent_node_id, "item"], state)
                logger.info(f"{self.formatted_name} node finished!, cost_time:{cost_time}", 
                    step=state.get("step",0),
                    wf_name=self.wf_name,
                    node_type=self.type,
                    node_id=self.id,
                    node_title=self.title,
                    iteration_round=state.get("iteration_round", 0),
                    iteration_item=iteration_item,
                    next_node_ids=next_node_ids,
                    output=output,
                    node_finished=True,
                )
            else:
                logger.info(f"{self.formatted_name} node finished!, cost_time:{cost_time}", 
                    step=state.get("step",0),
                    wf_name=self.wf_name,
                    node_type=self.type,
                    node_id=self.id,
                    node_title=self.title,
                    next_node_ids=next_node_ids,
                    output=output,
                    node_finished=True,
                )
            
            if (self.type == WfNodeType.END.value
                or self.type == WfNodeType.ANSWER.value):
                return value
            
            step = state.get("step",0)
            #print(self.formatted_name)

            value.update.update({"step":step+1})

            return value

        except Exception as e:
            # Must re-raise the exception; the outer layer catches it and sends an error event to the frontend
            raise e

    # Used for printing the output value; default implementation
    def truncate_output_value(self, value : any) :
        return value
    
    @property
    def formatted_name(self) -> str:
        return f"{self.wf_name}_{self.type}_{self.id}_{self.title}"

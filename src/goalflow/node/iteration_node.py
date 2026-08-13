from goalflow.node.base import BaseNode,NodeOutput
from typing import Dict, Any, Optional, Sequence, List
from pydantic import BaseModel
from goalflow.state import BaseState,GenericState
from goalflow.constants import WfNodeType,ErrorHandleMode
from langgraph.graph.state import CompiledStateGraph
from langgraph.graph import StateGraph, START
from langgraph.graph.state import Send,Command
from goalflow.tool.utils import VariableResolver


from goalflow.config import get_logger
logger = get_logger(__name__)


class IterationStartNode(BaseNode):
    
    def __init__(
        self,
        **kwargs
    ):
        super().__init__(**kwargs)
    
    def call(self, state: GenericState) -> NodeOutput:
        return Command(
            update={},
            goto=self.next_node_ids
        )



class IterationNode(BaseNode):
    """
    Iteration node for processing arrays and collections.
    This node iterates over array items and executes sub-workflows for each item.
    """
    start_node_id: str
    parallel_nums: int = 3
    is_parallel: bool = False
    iterator_selector: Sequence[str]
    output_selector: Sequence[str]
    subgraph: Optional[CompiledStateGraph] = None
    output_type: str
    error_handle_mode: ErrorHandleMode = ErrorHandleMode.TERMINATED
    
    # read only
    __node_type = WfNodeType.ITERATION
    
    @property
    def node_type(self) -> WfNodeType:
        return self.__node_type
    
    def __init__(
        self,
        *, 
        start_node_id: str, 
        parallel_nums: int = 5, 
        is_parallel: bool = False,
        iterator_selector: Sequence[str], 
        output_selector: Sequence[str], 
        output_type: str, 
        error_handle_mode: ErrorHandleMode = ErrorHandleMode.TERMINATED,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.start_node_id = start_node_id
        self.parallel_nums = parallel_nums
        self.is_parallel = is_parallel
        self.iterator_selector = iterator_selector
        self.output_selector = output_selector
        self.output_type = output_type
        self.error_handle_mode = error_handle_mode
    
    def call(self, state: GenericState) -> NodeOutput:
        """
        Execute iteration over the specified array.
        """
        if self.subgraph is None:
            raise ValueError("iteration node subgraph is None")
        
        inputs = VariableResolver.resolve_value_selector(self.iterator_selector, state)
        
        if inputs is None:
            raise ValueError("iteration node inputs is None")

        if not isinstance(inputs, list):
            raise ValueError("iteration node inputs must be list")
        
        # Pre-size the result list to the full input length and write each result
        # into its own slot by index. This fixes two bugs in the old code:
        #   1. data loss  — it only dispatched min(parallel_nums, len(inputs)) items,
        #      silently dropping everything past parallel_nums.
        #   2. ordering/race — every Send appended to one shared closure list, so
        #      results landed in completion order (not input order) and multiple
        #      concurrent branches mutated the same list.
        # Per-index assignment to distinct slots is safe under CPython threading.
        outputs = [None] * len(inputs)

        builder = StateGraph(BaseState)

        def parallel_route(state: BaseState) -> BaseState:
            send_list = []
            # Dispatch ALL items; concurrency is bounded by max_concurrency below,
            # not by truncating the work list.
            for i in range(len(inputs)):
                item = inputs[i]
                state_copy = state.copy()
                state_copy["output_variables"] = state_copy["output_variables"].copy()
                update_data = VariableResolver.format_output(
                    node_id=self.id,
                    outputs={"item": item}
                )
                state_copy["output_variables"].update(update_data["output_variables"])
                # 1-based round doubles as the 0-based result index (round - 1).
                state_copy["iteration_round"] = i + 1

                send_list.append(Send("call_subgraph", state_copy))

            return send_list

        def call_subgraph(subgraph_state: BaseState) -> BaseState:

            iteration_round = subgraph_state.get("iteration_round", 0)
            item = VariableResolver.resolve_value_selector([self.id, "item"], subgraph_state)

            logger.info("begin_execute_iteration_subgraph", iteration_round=iteration_round, item=item)

            subgraph_outputs = self.subgraph.invoke(subgraph_state)
            output = VariableResolver.resolve_value_selector(self.output_selector, subgraph_outputs)
            # Write to this item's own slot so the result order matches input order
            # regardless of which branch finishes first.
            outputs[iteration_round - 1] = output

        #builder.add_node("parallel_route", parallel_route)
        builder.add_node("call_subgraph", call_subgraph)
        builder.add_conditional_edges(
            START,
            parallel_route,
            ["call_subgraph"],
        )

        graph = builder.compile()

        # parallel_nums is a concurrency cap, not a work cap. is_parallel=False runs
        # the items one at a time (cap=1); otherwise cap at parallel_nums (min 1).
        max_concurrency = max(1, self.parallel_nums) if self.is_parallel else 1
        graph.invoke(state, config={"max_concurrency": max_concurrency})

        update = VariableResolver.format_output(node_id=self.id, outputs={"output":outputs})
        return Command(
            update=update,
            goto=self.next_node_ids
        )


        

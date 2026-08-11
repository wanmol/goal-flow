from typing import TypedDict, Sequence, Optional, TypeVar, Dict
from typing_extensions import Annotated
from goalflow.workflow_types import File,EnvironmentVariable
from langgraph.channels import AnyValue,LastValue

def persist_value(current, new):
    """Reducer that preserves business state across conversation turns.

    An AnyValue channel is reset to None on each new graph invocation (LangGraph behavior);
    using this function instead of AnyValue ensures that when a node does not explicitly write,
    the old value in the checkpoint is preserved.
    - Node returns a new value (non-None) → update to the new value
    - New value is None (not written this turn) → keep the old value in the checkpoint
    """
    return new if new is not None else current

def update_vars(current_vars: dict[str,any], other_vars: dict[str,any]):
    current_vars.update(other_vars)
    return current_vars

def deep_merge_vars(current_vars: dict[str,any], other_vars: dict[str,any]):
    """
    Deeply merge variables, supporting deep merge of nested dicts

    For nested dicts (such as upstreams in node_span_ids), use deep merge instead of overwriting,
    ensuring that when multiple nodes execute in parallel, their updates merge correctly rather than overwriting each other.
    """
    def deep_merge_dict(base: dict, update: dict) -> dict:
        """Deeply merge two dicts, ensuring nested structures (such as upstreams) are not overwritten"""
        result = {}
        # First deep-copy all nested dicts in base
        for key, value in base.items():
            if isinstance(value, dict):
                result[key] = deep_merge_dict(value, {})
            else:
                result[key] = value

        # Then deep-merge update
        for key, value in update.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                # Deep-merge nested dicts (especially upstreams)
                result[key] = deep_merge_dict(result[key], value)
            else:
                # If value is a dict, it also needs to be deep-copied
                if isinstance(value, dict):
                    result[key] = deep_merge_dict(value, {})
                else:
                    result[key] = value
        return result

    # Use deep merge instead of shallow update
    return deep_merge_dict(current_vars, other_vars)

# Base state definition (runtime state, copied between multiple nodes, so no overwrite-update issues)
class BaseState(TypedDict):
    sys_query: str
    sys_dialogue_count: Optional[int]
    sys_conversation_id: Optional[str]
    sys_user_id: str
    sys_files: Optional[Sequence[File]]
    sys_app_id: str
    sys_workflow_id: str
    sys_workflow_run_id: str
    
    sys_use_end_stream: bool = True
    
    # openai-like input parameters; the parameters may contain historical messages that need to be saved to redis, otherwise passing them through state wastes memory resources
    sys_openai_param: bool = False

    # Agent run scenario type  WANMOL: single-agent run, WANMOL_HUB: intelligent hub redirect
    sys_scene_type: str

    # Runtime state
    node_id: Annotated[str,AnyValue]
    source_handle: Annotated[str,AnyValue] 
    step: Annotated[int,AnyValue]
    iteration_round: Optional[int]
    
    # used for checkpoint
    rt_thread_id: Annotated[Optional[str], AnyValue] 
    
    request_id : Annotated[str,AnyValue]

    # Store the workflow's final output data
    outputs: Annotated[dict,AnyValue]

    # The input at the start of the workflow
    input_variables: Annotated[dict[str,any],update_vars] = {}

    # Nodes' output variables
    output_variables: Annotated[dict[str,any],update_vars] = {}

    # Conversation variables, shared by all nodes
    conversation_variables: Annotated[dict[str,any],update_vars] = {}

    # Environment variables
    environment_variables: Annotated[dict[str,any],update_vars] = {}

    # System time (global data)
    sys_current_date: Annotated[Optional[str], AnyValue]       # Current date (YYYY-MM-DD)
    sys_current_datetime: Annotated[Optional[str], AnyValue]   # Current datetime (ISO 8601)



    # ===== HITL related fields =====
    hitl_checkpoint: Annotated[Optional[str], AnyValue]        # Current checkpoint
    hitl_status: Annotated[Optional[str], AnyValue]            # HITL status
    hitl_review_id: Annotated[Optional[str], AnyValue]         # Review ID
    hitl_started_at: Annotated[Optional[str], AnyValue]        # Start time
    hitl_submitted_at: Annotated[Optional[str], AnyValue]      # Submit time
    hitl_action: Annotated[Optional[str], AnyValue]            # Review action
    hitl_comment: Annotated[Optional[str], AnyValue]           # Review comment
    


GenericState = TypeVar("GenericState",bound=BaseState, covariant=True)

__all__ = ["BaseState","GenericState"]


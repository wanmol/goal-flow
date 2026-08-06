from typing import TypedDict, Sequence, Optional, TypeVar, Dict
from typing_extensions import Annotated
from goalflow.workflow_types import File,EnvironmentVariable
from langgraph.channels import AnyValue,LastValue

def persist_value(current, new):
    """跨对话轮次保留业务状态的 reducer。

    AnyValue channel 在每次新 graph 调用时会被重置为 None（LangGraph 行为），
    使用此函数替代 AnyValue 可确保：节点未显式写入时，checkpoint 中的旧值被保留。
    - 节点返回新值（非 None）→ 更新为新值
    - 新值为 None（本轮未写入）→ 保留 checkpoint 中的旧值
    """
    return new if new is not None else current

def update_vars(current_vars: dict[str,any], other_vars: dict[str,any]):
    current_vars.update(other_vars)
    return current_vars

def deep_merge_vars(current_vars: dict[str,any], other_vars: dict[str,any]):
    """
    深度合并变量，支持深度合并嵌套字典
    
    对于嵌套字典（如 node_span_ids 中的 upstreams），使用深度合并而不是覆盖，
    确保多个节点并行执行时，它们的更新能够正确合并而不是相互覆盖。
    """
    def deep_merge_dict(base: dict, update: dict) -> dict:
        """深度合并两个字典，确保嵌套结构（如 upstreams）不会被覆盖"""
        result = {}
        # 先深度拷贝 base 中的所有嵌套字典
        for key, value in base.items():
            if isinstance(value, dict):
                result[key] = deep_merge_dict(value, {})
            else:
                result[key] = value
        
        # 然后深度合并 update
        for key, value in update.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                # 深度合并嵌套字典（特别是 upstreams）
                result[key] = deep_merge_dict(result[key], value)
            else:
                # 如果 value 是字典，也需要深度拷贝
                if isinstance(value, dict):
                    result[key] = deep_merge_dict(value, {})
                else:
                    result[key] = value
        return result
    
    # 使用深度合并而不是浅层更新
    return deep_merge_dict(current_vars, other_vars)

# 基础状态定义 (运行时状态，多个节点间会复制，不会有覆盖更新问题)
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
    
    # 类openai格式的入参， 参数中可能包含历史message，需要保存到redis中，否则通过state传递会浪费内存资源
    sys_openai_param: bool = False
    
    # 智能体运行场景类型  WANMOL：单智能体运行， WANMOL_HUB：智能中枢跳转
    sys_scene_type: str 
    
    # 运行时状态  
    node_id: Annotated[str,AnyValue]
    source_handle: Annotated[str,AnyValue] 
    step: Annotated[int,AnyValue]
    iteration_round: Optional[int]
    
    # used for checkpoint
    rt_thread_id: Annotated[Optional[str], AnyValue] 
    
    request_id : Annotated[str,AnyValue]

    # 存放工作流结束输出数据
    outputs: Annotated[dict,AnyValue]
    
    # 流程开始的输入
    input_variables: Annotated[dict[str,any],update_vars] = {}

    #节点的输出变量
    output_variables: Annotated[dict[str,any],update_vars] = {}
    
    #会话变量，所有节点共享
    conversation_variables: Annotated[dict[str,any],update_vars] = {}
    
    # 环境变量
    environment_variables: Annotated[dict[str,any],update_vars] = {}
    
    # 系统时间（全局数据）
    sys_current_date: Annotated[Optional[str], AnyValue]       # 当前日期 (YYYY-MM-DD)
    sys_current_datetime: Annotated[Optional[str], AnyValue]   # 当前日期时间 (ISO 8601)
    
    
    
    # ===== HITL 相关字段 =====
    hitl_checkpoint: Annotated[Optional[str], AnyValue]        # 当前 checkpoint
    hitl_status: Annotated[Optional[str], AnyValue]            # HITL 状态
    hitl_review_id: Annotated[Optional[str], AnyValue]         # 审核 ID
    hitl_started_at: Annotated[Optional[str], AnyValue]        # 开始时间
    hitl_submitted_at: Annotated[Optional[str], AnyValue]      # 提交时间
    hitl_action: Annotated[Optional[str], AnyValue]            # 审核动作
    hitl_comment: Annotated[Optional[str], AnyValue]           # 审核意见
    


GenericState = TypeVar("GenericState",bound=BaseState, covariant=True)

__all__ = ["BaseState","GenericState"]


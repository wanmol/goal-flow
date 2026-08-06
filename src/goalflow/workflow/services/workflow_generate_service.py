from goalflow.workflow.base_workflow import BaseWorkflow
from goalflow.state import GenericState
import uuid
from goalflow.workflow.chunk_processor.workflow_stream_processor import WorkflowStreamProcessor
from goalflow.errors import WorkflowError
import traceback
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Dict, Any,cast
from goalflow.workflow.stream.types import *
from goalflow.model.wf_message import Message
from goalflow.service.message_service import MessageService
from goalflow.state import GenericState, BaseState
from goalflow.config import request_id as request_id_ctx
from langchain_core.runnables.config import RunnableConfig
from goalflow.constants import STATE_VARIABLE_TYPE_INPUT, STATE_VARIABLE_TYPE_OUTPUT, STATE_VARIABLE_TYPE_CONVERSATION, STATE_VARIABLE_TYPE_ENVIRONMENT

from goalflow.infra.redis_manager import redis_client
import time
import json

from goalflow.config import get_logger

logger = get_logger(__name__)

class WorkflowGenerateService:
    
    def __init__(self, workflow: BaseWorkflow[GenericState]):
        self.workflow = workflow
        self.stream_processor = WorkflowStreamProcessor(workflow)

    @staticmethod
    def _is_stopped(key: str) -> bool:
        stopped = redis_client.get(key)
        if stopped:
            return True
        return False

    @staticmethod
    def set_stopped(key: str):
        redis_client.set(key, CONST_REDIS_STOP_MARK_TIMEOUT)

    def insert_message(self, initial_state: BaseState):

        new_message = MessageService.create(
            Message(
                conversation_id=initial_state["sys_conversation_id"],
                query=initial_state["sys_query"],
                inputs=initial_state["input_variables"],
                message_id=str(uuid.uuid4()),
                creator_id=initial_state["sys_user_id"],
            )
        )

        return new_message

    def update_message(self, initial_state: BaseState, answer: str, mid: int):

        message = Message(
            id=mid,
            answer=answer,
            conversation_id=initial_state["sys_conversation_id"],
            query=initial_state["sys_query"],
            last_updater_id=initial_state["sys_user_id"],
        )
        MessageService.update(message)

    # 流式执行
    def generate(self, initial_state: GenericState):
        # Start streaming
        chunk_counter = 0
        workflow_run_id = str(uuid.uuid4())
        request_id = initial_state.get("request_id")
        user_id = initial_state.get("sys_user_id")
        request_id_ctx.set(request_id)

        # workflow暂不考虑消息持久化存储，不像chatflow有多轮会话的概念
        # 插入消息
        start_time = time.perf_counter()
        #message = self.insert_message(initial_state)
        #logger.info(f"insert message cost time: {time.perf_counter() - start_time}")

        #message_id = message.id
        #message_uuid = message.message_id
        #if message_id is None or message_uuid is None:
        #    raise WorkflowError("插入消息失败")
        
        #conversation_id = message.conversation_id
        #initial_state["sys_conversation_id"] = conversation_id

        try:
            initial_state["sys_workflow_run_id"] = workflow_run_id
            
            # Send start event
            yield format_stream_chunk(
                chunk_id=chunk_counter,
                event_type="workflow_started", 
                data={"workflow_run_id": workflow_run_id, "status": "started"},
                workflow_run_id=workflow_run_id,
                task_id=workflow_run_id,
                #message_id=message_uuid,
                #conversation_id=conversation_id,
            )
            chunk_counter += 1

            runnable_config: RunnableConfig = {
                "recursion_limit": 500,
                "max_concurrency": 6,
                # use for log ,base on context copy
                #"message_id": message_uuid,
                #"conversation_id": conversation_id,
                "user_id": user_id,
                "request_id": request_id,
                "metadata": {
                    "user_id": user_id,
                    "request_id": request_id,
                },
            }
            
            # Execute workflow with streaming
            for stream_event in self.stream_processor.process(
                self.workflow.stream(
                    initial_state=initial_state, 
                    config=runnable_config,
                    stream_mode=["updates", "messages"],
                )
            ):
                #print(stream_event)

                chunk_counter += 1

                use_check_stop = chunk_counter % STREAM_OUTPUT_STOP_CHECK_INTERVAL == 0

                stopped_cache_key = f"generate_task_stopped:{workflow_run_id}"
                
                use_check_stop = use_check_stop or not isinstance(stream_event, NodeRunStreamChunkEvent)

                if use_check_stop and self._is_stopped(stopped_cache_key):
                    break
                
                if isinstance(stream_event, NodeRunSucceededEvent):
                    stream_event = cast(NodeRunSucceededEvent,stream_event)
                    node_id = stream_event.node_id
                    node_data = stream_event.node_data
                    node_type = stream_event.node_type
                    outputs = stream_event.outputs
                    data = node_data
                    #data["outputs"] = outputs

                    # end节点直接输出outputs，没有经过output_variables包装
                    if node_type == WfNodeType.END.value:
                        if "outputs" in outputs:
                            outputs = outputs["outputs"]
                        message_content = json.dumps(outputs)

                    outputs.update({"workflow_run_id": workflow_run_id})
                    outputs.update({"title": node_data.get("title", "")})

                    if "output_variables" in outputs:
                        output_variables = outputs.pop("output_variables")
                        output_data = {}
                        for key, value in output_variables.items():
                            if key.startswith(node_id + "_"):
                                output_data[key[len(node_id) + 1 :]] = value

                        outputs["outputs"] = output_data
                
                    yield format_stream_chunk(
                        task_id=workflow_run_id,
                        chunk_id=node_id,
                        #message_id=message_uuid,
                        #conversation_id=conversation_id,
                        # chunk_counter=chunk_counter,
                        event_type="node_finished",
                        data=outputs,
                        workflow_run_id=workflow_run_id,
                    )
                # llm节点
                elif isinstance(stream_event, NodeRunStreamChunkEvent):
                    stream_event = cast(NodeRunStreamChunkEvent,stream_event)
                    node_id = stream_event.node_id
                    metadata = stream_event.metadata

                    from_variable_selector = [node_id, "text"]
                    yield format_stream_chunk(
                        chunk_id=node_id,
                        event_type="text_chunk", 
                        data={
                            "text":stream_event.chunk_content,
                            "from_variable_selector":from_variable_selector
                        }, 
                        #answer=stream_event.chunk_content,
                        workflow_run_id=workflow_run_id,
                        metadata=metadata,
                        task_id=workflow_run_id,
                    )
            
            # Send completion event
            yield format_stream_chunk(
                chunk_id=chunk_counter + 1,
                event_type="workflow_finished",
                data={"workflow_run_id": workflow_run_id, "status": "completed"},
                task_id=workflow_run_id,
                workflow_run_id=workflow_run_id,
                #message_id=message_uuid,
                #conversation_id=conversation_id,
            )
            
        except WorkflowError as e:
            #traceback.print_exc()
            logger.error(f"WorkflowError_{e}", exc_info=True, user_id=user_id)

            yield format_stream_chunk(
                chunk_id=chunk_counter + 1,
                event_type="error",
                data={
                    #"error": str(e),
                    "error_type": "WorkflowError",
                    "workflow_run_id": workflow_run_id,
                },
                message=str(e),
                task_id=workflow_run_id,
                #message_id=message_uuid,
                #conversation_id=conversation_id,
            )
        except Exception as e:
            #traceback.print_exc()
            logger.error(f"UnknownError_{e}", exc_info=True,  user_id=user_id)

            yield format_stream_chunk(
                chunk_id=chunk_counter + 1,
                event_type="error",
                data={
                    #"error": str(e),
                    "error_type": "UnknownError",
                    "workflow_run_id": workflow_run_id,
                },
                workflow_run_id=workflow_run_id,
                task_id=workflow_run_id,
                message=str(e),
                #message_id=message_uuid,
                #conversation_id=conversation_id,
            )
        
        #self.update_message(initial_state, answer=message_content, mid=message_id)
        #self.stream_processor.process(init_state)
    
    # 非流式执行
    def execute(self, initial_state: BaseState):
        request_id = initial_state.get("request_id")
        user_id = initial_state.get("sys_user_id")
        request_id_ctx.set(request_id)

        workflow_run_id = initial_state.get("sys_workflow_run_id")
        if not workflow_run_id:
            workflow_run_id = str(uuid.uuid4())
            initial_state["sys_workflow_run_id"] = workflow_run_id
            
        try:
            runnable_config: RunnableConfig = {
                "recursion_limit": 500,
                "max_concurrency": 6,
                # use for log ,base on context copy
                "user_id": user_id,
                "request_id": request_id,
                "metadata": {
                    "user_id": user_id,
                    "request_id": request_id,
                },
            }

            start_time = time.time()
            result = self.workflow.execute(initial_state=initial_state, config=runnable_config)
            end_time = time.time()

            logger.info(f"workflow execute result: {result}")

            del result[STATE_VARIABLE_TYPE_INPUT]
            del result[STATE_VARIABLE_TYPE_OUTPUT]
            del result[STATE_VARIABLE_TYPE_CONVERSATION]
            del result[STATE_VARIABLE_TYPE_ENVIRONMENT]

            data = {
                "id": workflow_run_id,
                "outputs": result.get("outputs",{}),
                "elapsed_time": end_time - start_time,
                "created_at": start_time,
                "finished_at": end_time,
                "status": "succeeded"
            }

            response = WorkflowCompletionResponse(
                #id=workflow_run_id,
                workflow_run_id=workflow_run_id,
                task_id=workflow_run_id,
                data=data,
            )
            return response
        except Exception as e:
            logger.error(f"workflow_execute_error_{e}", exc_info=True, message_id=workflow_run_id, user_id=user_id)
            raise e
        
        
def format_stream_chunk(
        *,
        chunk_id: int, 
        event_type: str, 
        data: Dict[str, Any], 
        workflow_run_id: str,
        task_id: str = None,
        message_id: str = None,
        conversation_id: str = None,
        answer: str = None,
        metadata: Dict[str, Any] = None,
        message: str = None,
    ) -> str:
    """Format a streaming chunk as SSE format."""
    chunk = WorkflowStreamChunk(
        chunk_id=str(chunk_id),
        event=event_type,
        data=data,
        workflow_run_id=workflow_run_id,
        timestamp=datetime.utcnow().isoformat()
    )
    if data is not None:
        chunk.data = data

    if task_id is not None:
        chunk.task_id = task_id
    if message_id is not None:
        chunk.message_id = message_id
    if conversation_id is not None:
        chunk.conversation_id = conversation_id
    
    if answer is not None:
        chunk.answer = answer

    if metadata is not None:
        chunk.metadata = metadata

    if message is not None:
        chunk.message = message

    # Format as Server-Sent Events
    return f"data: {chunk.model_dump_json()}\n\n"


class WorkflowStreamChunk(BaseModel):
    """Streaming response chunk model."""
    chunk_id: str = Field(..., description="分块ID")
    workflow_run_id: str = Field(None, description="工作流运行ID")
    event: str = Field(..., description="分块类型: 'message'|'update'|'error'|'done'")
    data: Dict[str, Any] = Field(None, description="分块数据")
    timestamp: str = Field(..., description="时间戳")
    answer: str = Field(None, description="回答")
    metadata: Dict[str, Any] = Field(None, description="元数据")
    task_id: str = Field(None, description="任务ID")
    message_id: str = Field(None, description="消息ID")
    conversation_id: str = Field(None, description="会话ID")
    message: str = Field(None, description="错误消息，兼容dify")

class WorkflowCompletionResponse(BaseModel):
    """workflow completion response model."""
    task_id: str = Field(..., description="任务ID")
    workflow_run_id: str = Field(..., description="工作流运行ID")

    data: Dict[str, Any] = Field(None, description="执行输出结果")

    metadata: Dict[str, Any] = Field(None, description="元数据")

    message: str = Field(None, description="错误消息，兼容dify")


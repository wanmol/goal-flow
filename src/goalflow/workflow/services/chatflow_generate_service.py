from goalflow.model.wf_message import Message
from goalflow.service.message_service import MessageService
from goalflow.workflow.base_workflow import BaseWorkflow
from goalflow.state import GenericState, BaseState
import uuid
import os
from goalflow.workflow.chunk_processor.chatflow_stream_processor import ChatflowStreamProcessor
from goalflow.errors import WorkflowError
import traceback
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Dict, Any, cast
from goalflow.infra.redis_manager import RedisClusterManager
from goalflow.workflow.stream.types import *
import sys
from goalflow.tool.utils import VariableResolver
from goalflow.utils import ChatCompletionRequestCache
from goalflow.workflow_types import InterruptHook
from langchain_core.runnables.config import RunnableConfig
from goalflow.constants import (
    STREAM_OUTPUT_STOP_CHECK_INTERVAL,
    STATE_VARIABLE_TYPE_OUTPUT,
    CONST_REDIS_STOP_MARK_TIMEOUT,
    UPSTREAM_TRACE_ID_HEADER_NAME,
    UPSTREAM_SPAN_ID_HEADER_NAME
)

from goalflow.api.base_types import format_stream_chunk,ChatCompletionBlockingResponse

from goalflow.config import request_id as request_id_ctx, trace_info as trace_info_ctx

import tiktoken

from goalflow.infra.redis_manager import redis_client
import time

enc = tiktoken.get_encoding("o200k_base")

from goalflow.config import get_logger

logger = get_logger(__name__)


class ChatflowGenerateService:

    def __init__(self, workflow: BaseWorkflow[GenericState]):
        self.workflow = workflow
        self.stream_processor = ChatflowStreamProcessor(workflow)
        #  调试时候手动加载  环境变量  .env  TODO
        # self.app = create_app(os.getenv('FASTAPI_ENV', 'default'))

    @staticmethod
    def _is_stopped(key: str) -> bool:
        # TODO 从redis中获取stop标记
        stopped = redis_client.get(key)
        if stopped:
            return True
        return False

    @staticmethod
    def set_stopped(key: str):
        # TODO 把stop标记放到redis中
        redis_client.set(key, CONST_REDIS_STOP_MARK_TIMEOUT)

    # 流程开始时插入消息
    # 创建应用实例
    def insert_message(self, initial_state: BaseState):

        default_scene_type = os.getenv("WORKFLOW_SCENE_TYPE", "WANMOL") or "WANMOL"
        scene_type = initial_state.get("sys_scene_type", default_scene_type)
        new_message = MessageService.create(
            Message(
                conversation_id=initial_state["sys_conversation_id"],
                query=initial_state["sys_query"],
                inputs=initial_state["input_variables"],
                message_id=str(uuid.uuid4()),
                creator_id=initial_state["sys_user_id"],
                scene_type=scene_type
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
    def generate(self, initial_state: BaseState):
        request_id = initial_state.get("request_id")
        # 从 node_span_ids["trace_context"] 获取 trace_id 和 parent_span_id
        node_span_ids = initial_state.get("node_span_ids", {})
        trace_ctx = node_span_ids.get("trace_context", {}) if isinstance(node_span_ids, dict) else {}
        trace_id = trace_ctx.get("trace_id") if isinstance(trace_ctx, dict) else None
        span_id = trace_ctx.get("parent_span_id") if isinstance(trace_ctx, dict) else None
        user_id = initial_state.get("sys_user_id")
        request_id_ctx.set(request_id)
        trace_info_ctx.set({
            UPSTREAM_TRACE_ID_HEADER_NAME: trace_id,
            UPSTREAM_SPAN_ID_HEADER_NAME: span_id,
        })

        # 插入消息
        start_time = time.perf_counter()
        message = self.insert_message(initial_state)
        logger.info(f"insert message cost time: {time.perf_counter() - start_time}")

        message_id = message.id
        message_uuid = message.message_id
        if message_id is None or message_uuid is None:
            raise WorkflowError("插入消息失败")
        
        conversation_id = message.conversation_id
        initial_state["sys_conversation_id"] = conversation_id
        
        use_end_stream = initial_state.get("sys_use_end_stream",True)

        # Start streaming
        chunk_counter = 0
        
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0

        workflow_run_id = initial_state.get("sys_workflow_run_id")
        if not workflow_run_id:
            workflow_run_id = str(uuid.uuid4())
            initial_state["sys_workflow_run_id"] = workflow_run_id
            

        message_content = ""
        try:
            # Send start event
            yield format_stream_chunk(
                chunk_id=chunk_counter,
                event_type="workflow_started",
                data={"workflow_run_id": workflow_run_id, "status": "started"},
                task_id=workflow_run_id,
                message_id=message_uuid,
                conversation_id=conversation_id,
            )
            chunk_counter += 1

            runnable_config: RunnableConfig = {
                "recursion_limit": 500,
                "max_concurrency": 6,
                # use for log ,base on context copy
                "message_id": message_uuid,
                "conversation_id": conversation_id,
                "user_id": user_id,
                "request_id": request_id,
                # 兼容最新版本的langgraph， 如果基础镜像升级，langgraph升级到1.0以上，需要添加metadata字段，
                # 否则structlog日志输出无法自动追加message_id, conversation_id, user_id
                "metadata":{
                    "message_id": message_uuid,
                    "conversation_id": conversation_id,
                    "user_id": user_id,
                },
                UPSTREAM_TRACE_ID_HEADER_NAME: trace_id,
                UPSTREAM_SPAN_ID_HEADER_NAME: span_id
            }
            stream_method = self.workflow.stream
            # human in the loop 恢复执行
            hitl_review_id = initial_state.get("hitl_review_id")
            if hitl_review_id:
                logger.info(f"human in the loop resume , hitl_review_id: {hitl_review_id}")
                stream_method = self.workflow.resume
                config = {
                    "configurable":{
                        "thread_id" : initial_state["rt_thread_id"]
                    }
                }
                runnable_config.update(config)
                
            # {"recursion_limit": 500,"max_concurrency":10}
            # Execute workflow with streaming
            for stream_event in self.stream_processor.process(
                stream_method(
                    initial_state, 
                    runnable_config,
                    stream_mode=[
                        LANGGRAPH_STREAM_MODE_UPDATES, 
                        LANGGRAPH_STREAM_MODE_MESSAGES, 
                        LANGGRAPH_STREAM_MODE_CUSTOM
                    ]
                ),
                use_end_stream
            ):
                
                chunk_counter += 1

                # 每输出10个chunk进行stop检查，否则检查太频繁对性能有一定的影响（占用io资源）
                use_check_stop = chunk_counter % STREAM_OUTPUT_STOP_CHECK_INTERVAL == 0

                stopped_cache_key = f"generate_task_stopped:{workflow_run_id}"
                
                use_check_stop = (use_check_stop  or 
                    (
                        not isinstance(stream_event, NodeRunStreamChunkEvent) 
                         and not isinstance(stream_event, ProxyStreamDataChunk)
                    )
                )

                if use_check_stop and self._is_stopped(stopped_cache_key):
                    message_content="stop"
                    yield format_stream_chunk(
                        task_id=workflow_run_id,
                        chunk_id=chunk_counter,
                        message_id=message_uuid,
                        conversation_id=conversation_id,
                        event_type="stop",
                        data={},
                        workflow_run_id=workflow_run_id,
                    )
                    break
                
                if isinstance(stream_event, ProxyStreamDataChunk):
                    stream_event = cast(ProxyStreamDataChunk, stream_event)
                    
                    yield f"data: {stream_event.data}\n\n"

                if isinstance(stream_event, NodeRunSucceededEvent):
                    stream_event = cast(NodeRunSucceededEvent, stream_event)
                    node_id = stream_event.node_id
                    node_data = stream_event.node_data
                    node_type = stream_event.node_type
                    outputs = stream_event.outputs
                    data = node_data
                    # data["outputs"] = outputs

                    if node_type == WfNodeType.ANSWER.value:
                        message_content = VariableResolver.resolve_value_selector(
                            [node_id, "answer"], outputs
                        )

                    #if node_type == WfNodeType.END.value:
                    #    if "outputs" in outputs:
                    #        outputs = outputs["outputs"]
                    #    message_content = json.dumps(outputs)

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
                        message_id=message_uuid,
                        conversation_id=conversation_id,
                        # chunk_counter=chunk_counter,
                        event_type="node_finished",
                        data=outputs,
                        workflow_run_id=workflow_run_id,
                    )
                elif isinstance(stream_event, NodeRunStreamChunkEvent):
                    stream_event = cast(NodeRunStreamChunkEvent, stream_event)
                    node_id = stream_event.node_id
                    # chunk_content = stream_event.chunk_content
                    metadata = stream_event.metadata

                    if metadata is None:
                        event_type = "message"
                        completion_tokens += 1
                    else:
                        event_type = "message_end"

                    # 兼容gpt相关模型
                    if metadata is not None and "usage" in metadata and metadata["usage"].get("prompt_tokens") == 0:
                        metadata["usage"]["completion_tokens"] = completion_tokens
                        sys_query = initial_state["sys_query"]
                        prompt_tokens = len(enc.encode(sys_query))
                        metadata["usage"]["prompt_tokens"] = prompt_tokens
                        total_tokens = prompt_tokens + completion_tokens
                        metadata["usage"]["total_tokens"] = total_tokens

                    msg_chunk = format_stream_chunk(
                        # chunk_counter=chunk_counter,
                        task_id=workflow_run_id,
                        chunk_id=node_id,
                        message_id=message_uuid,
                        conversation_id=conversation_id,
                        event_type=event_type,
                        data={"workflow_run_id": workflow_run_id},
                        answer=stream_event.chunk_content,
                        workflow_run_id=workflow_run_id,
                        metadata=metadata,
                    )

                    # TODO 调试,线上环境关闭
                    # logger.info(f"stream chunk: {msg_chunk}")

                    yield msg_chunk
                elif isinstance(stream_event, NodeRunInterruptEvent):
                    stream_event = cast(NodeRunInterruptEvent,stream_event)
                    message_content="interrupt"
                    chunk_counter += 1
                    yield format_stream_chunk(
                        task_id=workflow_run_id,
                        chunk_id=chunk_counter,
                        message_id=message_uuid,
                        conversation_id=conversation_id,
                        event_type="interrupt",
                        data=stream_event.outputs,
                        workflow_run_id=workflow_run_id,
                    )
                    
                elif isinstance(stream_event, NodeRunControlEvent):
                    stream_event = cast(NodeRunControlEvent,stream_event)
                    message_content="control"
                    chunk_counter += 1
                    yield format_stream_chunk(
                        task_id=workflow_run_id,
                        chunk_id=chunk_counter,
                        message_id=message_uuid,
                        conversation_id=conversation_id,
                        event_type="control",
                        data=stream_event.outputs,
                        workflow_run_id=workflow_run_id,
                    )

            # Send completion event
            yield format_stream_chunk(
                chunk_id=chunk_counter + 1,
                event_type="workflow_finished",
                data={"workflow_run_id": workflow_run_id, "status": "completed"},
                task_id=workflow_run_id,
                message_id=message_uuid,
                conversation_id=conversation_id,
            )

        except WorkflowError as e:
            #traceback.print_exc()
            logger.error(f"WorkflowError_{e}", exc_info=True, message_id=message_uuid, user_id=user_id)
            
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
                message_id=message_uuid,
                conversation_id=conversation_id,
            )
        except Exception as e:
            #traceback.print_exc()
            logger.error(f"UnknownError_{e}", exc_info=True, message_id=message_uuid, user_id=user_id)
            
            yield format_stream_chunk(
                chunk_id=chunk_counter + 1,
                event_type="error",
                data={
                    #"error": str(e),
                    "error_type": "UnknownError",
                    "workflow_run_id": workflow_run_id,
                },
                message=str(e),
                task_id=workflow_run_id,
                message_id=message_uuid,
                conversation_id=conversation_id,
            )
        finally:
            self.clear_resource(initial_state)

        self.update_message(initial_state, answer=message_content, mid=message_id)

        # self.stream_processor.process(init_state)

    # 非流式执行
    def execute(self, initial_state: BaseState):
        request_id = initial_state.get("request_id")
        user_id = initial_state.get("sys_user_id")
        request_id_ctx.set(request_id)

        # 插入消息
        start_time = time.perf_counter()
        message = self.insert_message(initial_state)
        logger.info(f"insert message cost time: {time.perf_counter() - start_time}")

        message_id = message.id
        message_uuid = message.message_id
        if message_id is None or message_uuid is None:
            raise WorkflowError("插入消息失败")
        
        conversation_id = message.conversation_id
        initial_state["sys_conversation_id"] = conversation_id

        workflow_run_id = initial_state.get("sys_workflow_run_id")
        if not workflow_run_id:
            workflow_run_id = str(uuid.uuid4())
            initial_state["sys_workflow_run_id"] = workflow_run_id
            
        try:
            runnable_config: RunnableConfig = {
                "recursion_limit": 500,
                "max_concurrency": 6,
                # use for log ,base on context cop
                "message_id": message_uuid,
                "conversation_id": conversation_id,
                "user_id": user_id,
                "request_id": request_id
            }
            result = self.workflow.execute(initial_state=initial_state, config=runnable_config)

            output = result.get(STATE_VARIABLE_TYPE_OUTPUT, {})

            answer = ""

            # 如果chatflow中配置了多个answer节点，一般只有一个answer最后会被执行
            for var_name, value in output.items():
                if var_name.endswith("_answer"):
                    answer = value
                    break

            logger.info(f"workflow execute result: {result}")

            response = ChatCompletionBlockingResponse(
                id=message_uuid,
                message_id=message_uuid,
                conversation_id=conversation_id,
                task_id=workflow_run_id,
                answer=answer,
            )
            return response
        except Exception as e:
            logger.error(f"workflow_execute_error_{e}", exc_info=True, message_id=message_uuid, user_id=user_id)
            raise e
        finally:
            self.clear_resource(initial_state)
            
    def clear_resource(self, initial_state: BaseState):
        """清除资源"""
        
        # 如果是openai格式请求,则删除redis中的历史消息
        ChatCompletionRequestCache.delete_request_cache(
                state=initial_state,
        )
        
    def bind_interrupt_hook(self, interrupt_hook: InterruptHook):
        self.interrupt_hook = interrupt_hook


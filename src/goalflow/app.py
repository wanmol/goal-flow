"""
FastAPI web service for goalflow.
Provides streaming and non-streaming endpoints for workflow execution.
"""

import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, Any, List, Optional

import requests

from dotenv import load_dotenv

import os

import uvicorn
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from langchain_community.chat_models import ChatTongyi

from goalflow.utils import ChatCompletionRequestCache
from goalflow.tool.oss_client import OSSClient

from pydantic import BaseModel, Field

from goalflow.errors import WorkflowError, StateValidationError
from goalflow.prompts import SUGGESTED_QUESTIONS_AFTER_ANSWER_INSTRUCTION_PROMPT, suggest_q_tpl_map
from goalflow.service.message_service import MessageService
from goalflow.state import BaseState

# from storage.mysql.message_storage import MessageStorage

from goalflow.infra.redis_manager import RedisClusterManager
from goalflow.infra.database import Database

from goalflow.workflow.services.chatflow_generate_service import ChatflowGenerateService
from goalflow.workflow.services.workflow_generate_service import WorkflowGenerateService

from goalflow.workflow.services.data_adapter.openai_data_adapter import OpenAIDataAdapter

from goalflow.api.auth_validator import validate_token_and_get_wf

from goalflow.api.base_types import(
    ChatCompletionRequestMessagePart, 
    ChatCompletionRequestMessageRole,
    ChatCompletionRequest, 
    ImageGenerationRequest, 
    ImageGenerationResponse
)

import traceback

from goalflow.workflow.base_workflow import BaseWorkflow

# from sse_starlette.sse import EventSourceResponse
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR, HTTP_403_FORBIDDEN

# Import HITL API router
from goalflow.api.hitl_api import router as hitl_router

# Import Report API router
from goalflow.api.report_api import router as report_router

# from starlette.responses import StreamingResponse
from goalflow.config import (
    get_logger,
    trace_info as trace_info_ctx,
    request_id as request_id_ctx,
)
from goalflow.constants import (
    WF_REQUEST_ID_HEADER_NAME,
    UPSTREAM_TRACE_ID_HEADER_NAME,
    UPSTREAM_SPAN_ID_HEADER_NAME,
    RESPONSE_MODE_STREAMING,
    RESPONSE_MODE_BLOCKING,
    WF_TYPE_WORKFLOW,
    WF_TYPE_CHATFLOW,
    CHAT_COMPLETION_REQUEST_REDIS_KEY_FMT,
)

from goalflow.tool.env_loader import load_env

from goalflow.monitor.memory_monitor import init_memory_monitor,get_memory_monitor
from goalflow.monitor.memory_middleware import MemoryMonitoringMiddleware
from goalflow.monitor.memory_routes import router as memory_router

from goalflow.monitor.memory_routes_accurate import router as memory_router_accurate

logger = get_logger(__name__)

# Memory monitoring is a diagnostic tool that spawns background threads, snapshots
# on every request, and exposes unauthenticated diagnostic routes. It is opt-in and
# OFF by default so the framework doesn't instrument every request or run heap walks
# in production. Enable with MEMORY_MONITOR_ENABLED=true.
MEMORY_MONITOR_ENABLED = os.getenv("MEMORY_MONITOR_ENABLED", "false").strip().lower() in (
    "1", "true", "yes", "on",
)


# Pydantic models for request/response
class WorkflowInput(BaseModel):
    """Input model for workflow execution."""

    query: str = Field(default="", description="用户查询内容")
    conversation_id: Optional[str] = Field(default=None, description="会话ID")
    user: str = Field(..., description="用户ID")

    response_mode: Optional[str] = Field(default="streaming", description="响应模式")
    
    scene_type: Optional[str] = Field(default=None, description="场景类型")

    sys_app_id: str = Field(default="goalflow-workflow", description="应用ID")
    sys_workflow_id: str = Field(default="1745215322322", description="工作流ID")

    files: Optional[List[Dict]] = Field(default=None, description="上传文件")
    inputs: Dict[str, Any] = Field(default_factory=dict, description="输入变量")
    

class StreamChunk(BaseModel):
    """Streaming response chunk model."""

    chunk_id: str = Field(..., description="分块ID")
    type: str = Field(..., description="分块类型: 'message'|'update'|'error'|'done'")
    data: Dict[str, Any] = Field(..., description="分块数据")
    timestamp: str = Field(..., description="时间戳")
    
    
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load environment variables
    load_env()

    # Initialize the MySQL connection pool
    Database.init()
    # Initialize the Redis connection pool (optional)
    RedisClusterManager.init_cluster()

    # Load middleware checks
    middle_health_check()

    # Initialize memory monitoring (opt-in; see MEMORY_MONITOR_ENABLED).
    monitor = None
    leak_check_thread = None
    if MEMORY_MONITOR_ENABLED:
        monitor = init_memory_monitor("MyFastAPIApp")

        # Start the background monitoring thread (collects once every 10 seconds)
        monitor.start_background_monitoring(interval=10)

        # Periodically check for memory leaks (every 5 minutes)
        import threading

        leak_stop_event = threading.Event()

        def periodic_leak_check():
            while not leak_stop_event.is_set():
                try:
                    report = monitor.analyze_leak()
                    if report.get("leak_detected"):
                        # An alert can be sent here, e.g. email, Slack, etc.
                        logger.warning("memory leak detected", report=report)
                except Exception as e:
                    logger.error("leak check failed", error=str(e))

                # Check once every 5 minutes (interruptible on shutdown)
                leak_stop_event.wait(300)

        leak_check_thread = threading.Thread(
            target=periodic_leak_check,
            daemon=True,
            name="LeakCheckThread"
        )
        leak_check_thread.start()
    else:
        logger.info("memory monitoring disabled (set MEMORY_MONITOR_ENABLED=true to enable)")

    # app.state.executor = executor

    try:
        yield
    finally:
        logger.info("释放资源...")
        # Synchronous cleanup operations
        Database.close()
        RedisClusterManager.close()
        if monitor is not None:
            leak_stop_event.set()
            monitor.stop_monitoring()


# FastAPI app initialization
app = FastAPI(
    title="goalflow workflow API",
    description="兼容Dify等常用协议的LangGraph工作流执行服务",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware.
# Origins come from the CORS_ALLOW_ORIGINS env var (comma-separated); default is
# empty (no cross-origin access) so a misconfigured deployment fails closed.
# A wildcard "*" MUST NOT be combined with allow_credentials=True — Starlette would
# then reflect any Origin and return Access-Control-Allow-Credentials: true, letting
# any site make credentialed cross-origin reads. So credentials are only enabled
# when an explicit origin allow-list is configured.
_cors_env = os.getenv("CORS_ALLOW_ORIGINS", "").strip()
_cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()]
_cors_allow_wildcard = "*" in _cors_origins or _cors_env == "*"

if _cors_allow_wildcard:
    logger.warning(
        "CORS is configured with a wildcard origin; credentials are disabled. "
        "Set CORS_ALLOW_ORIGINS to an explicit comma-separated allow-list to enable credentials."
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Add memory monitoring middleware (opt-in; see MEMORY_MONITOR_ENABLED)
if MEMORY_MONITOR_ENABLED:
    app.add_middleware(MemoryMonitoringMiddleware)

# Register HITL API router
app.include_router(hitl_router)

# Register Report API router
app.include_router(report_router)

# Register memory monitoring routes (opt-in; these are diagnostic and unauthenticated)
if MEMORY_MONITOR_ENABLED:
    app.include_router(memory_router)
    app.include_router(memory_router_accurate)

def prepare_initial_state(workflow_input: WorkflowInput) -> BaseState:
    """Prepare initial state from input."""
    workflow_run_id = str(uuid.uuid4())

    # Convert input to state format
    initial_state = {
        "sys_query": workflow_input.query,
        "sys_user_id": workflow_input.user,
        "sys_app_id": workflow_input.sys_app_id,
        "sys_workflow_id": workflow_input.sys_workflow_id,
        "sys_workflow_run_id": workflow_run_id,
        "sys_conversation_id": workflow_input.conversation_id,
        "sys_scene_type": workflow_input.scene_type,
        "sys_files": workflow_input.files,
        "input_variables": workflow_input.inputs,
        "sys_use_end_stream": workflow_input.inputs.get("use_end_stream", True),
    }

    return initial_state


def prepare_state_from_chat_completion_request(chat_completion_request: ChatCompletionRequest) -> BaseState:
    """Prepare initial state from input."""
    workflow_run_id = str(uuid.uuid4())

    message_list = chat_completion_request.dialogue
    if not message_list:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"message param is empty",
        )
        
    last_message : ChatCompletionRequestMessagePart = message_list[-1]
    
    if last_message.role != "user":
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"last message role must be user",
        )
    
    query = last_message.content
    # Convert input to state format
    initial_state = {
        "sys_query": query,
        "sys_user_id": "OPENAPI",
        "sys_workflow_run_id": workflow_run_id,
        "sys_scene_type": "OPENAPI",
        "sys_openai_param": True,
        "sys_conversation_id": None,
        #TODO  hardcoded for now; need to consider in what form it will be passed in
        "input_variables": {"networkFlag":1,"deepThinkFlag":1}
    }

    return initial_state


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"message": "goalflow API", "status": "running", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    """Detailed health check."""
    
    monitor = get_memory_monitor()
    current = monitor.get_current_stats()
    
    try:
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "memory_mb": current['rss_mb'],
            "memory_percent": current['percent'],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Service unhealthy: {str(e)}")


# Middleware check; currently mysql and redis
@app.get("/middle_health")
def middle_health_check():
    from goalflow.infra.database import Database

    health_check_db = "failed"
    health_check_cache = "failed"

    try:
        if RedisClusterManager.is_enabled():
            health_check_cache = "successful"
        if Database.health_check():
            health_check_db = "successful"
        logger.info("The database loaded : " + health_check_db)
        logger.info("The cache loaded : " + health_check_cache)
        return {
            "status": "healthy",
            "middle_health": {
                "health_check_db": health_check_db,
                "health_check_cache": health_check_cache,
            },
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"middle unhealthy: {str(e)}",
        )


@app.post("/v1/workflows/run")
def execute_workflow(
    request: Request,
    workflow_input: WorkflowInput,
    workflow: BaseWorkflow = Depends(validate_token_and_get_wf),
):
    """
    Execute workflow synchronously , support streaming response and blocking response.

    Args:
        workflow_input: Workflow input parameters

    Returns:
        WorkflowOutput: Execution result
    """

    wf_type = workflow.workflow_type
    if wf_type != WF_TYPE_WORKFLOW:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Workflow type must be {WF_TYPE_WORKFLOW}",
        )

    request_id = request.headers.get(WF_REQUEST_ID_HEADER_NAME)
    if request_id is None:
        request_id = str(uuid.uuid4())

    # use without langgraph execution environment
    request_id_ctx.set(request_id)

    # trace_id, span_id passed in from the upstream call
    upstream_trace_id = request.headers.get(UPSTREAM_TRACE_ID_HEADER_NAME)
    upstream_span_id = request.headers.get(UPSTREAM_SPAN_ID_HEADER_NAME)
    if upstream_trace_id and upstream_span_id:
        trace_info_ctx.set(
            {
                UPSTREAM_TRACE_ID_HEADER_NAME: upstream_trace_id,
                UPSTREAM_SPAN_ID_HEADER_NAME: upstream_span_id,
            }
        )

    workflow_run_id = str(uuid.uuid4())

    user_id = workflow_input.user

    # Construct the desensitized log parameters
    # log_input = workflow_input.model_dump(exclude={"inputs": {"financial_data"}})
    # logger.info("workflow request start", request_param=log_input)
    logger.info("workflow request start", request_param=workflow_input)

    # workflow's model output mode is non-streaming output
    response_mode = workflow_input.response_mode or RESPONSE_MODE_BLOCKING
    # Prepare initial state
    initial_state = prepare_initial_state(workflow_input)
    initial_state["sys_workflow_run_id"] = workflow_run_id

    # use with langgraph execution environment through var_child_runnable_config
    initial_state["request_id"] = request_id
    # Store trace_id and parent_span_id in node_span_ids["trace_context"]
    if "node_span_ids" not in initial_state:
        initial_state["node_span_ids"] = {}
    if "trace_context" not in initial_state["node_span_ids"]:
        initial_state["node_span_ids"]["trace_context"] = {}
    if upstream_trace_id:
        initial_state["node_span_ids"]["trace_context"]["trace_id"] = upstream_trace_id
    if upstream_span_id:
        initial_state["node_span_ids"]["trace_context"]["parent_span_id"] = upstream_span_id

    workflow_service = WorkflowGenerateService(workflow)
    if response_mode == RESPONSE_MODE_STREAMING:
        return StreamingResponse(
            workflow_service.generate(initial_state),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Workflow-Run-ID": workflow_run_id,
            },
        )
    elif response_mode == RESPONSE_MODE_BLOCKING:
        try:
            # Execute workflow
            result = workflow_service.execute(initial_state)
            return result

        except Exception as e:
            # logger.error(f"UnknownError_{e}", exc_info=True, user_id=user_id)
            status_code = _get_status_code_by_error_msg(str(e))
            raise HTTPException(
                status_code=status_code, detail=f"Workflow execution failed: {str(e)}"
            )
    else:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unknown response mode: {response_mode}",
        )


@app.post("/v1/chat-messages/{task_id}/stop")
def stop_workflow(task_id: str):
    """
    Stop workflow execution.

    Args:
        workflow_run_id: ID of the workflow run to stop
    """
    stopped_cache_key = _generate_stopped_cache_key(task_id)

    ChatflowGenerateService.set_stopped(stopped_cache_key)
    return {"success": True, "message": "Workflow stopped successfully"}


def _generate_stopped_cache_key(workflow_run_id: str) -> str:
    """
    Generate stopped cache key
    :param workflow_run_id: workflow_run_id id
    :return:
    """
    return f"generate_task_stopped:{workflow_run_id}"


# import concurrent.futures
# executor = concurrent.futures.ThreadPoolExecutor(max_workers=8)


@app.post("/v1/chat-messages")
def chat_messages(
    request: Request,
    workflow_input: WorkflowInput,
    workflow: BaseWorkflow = Depends(validate_token_and_get_wf),
):
    """
    Execute chatflow , support streaming response and blocking response.

    Args:
        workflow_input: Workflow input parameters
        workflow: workflow instance dependency injection
        request: Request

    Returns:
        StreamingResponse: Server-sent events stream
    """

    wf_type = workflow.workflow_type
    if wf_type != WF_TYPE_CHATFLOW:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Workflow type must be {WF_TYPE_CHATFLOW}",
        )

    request_id = request.headers.get(WF_REQUEST_ID_HEADER_NAME)
    if request_id is None:
        request_id = str(uuid.uuid4())

    # use without langgraph execution environment
    request_id_ctx.set(request_id)

    # trace_id, span_id passed in from the upstream call
    upstream_trace_id = request.headers.get(UPSTREAM_TRACE_ID_HEADER_NAME)
    upstream_span_id = request.headers.get(UPSTREAM_SPAN_ID_HEADER_NAME)

    logger.info(
        "upstream_trace_info",
        upstream_trace_id=upstream_trace_id,
        upstream_span_id=upstream_span_id,
    )

    if upstream_trace_id and upstream_span_id:
        trace_info_ctx.set(
            {
                UPSTREAM_TRACE_ID_HEADER_NAME: upstream_trace_id,
                UPSTREAM_SPAN_ID_HEADER_NAME: upstream_span_id,
            }
        )

    workflow_run_id = str(uuid.uuid4())

    # Construct the desensitized log parameters
    # log_input = workflow_input.model_dump(exclude={"inputs": {"financial_data"}})
    # logger.info("chatflow request start", request_param=log_input)
    logger.info("chatflow request start", request_param=workflow_input)

    response_mode = workflow_input.response_mode or RESPONSE_MODE_STREAMING
    # Prepare initial state
    initial_state = prepare_initial_state(workflow_input)
    initial_state["sys_workflow_run_id"] = workflow_run_id

    # use with langgraph execution environment through var_child_runnable_config
    initial_state["request_id"] = request_id
    # Store trace_id and parent_span_id in node_span_ids["trace_context"]
    if "node_span_ids" not in initial_state:
        initial_state["node_span_ids"] = {}
    if "trace_context" not in initial_state["node_span_ids"]:
        initial_state["node_span_ids"]["trace_context"] = {}
    if upstream_trace_id:
        initial_state["node_span_ids"]["trace_context"]["trace_id"] = upstream_trace_id
    if upstream_span_id:
        initial_state["node_span_ids"]["trace_context"]["parent_span_id"] = upstream_span_id

    chat_service = ChatflowGenerateService(workflow)
    if response_mode == RESPONSE_MODE_STREAMING:
        # future = executor.submit(stream_service.generate, initial_state)
        return StreamingResponse(
            chat_service.generate(initial_state),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Workflow-Run-ID": workflow_run_id,
            },
        )
    elif response_mode == RESPONSE_MODE_BLOCKING:
        try:
            # Execute workflow
            result = chat_service.execute(initial_state)
            return result

        except Exception as e:
            # logger.error(f"UnknownError_{e}", exc_info=True, user_id=user_id)
            status_code = _get_status_code_by_error_msg(str(e))
            raise HTTPException(
                status_code=status_code, detail=f"Workflow execution failed: {str(e)}"
            )
    else:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unknown response mode: {response_mode}",
        )


# ugly fix
def _get_status_code_by_error_msg(error_msg: str) -> int:
    """Get status code by error message."""
    if "status_code: 4" in error_msg:
        return HTTP_403_FORBIDDEN
    else:
        return HTTP_500_INTERNAL_SERVER_ERROR


def format_stream_chunk(
    chunk_id: int, chunk_type: str, data: Dict[str, Any], workflow_run_id: str
) -> str:
    """Format a streaming chunk as SSE format."""
    chunk = StreamChunk(
        chunk_id=str(chunk_id),
        type=chunk_type,
        data=data,
        timestamp=datetime.utcnow().isoformat(),
    )

    # Format as Server-Sent Events
    return f"data: {chunk.model_dump_json()}\n\n"



# Exception handlers
@app.exception_handler(WorkflowError)
def workflow_error_handler(request, exc: WorkflowError):
    """Handle workflow-specific errors."""
    return JSONResponse(
        status_code=400,
        content={"error": "WorkflowError", "message": str(exc)},
    )


@app.exception_handler(StateValidationError)
def state_validation_error_handler(request, exc: StateValidationError):
    """Handle state validation errors."""
    return JSONResponse(
        status_code=400,
        content={"error": "StateValidationError", "message": str(exc)},
    )


def _extract_json_from_markdown(content: str) -> str:
    """
    Extract JSON content from a markdown code block
    Supported formats: ```json\n...\n``` or ```\n...\n``` or plain JSON
    """
    content = content.strip()

    # Check whether there is a markdown code block marker
    if content.startswith("```"):
        # Remove the leading ```json or ```
        lines = content.split("\n")
        # Remove the code block marker on the first line
        if lines[0].startswith("```"):
            lines = lines[1:]
        # Remove the code block marker on the last line
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines).strip()

    return content


@app.post("/v1/messages/{message_id}/suggested")
def get_message_suggested(user: str, message_id: str,request_body:dict={}):
    """
    Get the list of suggested questions for the next round
    """
    if not user:
        raise ValueError("user cannot be None")
    questions = []
    
    request_body = request_body or {}
    tpl_id = request_body.get("tpl_id", "")
    prompt_template:str = suggest_q_tpl_map.get(tpl_id, "")

    if tpl_id and not prompt_template:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown tpl_id: {tpl_id}",
        )
    
    message = MessageService.get_by_message_id(message_id)
    if message is not None:
        histories = MessageService.get_llm_template_by_conversation_id(
            message.conversation_id
        )
        histories = histories[::-1]
        _len = min(len(histories), 3)
        histories = histories[-_len:] or []

        prompt = ""
        client = ChatTongyi(
                api_key=os.environ['DASHSCOPE_KEY'],
                base_url=os.environ['DASHSCOPE_ENDPOINT'],
                model="deepseek-v4-flash",
                model_kwargs={"max_tokens": 256, "temperature": 0},
                streaming=False,
        )
        
        if prompt_template:
            request_body["histories"] = histories
            prompt = prompt_template.format(**request_body)
            
        elif len(histories) > 0:
            prompt = f"{histories}\n{SUGGESTED_QUESTIONS_AFTER_ANSWER_INSTRUCTION_PROMPT}\nquestions:\n"
            
        logger.info(f"suggest_question_prompt: {prompt}")
        
        if prompt:
            response = client.invoke(prompt)
            if response and response.content is not None:
                questions = json.loads(response.content)

    return {"result": "success", "data": questions}


@app.get("/v1/messages/{message_id}/suggested")
def get_message_suggested2(user: str, message_id: str):
    """
    Get the list of suggested questions for the next round
    """
    if not user:
        raise ValueError("user cannot be None")
    questions = []

    message = MessageService.get_by_message_id(message_id)
    if message is not None:
        history = MessageService.get_llm_template_by_conversation_id(
            message.conversation_id
        )
        history = history[::-1]
        _len = min(len(history), 3)
        history = history[-_len:]

        if len(history) > 0:
            prompt_template = f"{history}\n{SUGGESTED_QUESTIONS_AFTER_ANSWER_INSTRUCTION_PROMPT}\nquestions:\n"
            client = ChatTongyi(
                api_key=os.environ['DASHSCOPE_KEY'],
                base_url=os.environ['DASHSCOPE_ENDPOINT'],
                model="deepseek-v4-flash",
                model_kwargs={"max_tokens": 256, "temperature": 0},
                streaming=False,
            )
            response = client.invoke(prompt_template)
            if response and response.content is not None:
                # Clean up the markdown code block formatting, then parse JSON
                cleaned_content = _extract_json_from_markdown(response.content)
                questions = json.loads(cleaned_content)
    return {"result": "success", "data": questions}

@app.get("/memory-intensive")
async def memory_intensive():
    """
    Memory-intensive operation, used for testing monitoring
    """
    monitor = get_memory_monitor()

    # Record the start of the operation
    monitor.snapshot("memory_intensive_start")

    # Create a large number of objects
    data = []
    for i in range(100000):
        data.append(f"string_{i}" * 10)

    # Record the intermediate state of the operation
    monitor.snapshot("memory_intensive_middle")

    # Clean up part of the data
    del data[50000:]

    # Record the end of the operation
    monitor.snapshot("memory_intensive_end")

    return {
        "message": "内存密集型操作完成",
        "remaining_items": len(data)
    }
 
def main():
    """Console-script entry point (goalflow-server)."""
    uvicorn.run("goalflow.app:app", host="0.0.0.0", port=8000, reload=True, log_level="info")


if __name__ == "__main__":
    # Run the server
    main()

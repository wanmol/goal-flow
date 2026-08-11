from enum import Enum
from typing import Literal
import sys

class WfNodeType(Enum):
    """
    Wf Node Type in Workflow or Chatflow
    """
    START               = "start"
    END                 = "end"
    LLM                 = "llm"
    ANSWER              = "answer"
    CODE                = "code"
    HTTP_REQUEST        = "http-request"
    IF_ELSE             = "if-else"
    KNOWLEDGE_RETRIEVAL = "knowledge-retrieval" 
    ITERATION           = "iteration" 
    ITERATION_START     = "iteration-start"
    QUESTION_CLASSIFIER = "question-classifier"
    VARIABLE_AGGREGATOR = "variable-aggregator"
    ASSIGNER            = "assigner"
    TEMPLATE_TRANSFORM  = "template-transform"
    LOOP                = "loop"
    LOOP_START          = "loop-start"
    LOOP_END            = "loop-end"
    TOOL                = "tool"
    AGENT               = "agent"
    DOCUMENT_EXTRACTOR  = "document-extractor"
    
    #===============below is custom type==============
    # Convert natural language to SQL and run the database query
    NL_DB_QUERY         = "nl_db_query"
    
    @staticmethod
    def value_of(value):
        for member in WfNodeType:
            if member.value == value:
                return member
        raise ValueError(f"No matching enum found for value '{value}'")

class DefaultValueType(Enum):
    STRING = "string"
    NUMBER = "number"
    OBJECT = "object"
    ARRAY_NUMBER = "array[number]"
    ARRAY_STRING = "array[string]"
    ARRAY_OBJECT = "array[object]"
    ARRAY_FILES = "array[file]"
    
    @staticmethod
    def value_of(value):
        for member in DefaultValueType:
            if member.value == value:
                return member
        raise ValueError(f"No matching enum found for value '{value}'")
    
class ErrorStrategy(Enum):
    FAIL_BRANCH   = "fail-branch"
    DEFAULT_VALUE = "default-value"
    
    @staticmethod
    def value_of(value):
        for member in ErrorStrategy:
            if member.value == value:
                return member
        raise ValueError(f"No matching enum found for value '{value}'")
    

class AssignerInputType(Enum):
    VARIABLE = "variable"
    CONSTANT = "constant"
    
    @staticmethod
    def value_of(value):
        for member in AssignerInputType:
            if member.value == value:
                return member
        raise ValueError(f"No matching enum found for value '{value}'")
    
class AssignerOperation(Enum):
    OVER_WRITE = "over-write"
    CLEAR = "clear"
    APPEND = "append"
    EXTEND = "extend"
    SET = "set"
    ADD = "+="
    SUBTRACT = "-="
    MULTIPLY = "*="
    DIVIDE = "/="
    REMOVE_FIRST = "remove-first"
    REMOVE_LAST = "remove-last"
    
    @staticmethod
    def value_of(value):
        for member in AssignerOperation:
            if member.value == value:
                return member
        raise ValueError(f"No matching enum found for value '{value}'")
    
#from enum import StrEnum
# error handle on iteration and loop node
class ErrorHandleMode(Enum):
    TERMINATED = "terminated"
    CONTINUE_ON_ERROR = "continue-on-error"
    REMOVE_ABNORMAL_OUTPUT = "remove-abnormal-output"
    
    @staticmethod
    def value_of(value):
        for member in ErrorHandleMode:
            if member.value == value:
                return member
        raise ValueError(f"No matching enum found for value '{value}'")
    
class FileType(Enum):
    IMAGE = "image"
    DOCUMENT = "document"
    AUDIO = "audio"
    VIDEO = "video"
    CUSTOM = "custom"

    @staticmethod
    def value_of(value):
        for member in FileType:
            if member.value == value:
                return member
        raise ValueError(f"No matching enum found for value '{value}'")

"""    
class FileTransferMethod(Enum):
    REMOTE_URL = "remote_url"
    LOCAL_FILE = "local_file"
    TOOL_FILE = "tool_file"

    @staticmethod
    def value_of(value):
        for member in FileTransferMethod:
            if member.value == value:
                return member
        raise ValueError(f"No matching enum found for value '{value}'")
"""

    
VariableEntityType = Literal["text-input","number","paragraph","select","external_data_tool","file","file-list"]
FileTransferMethod = Literal["remote_url","local_file","tool_file"]


STATE_VARIABLE_TYPE_INPUT = sys.intern("input_variables")
STATE_VARIABLE_TYPE_OUTPUT = sys.intern("output_variables")
STATE_VARIABLE_TYPE_CONVERSATION = sys.intern("conversation_variables")
STATE_VARIABLE_TYPE_ENVIRONMENT = sys.intern("environment_variables")

STATE_VARIABLE_TYPE = Literal[
    STATE_VARIABLE_TYPE_INPUT,
    STATE_VARIABLE_TYPE_OUTPUT,
    STATE_VARIABLE_TYPE_CONVERSATION,
    STATE_VARIABLE_TYPE_ENVIRONMENT
]

class PromptMessageRole(Enum):
    """
    Enum class for prompt message.
    """

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    
    @staticmethod
    def value_of(value):
        for member in PromptMessageRole:
            if member.value == value:
                return member
        raise ValueError(f"No matching enum found for value '{value}'")
    
class ToolProviderType(Enum):
    """
    Type of external component invoked by the Tool node
    """
    PLUGIN = "plugin"
    BUILT_IN = "builtin"
    WORKFLOW = "workflow"
    API = "api"
    APP = "app"
    DATASET_RETRIEVAL = "dataset-retrieval"
    MCP = "mcp"
    
    @staticmethod
    def value_of(value):
        for member in ToolProviderType:
            if member.value == value:
                return member
        raise ValueError(f"No matching enum found for value '{value}'")
    
    
class HummanApproveAction(Enum):
    """
    Enum class for human approve action.
    """

    APPROVE = "approve"
    REJECT = "reject"
    MODIFY = "modify"
    
    @staticmethod
    def value_of(value):
        for member in HummanApproveAction:
            if member.value == value:
                return member
        raise ValueError(f"No matching enum found for value '{value}'")


WF_TYPE_CHATFLOW = sys.intern("chatflow")
WF_TYPE_WORKFLOW = sys.intern("workflow")

RESPONSE_MODE_STREAMING = "streaming"
RESPONSE_MODE_BLOCKING = "blocking"

# Carries the request_id from the upstream call, to facilitate distributed tracing
WF_REQUEST_ID_HEADER_NAME = sys.intern("X-Request-Id")

UPSTREAM_TRACE_ID_HEADER_NAME = sys.intern("X-Trace-Id")

UPSTREAM_SPAN_ID_HEADER_NAME = sys.intern("X-Span-Id")

STREAM_OUTPUT_STOP_CHECK_INTERVAL = 10

THINK_START_TAG = "<think>"

THINK_END_TAG = "</think>"

THINKING_CONTENT_KEY = "reasoning_content"

# Set the expiration time for the stop marker in redis
CONST_REDIS_STOP_MARK_TIMEOUT = 60

CHAT_COMPLETION_REQUEST_REDIS_KEY_FMT = "chat_completion_request:{}"


class RedisKeyConstants:
    WORKFLOW_PREFIX_BY_CONVERSATION_ID = "workflow_variables:conversation_id:"
    MESSAGE_PREFIX_BY_CONVERSATION_ID = "message:conversation_id:"


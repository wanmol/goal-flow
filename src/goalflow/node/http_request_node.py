from goalflow.node.base import BaseNode, NodeOutput
from typing import Dict, Any, Optional, Literal
from pydantic import BaseModel
from goalflow.workflow_types import (
    HttpRequestBodyConfig,
    HttpNodeAuthorizationConfig,
    HttpNodeRetryConfig,
    HttpNodeTimeoutConfig,
)
from goalflow.state import GenericState
from goalflow.constants import WfNodeType
import requests
import json
import time
import re
from urllib.parse import urlencode
from langgraph.types import Command

from goalflow.tool.utils import VariableResolver

from goalflow.tool.httpclient.sse_client import SSEClient
from goalflow.tool.httpclient.sse_callback_list import get_callback_by_url
from functools import partial

from goalflow.config import get_logger

logger = get_logger(__name__)


class HttpRequestNode(BaseNode):
    """
    HTTP Request node for making external API calls.
    This node sends HTTP requests and processes responses.
    """

    url: str
    method: Literal[
        "get",
        "post",
        "put",
        "patch",
        "delete",
        "head",
        "options",
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "HEAD",
        "OPTIONS",
    ]
    headers: Dict[str, Any]
    body: Optional[HttpRequestBodyConfig] = None
    authorization: HttpNodeAuthorizationConfig
    params: Dict[str, Any]
    ssl_verify: Optional[bool] = True
    retry_config: Optional[HttpNodeRetryConfig] = None
    timeout_config: Optional[HttpNodeTimeoutConfig] = None

    # read only
    __node_type = WfNodeType.HTTP_REQUEST

    @property
    def node_type(self) -> WfNodeType:
        return self.__node_type

    def __init__(
        self,
        *,
        url: str,
        method: str,
        headers: Dict[str, str],
        body: Optional[HttpRequestBodyConfig],
        authorization: HttpNodeAuthorizationConfig,
        params: Dict[str, str],
        ssl_verify: bool = True,
        retry_config: Optional[HttpNodeRetryConfig] = None,
        timeout_config: Optional[HttpNodeTimeoutConfig] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.url = url
        self.method = method.upper()
        self.headers = headers or {}
        self.body = body
        self.authorization = authorization
        self.params = params or {}
        self.ssl_verify = ssl_verify
        self.retry_config = retry_config
        self.timeout_config = timeout_config
        
        self._data_preprocessing()
        
    def _data_preprocessing(self):
        if self.body and self.body.data:
            body_data = self.body.data
            if body_data and body_data != []:
                # 默认body_data只有一个元素
                value = body_data[0].value
                value = value.replace(u"\u00a0"," ")
                value = value.replace(u'\xa0', u' ')
                body_data[0].value = value

    def call(self, state: GenericState) -> NodeOutput:
        """
        Execute HTTP request with the given state.
        """

        try:
            # Resolve variables
            resolved_variables = self._resolve_variables(state)

            # Build request parameters
            request_url = self._process_template_string(
                self.url, resolved_variables, state
            )
            request_headers = self._build_headers(resolved_variables, state)
            request_params = self._build_params(resolved_variables, state)
            request_body = self._build_body(resolved_variables, state)
            logger.info(
                f"{self.formatted_name} node begin http request",
                request_url=request_url, 
                request_headers=request_headers, 
                request_params=request_params, 
                request_body=request_body, 
                node_id=self.formatted_name
            )
            
            request_info = {
                "url": request_url,
                "headers": request_headers,
                "params": request_params,
                "body": request_body,
            }
            
            #span:Span = self.start_trace()
            
            response_data = None
            if "Accept" in request_headers and request_headers["Accept"] == "text/event-stream":
                response_data = self._request_with_streaming(
                    request_url, request_headers, request_params, request_body
                )
            else:
                # Execute request with retry logic
                response_data = self._execute_request_with_retry(
                    request_url, request_headers, request_params, request_body
                )


            #if span:
            #    self.end_trace(span, request_info, response_data)

            logger.info(
                f"{self.formatted_name} node response_data: {response_data}", 
                node_id=self.formatted_name
            )

            
            # Update state with response
            update_vars = {}

            update_vars["status_code"] = response_data["status_code"]
            update_vars["body"] = response_data["body"]
            update_vars["headers"] = response_data["headers"]
            update_vars["size"] = response_data["size"]
            update_vars["time"] = response_data["time"]
            update_vars["request_url"] = request_url
            update_vars["request_body"] = request_body
            
            try:
                if "files" in response_data["body"]:
                    json_response = json.loads(response_data["body"])
                    if "files" in json_response and type(json_response["files"]) == list:
                        update_vars["files"] = json_response["files"]
            except json.JSONDecodeError:
               logger.error("response body is not json format")

            # If status is not 200, throw exception and enter exception handling mode
            # (1. Directly throw exception 2. Set default value 3. Exception branch)
            if response_data["status_code"] != 200:
                logger.info(
                    f"{self.formatted_name} node response_data: {response_data}"
                )
                #raise Exception(f"HTTP request failed with status code {response_data['status_code']}")

            update_data = VariableResolver.format_output(
                node_id=self.id, outputs=update_vars
            )

            return Command(
                update=update_data,
                goto=self.next_node_ids,
            )

        except Exception as e:
            logger.error("http request error", exc_info=True, node_id=self.formatted_name)
            return self._handle_error(state, e)

    def _resolve_variables(self, state: GenericState) -> Dict[str, Any]:
        """Resolve all variables referenced in the node configuration"""
        resolved = {}

        if self.variables:
            for var_config in self.variables:
                variable_name = var_config.variable
                value_selector = var_config.value_selector

                resolved_value = self._resolve_value_selector(value_selector, state)
                resolved[variable_name] = resolved_value

        return resolved

    def _resolve_value_selector(
        self, value_selector: list[str], state: GenericState
    ) -> Any:
        """Resolve a value selector to its actual value in the state"""
        if not value_selector or len(value_selector) != 2:
            return None

        node_id, variable_name = value_selector

        # Handle system variables
        if node_id == "sys":
            return state.get(f"sys_{variable_name}", None)

        # Handle output variables from other nodes
        output_vars = state.get("output_variables", {})
        node_var_key = f"{node_id}_{variable_name}"

        if node_var_key in output_vars:
            return output_vars[node_var_key]
        elif variable_name in output_vars:
            return output_vars[variable_name]

        return None

    def _process_template_string(
        self, template: str, resolved_variables: Dict[str, Any], state: GenericState,adjust_json:bool=False
    ) -> str:
        """Process template strings with variable substitution"""
        
        def normalize_value(value: Any) -> str:
            """
            Normalize value for JSON format
            Example case for JSON:
                s = {
                    "name": "Alice",
                    "age": 30,
                    "city": "New York\n"
                }
                This JSON string is not valid because JSON value contains "\n", which throws an error when using json.load(s)
            """
            if adjust_json and isinstance(value, str):
                value = value.replace("\n", "\\n")
                #value = value.replace("\"", " ")
                #value = value.replace("\"", "'")
                
            return str(value)

        def replace_var(match):
            var_ref = match.group(1)

            # Handle system variables
            if var_ref.startswith("sys."):
                sys_var = var_ref[4:]
                return normalize_value(state.get(f"sys_{sys_var}", ""))

            # Handle node output variables
            if "." in var_ref:
                parts = var_ref.split(".")
                if len(parts) == 2:
                    node_id, var_name = parts
                    output_vars = state.get("output_variables", {})
                    params_var_key = f"{node_id}_{var_name}"
                    node_var_key = "{}_{}".format(parts[0], hash(tuple(parts[1:])))
                    resolved_value = VariableResolver.resolve_value_selector(
                        [node_id, var_name], state
                    )
                    return normalize_value(
                        resolved_value
                    )

            # Handle resolved variables
            if var_ref in resolved_variables:
                return normalize_value(resolved_variables[var_ref])

            return match.group(0)  # Return original if not found

        # Replace variables in the format {{#variable#}}
        pattern = r"\{\{#([^#]+)#\}\}"
        result = re.sub(pattern, replace_var, template)

        variable_pool = {
            "sys_query": state.get("sys_query"),
            "sys_dialogue_count": state.get("sys_dialogue_count"),
            "sys_conversation_id": state.get("sys_conversation_id"),
            "sys_user_id": state.get("sys_user_id"),
            "sys_files": state.get("sys_files"),
            "sys_app_id": state.get("sys_app_id"),
            "sys_workflow_id": state.get("sys_workflow_id"),
            "sys_workflow_run_id": state.get("sys_workflow_run_id"),
        }
        # 使用 dict.update() 比字典解包更高效
        variable_pool.update(state.get("input_variables", {}))
        variable_pool.update(state.get("output_variables", {}))
        variable_pool.update(state.get("conversation_variables", {}))

        return VariableResolver.replace_template(result, variable_pool)

    def _build_headers(
        self, resolved_variables: Dict[str, Any], state: GenericState
    ) -> Dict[str, str]:
        """Build request headers with variable substitution and authorization"""
        headers = {}

        # Process base headers
        for key, value in self.headers.items():
            processed_key = self._process_template_string(
                str(key), resolved_variables, state
            )
            processed_value = self._process_template_string(
                str(value), resolved_variables, state
            )
            headers[processed_key] = processed_value

        # Add authorization headers
        if self.authorization and hasattr(self.authorization, "type"):
            if self.authorization.type == "api-key" and hasattr(
                self.authorization, "config"
            ):
                config = self.authorization.config
                if config and hasattr(config, "api_key"):
                    header_name = config.header or "Authorization"
                    auth_type = getattr(config, "type", "bearer")

                    if auth_type == "bearer":
                        api_key = self._process_template_string(
                            str(config.api_key), resolved_variables, state
                        )
                        headers[header_name] = f"Bearer {api_key}"
                    elif auth_type == "basic":
                        import base64

                        credentials = config.api_key
                        if ":" in credentials:
                            encoded = base64.b64encode(credentials.encode()).decode()
                        else:
                            encoded = credentials
                        headers[header_name] = f"Basic {encoded}"
                    elif auth_type == "custom":
                        headers[header_name] = config.api_key

        return headers

    def _build_params(
        self, resolved_variables: Dict[str, Any], state: GenericState
    ) -> Dict[str, str]:
        """Build URL parameters with variable substitution"""
        params = {}

        for key, value in self.params.items():
            processed_key = self._process_template_string(
                str(key), resolved_variables, state
            )
            processed_value = self._process_template_string(
                str(value), resolved_variables, state
            )
            params[processed_key] = processed_value

        return params

    def _build_body(
        self, resolved_variables: Dict[str, Any], state: GenericState
    ) -> Any:
        """Build request body based on body configuration"""
        if not self.body or not hasattr(self.body, "type"):
            return None

        body_type = self.body.type

        if body_type == "none":
            return None
        elif body_type == "json":
            # Process JSON body
            if hasattr(self.body, "data") and self.body.data:
                json_str = self.body.data[0].value if self.body.data else "{}"
                processed_json = self._process_template_string(
                    json_str, resolved_variables, state,True
                )
                try:
                    return json.loads(processed_json)
                except json.JSONDecodeError:
                    logger.error(f"JSON解析错误: {processed_json}", exc_info=True)
                    return processed_json
        elif body_type == "raw-text":
            # Process raw text body
            if hasattr(self.body, "data") and self.body.data:
                raw_text = self.body.data[0].value if self.body.data else ""
                return self._process_template_string(
                    raw_text, resolved_variables, state
                )
        elif body_type == "form-data":
            # Process form data
            form_data = {}
            if hasattr(self.body, "data") and self.body.data:
                for item in self.body.data:
                    if hasattr(item, "key") and hasattr(item, "value"):
                        key = self._process_template_string(
                            item.key, resolved_variables, state
                        )
                        value = self._process_template_string(
                            item.value, resolved_variables, state
                        )
                        form_data[key] = value
            return form_data
        elif body_type == "x-www-form-urlencoded":
            # Process URL encoded data
            form_data = {}
            if hasattr(self.body, "data") and self.body.data:
                for item in self.body.data:
                    if hasattr(item, "key") and hasattr(item, "value"):
                        key = self._process_template_string(
                            item.key, resolved_variables, state
                        )
                        value = self._process_template_string(
                            item.value, resolved_variables, state
                        )
                        form_data[key] = value
            return urlencode(form_data)

        return None
    
    def _request_with_streaming(
        self, url: str, headers: Dict[str, str], params: Dict[str, str], body: Any
    ):
        """Execute HTTP request with streaming"""
        
        max_retries ,retry_interval = self._get_max_retries_and_interval()
        
        # 获取超时配置
        connect_timeout = 10.0
        read_timeout = 300.0
        if self.timeout_config:
            connect_timeout = getattr(self.timeout_config, "max_connect_timeout", 10) or 10
            read_timeout = getattr(self.timeout_config, "max_read_timeout", 300) or 300
        
        #TODO 多个请求复用相同client
        client = SSEClient(
            url=url,
            method=self.method,
            headers=headers,
            data=json.dumps(body, ensure_ascii=False) if body else None,
            reconnect_interval=retry_interval,
            max_reconnect_attempts=max_retries,
            connect_timeout=connect_timeout,  # ✅ 传递连接超时
            read_timeout=read_timeout          # ✅ 传递读取超时
        )
        message_callback = get_callback_by_url(url)
        
        if message_callback is None:
            raise ValueError(f"未找到URL {url} 的消息回调函数")
        
        def on_error(error):
            """处理错误"""
            logger.error(f"sse发生错误: {error}, url={url}", exc_info=True)
            raise ValueError(f"sse发生错误: {error}, url={url}")

        def on_open():
            """连接建立时调用"""
            logger.info(f"sse连接已建立, url={url}")
            
        # 设置回调函数
        client.on_message(partial(message_callback, node_id=self.id))
        client.on_error(on_error)
        client.on_open(on_open)
        client.connect()
        
        client.close()
        
        full_message = client.get_revc_full_message()
        
        return {"status_code": 200, "body": full_message, "headers": headers,"size": 0,"time": 0}
        
    def _get_max_retries_and_interval(self):
        max_retries = 0
        retry_interval = 1

        if self.retry_config:
            max_retries = getattr(self.retry_config, "max_retries", 0)
            retry_interval = getattr(self.retry_config, "retry_interval", 100)
            if type(retry_interval) == str:
                retry_interval = int(retry_interval)
            retry_interval = retry_interval / 1000
            
            retry_enabled = getattr(self.retry_config, "retry_enabled", False)

            if not retry_enabled:
                max_retries = 0
                
        return max_retries, retry_interval


    def _execute_request_with_retry(
        self, url: str, headers: Dict[str, str], params: Dict[str, str], body: Any
    ) -> Dict[str, Any]:
        """Execute HTTP request with retry logic"""
        max_retries ,retry_interval = self._get_max_retries_and_interval()

        last_exception = None

        for attempt in range(max_retries + 1):
            try:
                return self._execute_single_request(url, headers, params, body)
            except Exception as e:
                last_exception = e
                if attempt < max_retries:
                    time.sleep(retry_interval)
                else:
                    raise e

        raise last_exception

    def _execute_single_request(
        self, url: str, headers: Dict[str, str], params: Dict[str, str], body: Any
    ) -> Dict[str, Any]:
        """Execute a single HTTP request"""
        # Setup timeout
        timeout = 30  # Default timeout
        if self.timeout_config:
            connect_timeout = getattr(self.timeout_config, "max_connect_timeout", 30) or 30
            read_timeout = getattr(self.timeout_config, "max_read_timeout", 30) or 30
            timeout = (connect_timeout, read_timeout)

        # Prepare request arguments
        request_kwargs = {
            "url": url,
            "headers": headers,
            "params": params,
            "timeout": timeout,
            "verify": self.ssl_verify,
        }

        # Add body based on content type
        if body is not None:
            if isinstance(body, dict) and "Content-Type" in headers:
                # JSON body
                request_kwargs["json"] = body
            elif isinstance(body, str) and body.startswith("{"):
                # JSON string
                #body = body.replace("\n", "\\n")
                request_kwargs["json"] = json.loads(body)
                headers["Content-Type"] = "application/json"
            elif isinstance(body, str):
                # Raw text body
                request_kwargs["data"] = body
            elif isinstance(body, dict):
                # Form data
                request_kwargs["data"] = body

        # Execute request
        start_time = time.time()

        if self.method == "GET":
            response = requests.get(**request_kwargs)
        elif self.method == "POST":
            response = requests.post(**request_kwargs)
        elif self.method == "PUT":
            response = requests.put(**request_kwargs)
        elif self.method == "PATCH":
            response = requests.patch(**request_kwargs)
        elif self.method == "DELETE":
            response = requests.delete(**request_kwargs)
        elif self.method == "HEAD":
            response = requests.head(**request_kwargs)
        elif self.method == "OPTIONS":
            response = requests.options(**request_kwargs)
        else:
            raise ValueError(f"Unsupported HTTP method: {self.method}")

        end_time = time.time()

        # Process response
        # try:
        #    response_body = response.json()
        # except json.JSONDecodeError:
        #    response_body = response.text
        logger.info(f"{self.formatted_name} node request_kwargs: {request_kwargs}")

        response_body = response.text

        return {
            "status_code": response.status_code,
            "body": response_body,
            "headers": dict(response.headers),
            "size": len(response.content),
            "time": round((end_time - start_time) * 1000),  # Time in milliseconds
        }

    # TODO
    def _handle_error(self, state: GenericState, error: Exception) -> GenericState:
        """Handle errors according to the node's error strategy"""
        if self.error_strategy and hasattr(self.error_strategy, "value"):
            if self.error_strategy.value == "fail-branch":
                # Set error response and continue
                return Command(
                    # this is the state update
                    update={
                        "output_variables": {f"{self.id}_error": str(error)},
                        "node_id": self.id,
                        "source_handle": "fail-branch",
                    },
                    # this is a replacement for an edge
                    goto=self.fail_branch_node_ids,
                )

            elif self.error_strategy.value == "default-value":
                # Use configured default values
                update_vars = {}

                if self.default_value:
                    for default_val in self.default_value:
                        update_vars[f"{default_val.key}"] = default_val.value
                else:
                    # Use standard defaults

                    update_vars["status_code"] = 200
                    update_vars["body"] = ""
                    update_vars[f"headers"] = {}
                    update_vars[f"size"] = 0
                    update_vars[f"time"] = 0

                # return {'output_variables': update_vars,"node_id":self.id,"source_handle":"source"}
                update_data = VariableResolver.format_output(
                    node_id=self.id, outputs=update_vars
                )
                return Command(
                    update=update_data,
                    goto=self.next_node_ids,
                )
        # Default: re-raise the error
        raise error

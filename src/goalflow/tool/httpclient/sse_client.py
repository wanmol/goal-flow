import requests
import json
import time
import threading
from typing import Callable, Optional, Dict, Any, Union

from goalflow.config import get_logger

logger = get_logger(__name__)

class SSEClient:
    """
    Python SSE (Server-Sent Events) 客户端实现
    支持自动重连、事件处理、GET/POST请求等功能
    """

    def __init__(self, url: str, method: str = "GET", 
                 headers: Optional[Dict[str, str]] = None,
                 data: Optional[Union[str, Dict[str, Any], bytes]] = None,
                 reconnect_interval: float = 3.0, max_reconnect_attempts: int = 5,
                 connect_timeout: float = 10.0, read_timeout: float = 300.0):
        """
        初始化SSE客户端
        
        Args:
            url: SSE服务端URL
            method: HTTP方法 ("GET" 或 "POST")
            headers: 请求头
            data: POST请求的数据 (仅在method="POST"时有效)
            reconnect_interval: 重连间隔（秒）
            max_reconnect_attempts: 最大重连尝试次数
            connect_timeout: 连接超时时间（秒），默认 10 秒
            read_timeout: 读取超时时间（秒），默认 300 秒（5分钟）
        """
        self.url = url
        self.method = method.upper()
        self.headers = headers or {}
        self.data = data
        self.reconnect_interval = reconnect_interval
        self.max_reconnect_attempts = max_reconnect_attempts
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        
        # 确保Accept头设置正确
        if "Accept" not in self.headers:
            self.headers["Accept"] = "text/event-stream"
        
        # 如果是POST请求，设置默认Content-Type
        if self.method == "POST" and "Content-Type" not in self.headers:
            if isinstance(data, dict):
                self.headers["Content-Type"] = "application/json"
            else:
                self.headers["Content-Type"] = "text/plain"
        
        # 回调函数
        self.on_message_callback: Optional[Callable[[str], None]] = None
        self.on_event_callback: Optional[Callable[[str, str], None]] = None
        self.on_error_callback: Optional[Callable[[Exception], None]] = None
        self.on_open_callback: Optional[Callable[[], None]] = None
        
        # 内部状态
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._session = requests.Session()
        self._connection_closed_by_server = False  # 新增：标记服务器是否主动关闭连接
        
        self.revc_full_message = ""

    def on_message(self, callback: Callable[[str], None]):
        """设置消息回调函数"""
        self.on_message_callback = callback
        return self

    def on_event(self, callback: Callable[[str, str], None]):
        """设置事件回调函数"""
        self.on_event_callback = callback
        return self

    def on_error(self, callback: Callable[[Exception], None]):
        """设置错误回调函数"""
        self.on_error_callback = callback
        return self

    def on_open(self, callback: Callable[[], None]):
        """设置连接打开回调函数"""
        self.on_open_callback = callback
        return self

    def _parse_event(self, line: str) -> Dict[str, Any]:
        """解析SSE事件行"""
        if line.startswith(":"):
            # 注释行，忽略
            return {}
        
        if ":" in line:
            field, value = line.split(":", 1)
            value = value.lstrip()
        else:
            field, value = line, ""
        
        return {field: value}

    def _process_stream(self, response):
        """处理SSE流数据"""
        event_data = {
            "event": "message",
            "data": "",
            "id": "",
            "retry": ""
        }
        
        for line in response.iter_lines(decode_unicode=True):
            #print(f"收到原始行: {line}")
            if not self._running:
                break
                
            if line:
                parsed = self._parse_event(line)
                if not parsed:
                    continue
                    
                field, value = next(iter(parsed.items()))
                
                if field == "data":
                    event_data["data"] += value + "\n"
                elif field == "event":
                    event_data["event"] = value
                elif field == "id":
                    event_data["id"] = value
                elif field == "retry":
                    try:
                        self.reconnect_interval = int(value) / 1000.0
                    except ValueError:
                        pass
            else:
                # 空行表示一个事件结束
                if event_data["data"]:
                    # 移除最后一个换行符
                    event_data["data"] = event_data["data"].rstrip("\n")
                    
                    # 触发事件回调
                    if self.on_event_callback:
                        self.on_event_callback(event_data["event"], event_data["data"])
                    
                    # 如果是message事件，触发消息回调
                    if event_data["event"] == "message" and self.on_message_callback:
                        message = self.on_message_callback(event_data["data"])
                        if message is not None:
                            self.revc_full_message += message
                        

                # 重置事件数据
                event_data = {
                    "event": "message",
                    "data": "",
                    "id": "",
                    "retry": ""
                }

    def _connect_and_listen(self):
        """连接并监听SSE流"""
        reconnect_attempts = 0
        
        while self._running and reconnect_attempts < self.max_reconnect_attempts:
            try:
                # 检查是否是服务器主动关闭连接的情况
                if self._connection_closed_by_server:
                    logger.info("Connection was closed by server, stopping client")
                    break
                    
                logger.info(f"Connecting to SSE server: {self.url} using {self.method}")
                
                # 根据方法选择请求参数
                # 使用动态超时配置（从 __init__ 传入）
                request_kwargs = {
                    "url": self.url,
                    "headers": self.headers,
                    "stream": True,
                    "timeout": (self.connect_timeout, self.read_timeout)
                }
                
                # 如果是POST请求，添加数据
                if self.method == "POST":
                    request_kwargs["data"] = self.data
                    
                
                # 发起HTTP请求
                if self.method == "GET":
                    response = self._session.get(**request_kwargs)
                elif self.method == "POST":
                    response = self._session.post(**request_kwargs)
                else:
                    raise ValueError(f"Unsupported HTTP method: {self.method}")
                
                # 检查响应状态码
                if response.status_code != 200:
                    logger.error(f"sse_request_failed: {response}")
                    raise requests.exceptions.HTTPError(f"HTTP {response.status_code}: {response.reason}")
                
                # 检查Content-Type
                content_type = response.headers.get("Content-Type", "")
                if "text/event-stream" not in content_type:
                    logger.warning(f"Unexpected Content-Type: {content_type}")
                
                # 触发连接打开回调
                if self.on_open_callback:
                    self.on_open_callback()
                
                # 重置重连计数和服务器关闭标记
                reconnect_attempts = 0
                self._connection_closed_by_server = False
                
                # 处理流数据
                self._process_stream(response)
                
                # 如果正常退出_process_stream，说明服务器关闭了连接
                self._connection_closed_by_server = True
                
            except Exception as e:
                if not self._running:
                    break
                    
                reconnect_attempts += 1
                logger.error(f"Error in SSE connection: {e}", exc_info=True)
                
                # 触发错误回调
                if self.on_error_callback:
                    self.on_error_callback(e)
                
                # 如果达到最大重连次数，则退出
                if reconnect_attempts >= self.max_reconnect_attempts:
                    logger.error("Max reconnect attempts reached, stopping client")
                    break
                
                # 等待重连
                logger.info(f"Reconnecting in {self.reconnect_interval} seconds...")
                time.sleep(self.reconnect_interval)

    def get_revc_full_message(self):
        """获取完整接收的消息"""
        return self.revc_full_message

    def connect(self):
        """同步连接到SSE服务器（阻塞式）"""
        self._running = True
        self._connection_closed_by_server = False  # 重置服务器关闭标记
        self._connect_and_listen()

    def connect_async(self):
        """异步连接到SSE服务器（非阻塞式）"""
        if self._thread and self._thread.is_alive():
            logger.warning("SSE client is already running")
            return
            
        self._running = True
        self._connection_closed_by_server = False  # 重置服务器关闭标记
        self._thread = threading.Thread(target=self._connect_and_listen, daemon=True)
        self._thread.start()
        return self._thread

    def close(self):
        """关闭SSE连接"""
        logger.info("Closing SSE connection")
        self._running = False
        self._connection_closed_by_server = True  # 标记为主动关闭
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._session.close()


# 使用示例
if __name__ == "__main__":
    # 示例1: GET请求
    def on_message(data):
        print(f"Received message: {data}")

    def on_event(event, data):
        print(f"Received event '{event}': {data}")

    def on_error(error):
        print(f"Error occurred: {error}")

    def on_open():
        print("Connection opened")

    # 创建GET客户端
    get_client = SSEClient("http://example.com/events")
    
    # 设置回调
    get_client.on_message(on_message)\
             .on_event(on_event)\
             .on_error(on_error)\
             .on_open(on_open)
    
    # 异步连接
    get_client.connect_async()
    
    # 示例2: POST请求
    post_data = {
        "user_id": "12345",
        "subscription": ["news", "updates"]
    }
    
    post_client = SSEClient(
        url="http://example.com/events",
        method="POST",
        data=json.dumps(post_data),
        headers={"Content-Type": "application/json"}
    )
    
    # 可以复用相同的回调函数
    post_client.on_message(on_message)\
              .on_event(on_event)\
              .on_error(on_error)\
              .on_open(on_open)
    
    # 异步连接
    post_client.connect_async()
    
    # 保持主线程运行
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down...")
        get_client.close()
        post_client.close()
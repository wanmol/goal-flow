import requests
import json
import time
import threading
from typing import Callable, Optional, Dict, Any, Union

from goalflow.config import get_logger

logger = get_logger(__name__)

class SSEClient:
    """
    Python SSE (Server-Sent Events) client implementation
    Supports automatic reconnection, event handling, GET/POST requests, and more
    """

    def __init__(self, url: str, method: str = "GET", 
                 headers: Optional[Dict[str, str]] = None,
                 data: Optional[Union[str, Dict[str, Any], bytes]] = None,
                 reconnect_interval: float = 3.0, max_reconnect_attempts: int = 5,
                 connect_timeout: float = 10.0, read_timeout: float = 300.0):
        """
        Initialize the SSE client

        Args:
            url: SSE server URL
            method: HTTP method ("GET" or "POST")
            headers: Request headers
            data: Data for POST requests (only valid when method="POST")
            reconnect_interval: Reconnection interval (seconds)
            max_reconnect_attempts: Maximum number of reconnection attempts
            connect_timeout: Connection timeout (seconds), default 10 seconds
            read_timeout: Read timeout (seconds), default 300 seconds (5 minutes)
        """
        self.url = url
        self.method = method.upper()
        self.headers = headers or {}
        self.data = data
        self.reconnect_interval = reconnect_interval
        self.max_reconnect_attempts = max_reconnect_attempts
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        
        # Ensure the Accept header is set correctly
        if "Accept" not in self.headers:
            self.headers["Accept"] = "text/event-stream"

        # If it is a POST request, set the default Content-Type
        if self.method == "POST" and "Content-Type" not in self.headers:
            if isinstance(data, dict):
                self.headers["Content-Type"] = "application/json"
            else:
                self.headers["Content-Type"] = "text/plain"

        # Callback functions
        self.on_message_callback: Optional[Callable[[str], None]] = None
        self.on_event_callback: Optional[Callable[[str, str], None]] = None
        self.on_error_callback: Optional[Callable[[Exception], None]] = None
        self.on_open_callback: Optional[Callable[[], None]] = None

        # Internal state
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._session = requests.Session()
        self._connection_closed_by_server = False  # New: flag whether the server actively closed the connection
        
        self.revc_full_message = ""

    def on_message(self, callback: Callable[[str], None]):
        """Set the message callback function"""
        self.on_message_callback = callback
        return self

    def on_event(self, callback: Callable[[str, str], None]):
        """Set the event callback function"""
        self.on_event_callback = callback
        return self

    def on_error(self, callback: Callable[[Exception], None]):
        """Set the error callback function"""
        self.on_error_callback = callback
        return self

    def on_open(self, callback: Callable[[], None]):
        """Set the connection-open callback function"""
        self.on_open_callback = callback
        return self

    def _parse_event(self, line: str) -> Dict[str, Any]:
        """Parse an SSE event line"""
        if line.startswith(":"):
            # Comment line, ignore
            return {}
        
        if ":" in line:
            field, value = line.split(":", 1)
            value = value.lstrip()
        else:
            field, value = line, ""
        
        return {field: value}

    def _process_stream(self, response):
        """Process SSE stream data"""
        event_data = {
            "event": "message",
            "data": "",
            "id": "",
            "retry": ""
        }
        
        for line in response.iter_lines(decode_unicode=True):
            #print(f"received raw line: {line}")
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
                # An empty line marks the end of an event
                if event_data["data"]:
                    # Remove the last newline character
                    event_data["data"] = event_data["data"].rstrip("\n")

                    # Trigger the event callback
                    if self.on_event_callback:
                        self.on_event_callback(event_data["event"], event_data["data"])

                    # If it is a message event, trigger the message callback
                    if event_data["event"] == "message" and self.on_message_callback:
                        message = self.on_message_callback(event_data["data"])
                        if message is not None:
                            self.revc_full_message += message


                # Reset the event data
                event_data = {
                    "event": "message",
                    "data": "",
                    "id": "",
                    "retry": ""
                }

    def _connect_and_listen(self):
        """Connect and listen to the SSE stream"""
        reconnect_attempts = 0

        while self._running and reconnect_attempts < self.max_reconnect_attempts:
            try:
                # Check whether the server actively closed the connection
                if self._connection_closed_by_server:
                    logger.info("Connection was closed by server, stopping client")
                    break

                logger.info(f"Connecting to SSE server: {self.url} using {self.method}")

                # Select request parameters based on the method
                # Use dynamic timeout configuration (passed in from __init__)
                request_kwargs = {
                    "url": self.url,
                    "headers": self.headers,
                    "stream": True,
                    "timeout": (self.connect_timeout, self.read_timeout)
                }

                # If it is a POST request, add the data
                if self.method == "POST":
                    request_kwargs["data"] = self.data


                # Send the HTTP request
                if self.method == "GET":
                    response = self._session.get(**request_kwargs)
                elif self.method == "POST":
                    response = self._session.post(**request_kwargs)
                else:
                    raise ValueError(f"Unsupported HTTP method: {self.method}")

                # Check the response status code
                if response.status_code != 200:
                    logger.error(f"sse_request_failed: {response}")
                    raise requests.exceptions.HTTPError(f"HTTP {response.status_code}: {response.reason}")

                # Check the Content-Type
                content_type = response.headers.get("Content-Type", "")
                if "text/event-stream" not in content_type:
                    logger.warning(f"Unexpected Content-Type: {content_type}")

                # Trigger the connection-open callback
                if self.on_open_callback:
                    self.on_open_callback()

                # Reset the reconnect count and the server-closed flag
                reconnect_attempts = 0
                self._connection_closed_by_server = False

                # Process the stream data
                self._process_stream(response)

                # If _process_stream exits normally, the server closed the connection
                self._connection_closed_by_server = True

            except Exception as e:
                if not self._running:
                    break

                reconnect_attempts += 1
                logger.error(f"Error in SSE connection: {e}", exc_info=True)

                # Trigger the error callback
                if self.on_error_callback:
                    self.on_error_callback(e)

                # If the maximum number of reconnects is reached, exit
                if reconnect_attempts >= self.max_reconnect_attempts:
                    logger.error("Max reconnect attempts reached, stopping client")
                    break

                # Wait before reconnecting
                logger.info(f"Reconnecting in {self.reconnect_interval} seconds...")
                time.sleep(self.reconnect_interval)

    def get_revc_full_message(self):
        """Get the full received message"""
        return self.revc_full_message

    def connect(self):
        """Connect to the SSE server synchronously (blocking)"""
        self._running = True
        self._connection_closed_by_server = False  # Reset the server-closed flag
        self._connect_and_listen()

    def connect_async(self):
        """Connect to the SSE server asynchronously (non-blocking)"""
        if self._thread and self._thread.is_alive():
            logger.warning("SSE client is already running")
            return

        self._running = True
        self._connection_closed_by_server = False  # Reset the server-closed flag
        self._thread = threading.Thread(target=self._connect_and_listen, daemon=True)
        self._thread.start()
        return self._thread

    def close(self):
        """Close the SSE connection"""
        logger.info("Closing SSE connection")
        self._running = False
        self._connection_closed_by_server = True  # Mark as actively closed
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._session.close()


# Usage example
if __name__ == "__main__":
    # Example 1: GET request
    def on_message(data):
        print(f"Received message: {data}")

    def on_event(event, data):
        print(f"Received event '{event}': {data}")

    def on_error(error):
        print(f"Error occurred: {error}")

    def on_open():
        print("Connection opened")

    # Create a GET client
    get_client = SSEClient("http://example.com/events")

    # Set callbacks
    get_client.on_message(on_message)\
             .on_event(on_event)\
             .on_error(on_error)\
             .on_open(on_open)

    # Connect asynchronously
    get_client.connect_async()

    # Example 2: POST request
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

    # The same callback functions can be reused
    post_client.on_message(on_message)\
              .on_event(on_event)\
              .on_error(on_error)\
              .on_open(on_open)

    # Connect asynchronously
    post_client.connect_async()

    # Keep the main thread running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down...")
        get_client.close()
        post_client.close()
# memory_middleware.py
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from typing import Callable
import time

class MemoryMonitoringMiddleware(BaseHTTPMiddleware):
    """Memory monitoring middleware - compatible with all FastAPI versions"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        from .memory_monitor import get_memory_monitor

        # Get the memory monitor
        monitor = get_memory_monitor()

        # Record memory at the start of the request
        start_snapshot = monitor.snapshot(f"request_start_{request.url.path}")

        # Record the request time
        start_time = time.time()

        try:
            # Process the request
            response = await call_next(request)

            # Calculate the request processing time
            process_time = time.time() - start_time

            # Record memory at the end of the request
            end_snapshot = monitor.snapshot(f"request_end_{request.url.path}")

            # Calculate the memory change
            memory_change = end_snapshot['rss_mb'] - start_snapshot['rss_mb']

            # Add memory info to the response headers (optional)
            response.headers["X-Process-Time"] = str(process_time)
            response.headers["X-Memory-Change-MB"] = str(round(memory_change, 2))
            response.headers["X-Memory-Current-MB"] = str(round(end_snapshot['rss_mb'], 2))

            # If the memory change is large, log it
            if abs(memory_change) > 10:  # change exceeds 10MB
                print(f"⚠️  {request.method} {request.url.path} - "
                      f"内存变化: {memory_change:.1f} MB, "
                      f"耗时: {process_time:.2f}s")

            return response

        except Exception as e:
            # Record memory on exception
            monitor.snapshot(f"request_error_{request.url.path}")
            print(f"❌ 请求处理出错 {request.url.path}: {e}")
            raise e
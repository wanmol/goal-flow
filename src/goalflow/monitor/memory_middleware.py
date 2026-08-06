# memory_middleware.py
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from typing import Callable
import time

class MemoryMonitoringMiddleware(BaseHTTPMiddleware):
    """内存监控中间件 - 兼容所有 FastAPI 版本"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        from .memory_monitor import get_memory_monitor
        
        # 获取内存监控器
        monitor = get_memory_monitor()
        
        # 记录请求开始时的内存
        start_snapshot = monitor.snapshot(f"request_start_{request.url.path}")
        
        # 记录请求时间
        start_time = time.time()
        
        try:
            # 处理请求
            response = await call_next(request)
            
            # 计算请求处理时间
            process_time = time.time() - start_time
            
            # 记录请求结束时的内存
            end_snapshot = monitor.snapshot(f"request_end_{request.url.path}")
            
            # 计算内存变化
            memory_change = end_snapshot['rss_mb'] - start_snapshot['rss_mb']
            
            # 将内存信息添加到响应头（可选）
            response.headers["X-Process-Time"] = str(process_time)
            response.headers["X-Memory-Change-MB"] = str(round(memory_change, 2))
            response.headers["X-Memory-Current-MB"] = str(round(end_snapshot['rss_mb'], 2))
            
            # 如果内存变化较大，记录日志
            if abs(memory_change) > 10:  # 变化超过10MB
                print(f"⚠️  {request.method} {request.url.path} - "
                      f"内存变化: {memory_change:.1f} MB, "
                      f"耗时: {process_time:.2f}s")
            
            return response
            
        except Exception as e:
            # 记录异常时的内存
            monitor.snapshot(f"request_error_{request.url.path}")
            print(f"❌ 请求处理出错 {request.url.path}: {e}")
            raise e
# framework_leak_checker.py
import gc
import sys
import inspect
from typing import List, Dict
import asyncio

class FrameworkLeakChecker:
    """Memory leak checker for common frameworks"""

    @staticmethod
    def check_fastapi():
        """Check common FastAPI memory issues"""
        issues = []

        try:
            from fastapi import FastAPI
            import fastapi

            # Check route cache
            app_instances = []
            for obj in gc.get_objects():
                if isinstance(obj, FastAPI):
                    app_instances.append(obj)
            
            if len(app_instances) > 1:
                issues.append(f"⚠️  发现多个FastAPI实例 ({len(app_instances)}个)")
            
            # Check dependency cache
            for obj in gc.get_objects():
                if hasattr(obj, '__class__') and 'dependency' in str(obj.__class__).lower():
                    if hasattr(obj, '_cache') and isinstance(obj._cache, dict):
                        cache_size = len(obj._cache)
                        if cache_size > 1000:
                            issues.append(f"⚠️  依赖缓存过大: {cache_size} 项")
            
        except ImportError:
            pass
        
        return issues
    
    @staticmethod
    def check_sqlalchemy():
        """Check common SQLAlchemy memory issues"""
        issues = []

        try:
            from sqlalchemy.orm import Session
            import sqlalchemy

            # Check for unclosed Sessions
            open_sessions = []
            for obj in gc.get_objects():
                if isinstance(obj, Session) and obj.is_active:
                    open_sessions.append(obj)
            
            if open_sessions:
                issues.append(f"⚠️  发现 {len(open_sessions)} 个活跃的SQLAlchemy Session未关闭")
            
            # Check query cache
            engine_count = 0
            # for obj in gc.get_objects():
            #     if hasattr(obj, 'execute') and hasattr(obj, 'connect'):
            #         engine_count += 1

            # if engine_count > 5:
            #     issues.append(f"⚠️  发现 {engine_count} 个数据库引擎，可能过多")
            
        except ImportError:
            pass
        
        return issues
    
    @staticmethod
    def check_asyncio():
        """Check common asyncio memory issues"""
        issues = []

        try:
            # Check for incomplete tasks
            tasks = [t for t in asyncio.all_tasks() if not t.done()]
            if tasks:
                issues.append(f"⚠️  发现 {len(tasks)} 个未完成的asyncio任务")

            # Check callbacks in the event loop
            loop = asyncio.get_event_loop()

            # Check timers
            if hasattr(loop, '_scheduled'):
                scheduled = len(loop._scheduled)
                if scheduled > 100:
                    issues.append(f"⚠️  事件循环中有 {scheduled} 个定时任务")

            # Check callbacks
            if hasattr(loop, '_ready'):
                ready = len(loop._ready)
                if ready > 1000:
                    issues.append(f"⚠️  事件循环中有 {ready} 个就绪回调")
            
        except Exception as e:
            issues.append(f"⚠️  检查asyncio时出错: {e}")
        
        return issues
    
    @staticmethod
    def check_redis():
        """Check for Redis connection leaks"""
        issues = []
        
        try:
            import redis
            
            redis_connections = []
            for obj in gc.get_objects():
                if hasattr(obj, '__class__') and 'redis' in str(obj.__class__).lower():
                    if hasattr(obj, 'connection_pool'):
                        redis_connections.append(obj)
            
            if len(redis_connections) > 10:
                issues.append(f"⚠️  发现 {len(redis_connections)} 个Redis连接，可能泄漏")
            
        except ImportError:
            pass
        
        return issues
    
    @staticmethod
    def check_all_frameworks():
        """Check all supported frameworks"""
        all_issues = []
        
        print("🔍 检查框架相关内存问题...")
        print("-" * 60)
        
        # FastAPI
        fastapi_issues = FrameworkLeakChecker.check_fastapi()
        if fastapi_issues:
            print("FastAPI:")
            for issue in fastapi_issues:
                print(f"  {issue}")
            all_issues.extend(fastapi_issues)
        
        # SQLAlchemy
        sqlalchemy_issues = FrameworkLeakChecker.check_sqlalchemy()
        if sqlalchemy_issues:
            print("\nSQLAlchemy:")
            for issue in sqlalchemy_issues:
                print(f"  {issue}")
            all_issues.extend(sqlalchemy_issues)
        
        # asyncio
        asyncio_issues = FrameworkLeakChecker.check_asyncio()
        if asyncio_issues:
            print("\nasyncio:")
            for issue in asyncio_issues:
                print(f"  {issue}")
            all_issues.extend(asyncio_issues)
        
        # Redis
        redis_issues = FrameworkLeakChecker.check_redis()
        if redis_issues:
            print("\nRedis:")
            for issue in redis_issues:
                print(f"  {issue}")
            all_issues.extend(redis_issues)
        
        if not all_issues:
            print("✅ 未发现框架相关内存问题")
        
        return all_issues
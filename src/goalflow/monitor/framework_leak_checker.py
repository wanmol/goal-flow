# framework_leak_checker.py
import gc
import sys
import inspect
from typing import List, Dict
import asyncio

class FrameworkLeakChecker:
    """针对常见框架的内存泄漏检查器"""
    
    @staticmethod
    def check_fastapi():
        """检查FastAPI常见内存问题"""
        issues = []
        
        try:
            from fastapi import FastAPI
            import fastapi
            
            # 检查路由缓存
            app_instances = []
            for obj in gc.get_objects():
                if isinstance(obj, FastAPI):
                    app_instances.append(obj)
            
            if len(app_instances) > 1:
                issues.append(f"⚠️  发现多个FastAPI实例 ({len(app_instances)}个)")
            
            # 检查依赖项缓存
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
        """检查SQLAlchemy常见内存问题"""
        issues = []
        
        try:
            from sqlalchemy.orm import Session
            import sqlalchemy
            
            # 检查未关闭的Session
            open_sessions = []
            for obj in gc.get_objects():
                if isinstance(obj, Session) and obj.is_active:
                    open_sessions.append(obj)
            
            if open_sessions:
                issues.append(f"⚠️  发现 {len(open_sessions)} 个活跃的SQLAlchemy Session未关闭")
            
            # 检查查询缓存
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
        """检查asyncio常见内存问题"""
        issues = []
        
        try:
            # 检查未完成的任务
            tasks = [t for t in asyncio.all_tasks() if not t.done()]
            if tasks:
                issues.append(f"⚠️  发现 {len(tasks)} 个未完成的asyncio任务")
            
            # 检查事件循环中的回调
            loop = asyncio.get_event_loop()
            
            # 检查定时器
            if hasattr(loop, '_scheduled'):
                scheduled = len(loop._scheduled)
                if scheduled > 100:
                    issues.append(f"⚠️  事件循环中有 {scheduled} 个定时任务")
            
            # 检查回调
            if hasattr(loop, '_ready'):
                ready = len(loop._ready)
                if ready > 1000:
                    issues.append(f"⚠️  事件循环中有 {ready} 个就绪回调")
            
        except Exception as e:
            issues.append(f"⚠️  检查asyncio时出错: {e}")
        
        return issues
    
    @staticmethod
    def check_redis():
        """检查Redis连接泄漏"""
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
        """检查所有支持的框架"""
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
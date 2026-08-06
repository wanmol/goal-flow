# leak_detector.py
import gc
import sys
import psutil
import os
from collections import defaultdict
import time

class QuickLeakDetector:
    """快速内存泄漏探测器"""
    
    @staticmethod
    def quick_check():
        """5分钟快速检查"""
        
        print("🔍 快速内存泄漏检查开始...")
        print("-" * 60)
        
        # 1. 检查对象增长
        gc.collect()
        initial_objects = len(gc.get_objects())
        print(f"1. 初始对象数: {initial_objects:,}")
        
        # 2. 检查常见问题模式
        issues = []
        
        # 检查循环引用
        unreachable = gc.collect()
        if unreachable > 0:
            issues.append(f"⚠️  发现 {unreachable} 个不可达对象（可能已被GC清理）")
        
        # 检查全局变量
        global_vars = list(globals().keys())
        if len(global_vars) > 50:
            issues.append(f"⚠️  全局变量过多 ({len(global_vars)}个)")
        
        # 检查模块加载
        modules = list(sys.modules.keys())
        if len(modules) > 200:
            issues.append(f"⚠️  加载模块过多 ({len(modules)}个)")
        
        # 3. 简单压力测试
        print("\n2. 执行简单压力测试...")
        test_data = []
        for i in range(10000):
            test_data.append({"id": i, "data": "x" * 100})
        
        gc.collect()
        after_objects = len(gc.get_objects())
        object_growth = after_objects - initial_objects
        
        # 清理测试数据
        del test_data
        gc.collect()
        final_objects = len(gc.get_objects())
        
        print(f"   测试后对象数: {after_objects:,}")
        print(f"   对象增长: {object_growth:,}")
        print(f"   清理后对象数: {final_objects:,}")
        
        if final_objects > initial_objects * 1.1:
            issues.append(f"🚨 对象未完全释放 (增长 {final_objects - initial_objects:,}个)")
        
        # 输出结果
        print("\n3. 检查结果:")
        print("-" * 60)
        if issues:
            for issue in issues:
                print(issue)
            print(f"\n💡 建议: 使用详细分析工具进一步调查")
        else:
            print("✅ 未发现明显内存问题")
        
        return issues
# leak_detector.py
import gc
import sys
import psutil
import os
from collections import defaultdict
import time

class QuickLeakDetector:
    """Quick memory leak detector"""

    @staticmethod
    def quick_check():
        """5-minute quick check"""

        print("🔍 快速内存泄漏检查开始...")
        print("-" * 60)

        # 1. Check object growth
        gc.collect()
        initial_objects = len(gc.get_objects())
        print(f"1. 初始对象数: {initial_objects:,}")

        # 2. Check common problem patterns
        issues = []

        # Check circular references
        unreachable = gc.collect()
        if unreachable > 0:
            issues.append(f"⚠️  发现 {unreachable} 个不可达对象（可能已被GC清理）")

        # Check global variables
        global_vars = list(globals().keys())
        if len(global_vars) > 50:
            issues.append(f"⚠️  全局变量过多 ({len(global_vars)}个)")

        # Check loaded modules
        modules = list(sys.modules.keys())
        if len(modules) > 200:
            issues.append(f"⚠️  加载模块过多 ({len(modules)}个)")

        # 3. Simple stress test
        print("\n2. 执行简单压力测试...")
        test_data = []
        for i in range(10000):
            test_data.append({"id": i, "data": "x" * 100})

        gc.collect()
        after_objects = len(gc.get_objects())
        object_growth = after_objects - initial_objects

        # Clean up test data
        del test_data
        gc.collect()
        final_objects = len(gc.get_objects())
        
        print(f"   测试后对象数: {after_objects:,}")
        print(f"   对象增长: {object_growth:,}")
        print(f"   清理后对象数: {final_objects:,}")
        
        if final_objects > initial_objects * 1.1:
            issues.append(f"🚨 对象未完全释放 (增长 {final_objects - initial_objects:,}个)")
        
        # Output results
        print("\n3. 检查结果:")
        print("-" * 60)
        if issues:
            for issue in issues:
                print(issue)
            print(f"\n💡 建议: 使用详细分析工具进一步调查")
        else:
            print("✅ 未发现明显内存问题")
        
        return issues
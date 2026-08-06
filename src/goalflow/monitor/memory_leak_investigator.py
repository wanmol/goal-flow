# memory_leak_investigator.py
import gc
import sys
import tracemalloc
import objgraph
import linecache
from collections import defaultdict, Counter
from typing import Dict, List, Set, Any, Optional
import time
import threading
from datetime import datetime
import atexit

class MemoryLeakInvestigator:
    """系统化内存泄漏调查器"""
    
    def __init__(self, app_name: str):
        self.app_name = app_name
        self.snapshots = []
        self.leak_suspects = []
        self._setup_monitoring()
        
        # 注册退出时的分析
        atexit.register(self._exit_analysis)
    
    def _setup_monitoring(self):
        """设置监控"""
        # 启用tracemalloc
        tracemalloc.start(25)
        
        # 启用objgraph回调
        gc.set_debug(gc.DEBUG_SAVEALL)
        
        print(f"🧠 {self.app_name} 内存泄漏监控已启用")
    
    def take_snapshot(self, label: str = None):
        """获取内存快照"""
        snapshot = {
            'timestamp': time.time(),
            'datetime': datetime.now().isoformat(),
            'label': label,
            'tracemalloc': tracemalloc.take_snapshot(),
            'gc_objects': len(gc.get_objects()),
            'gc_garbage': len(gc.garbage)
        }
        
        self.snapshots.append(snapshot)
        return snapshot
    
    def analyze_growth_patterns(self):
        """分析增长模式"""
        if len(self.snapshots) < 2:
            return {"error": "需要至少2个快照"}
        
        results = []
        
        for i in range(1, len(self.snapshots)):
            prev = self.snapshots[i-1]
            curr = self.snapshots[i]
            
            # 比较快照
            diff = curr['tracemalloc'].compare_to(prev['tracemalloc'], 'lineno')
            
            # 分析显著增长
            significant_growth = []
            for stat in diff[:20]:  # 查看前20个变化
                if stat.size_diff > 1024 * 1024:  # 增长超过1MB
                    trace = stat.traceback
                    if trace:
                        frame = trace[0]
                        filename = frame.filename
                        lineno = frame.lineno
                        line = linecache.getline(filename, lineno).strip()
                        
                        significant_growth.append({
                            'size_diff_mb': stat.size_diff / (1024 * 1024),
                            'count_diff': stat.count_diff,
                            'filename': filename,
                            'lineno': lineno,
                            'line': line
                        })
            
            if significant_growth:
                results.append({
                    'time_range': f"{prev['datetime']} → {curr['datetime']}",
                    'object_growth': curr['gc_objects'] - prev['gc_objects'],
                    'significant_growth': significant_growth
                })
        
        return results
    
    def find_circular_references(self, top_n: int = 10):
        """查找循环引用"""
        gc.collect()
        gc.collect()  # 两次确保
        
        garbage = gc.garbage
        if not garbage:
            return {"message": "未发现不可达的循环引用"}
        
        # 分析垃圾对象
        analysis = []
        for i, obj in enumerate(garbage[:top_n]):
            analysis.append({
                'index': i,
                'type': type(obj).__name__,
                'repr': repr(obj)[:200],
                'referrers': len(gc.get_referrers(obj))
            })
        
        return {
            'garbage_count': len(garbage),
            'analysis': analysis,
            'suggestion': '检查 __del__ 方法或使用 weakref 打破循环引用'
        }
    
    def track_object_creation(self, target_type: str, duration: int = 30):
        """跟踪特定类型对象的创建"""
        print(f"👀 开始跟踪 {target_type} 对象创建，持续 {duration} 秒...")
        
        initial_count = self._count_objects_by_type(target_type)
        snapshots = []
        
        start_time = time.time()
        while time.time() - start_time < duration:
            time.sleep(5)
            
            current_count = self._count_objects_by_type(target_type)
            snapshot = {
                'time': time.time() - start_time,
                'count': current_count,
                'growth': current_count - initial_count
            }
            
            snapshots.append(snapshot)
            
            if current_count - initial_count > 1000:
                print(f"⚠️  {target_type} 快速增长: {current_count - initial_count} 个")
        
        # 分析趋势
        growth_rate = (snapshots[-1]['count'] - snapshots[0]['count']) / duration
        
        return {
            'target_type': target_type,
            'duration': duration,
            'initial_count': initial_count,
            'final_count': snapshots[-1]['count'] if snapshots else initial_count,
            'total_growth': snapshots[-1]['count'] - initial_count if snapshots else 0,
            'growth_rate_per_sec': growth_rate,
            'snapshots': snapshots,
            'assessment': self._assess_growth(growth_rate, target_type)
        }
    
    def _count_objects_by_type(self, target_type: str) -> int:
        """统计特定类型的对象数量"""
        count = 0
        for obj in gc.get_objects():
            if type(obj).__name__ == target_type:
                count += 1
        return count
    
    def _assess_growth(self, growth_rate: float, obj_type: str) -> str:
        """评估增长严重性"""
        if growth_rate > 10:
            return f"🚨 严重泄漏: {obj_type} 以 {growth_rate:.1f}/秒的速度增长"
        elif growth_rate > 1:
            return f"⚠️  可能泄漏: {obj_type} 持续增长 ({growth_rate:.1f}/秒)"
        elif growth_rate > 0:
            return f"📈 缓慢增长: {obj_type} ({growth_rate:.1f}/秒)"
        else:
            return f"✅ 稳定: {obj_type} 数量稳定"
    
    def _exit_analysis(self):
        """退出时分析"""
        print("\n" + "="*60)
        print("程序退出 - 内存泄漏最终分析")
        print("="*60)
        
        if len(self.snapshots) >= 2:
            results = self.analyze_growth_patterns()
            if isinstance(results, list) and results:
                print("\n内存增长分析:")
                for result in results:
                    print(f"\n时间段: {result['time_range']}")
                    print(f"对象增长: {result['object_growth']:,} 个")
                    
                    if result['significant_growth']:
                        print("显著增长点:")
                        for growth in result['significant_growth'][:3]:
                            print(f"  +{growth['size_diff_mb']:.1f}MB: {growth['filename']}:{growth['lineno']}")
                            print(f"    代码: {growth['line']}")
        
        # 检查循环引用
        circular = self.find_circular_references()
        if 'garbage_count' in circular and circular['garbage_count'] > 0:
            print(f"\n🚨 发现 {circular['garbage_count']} 个循环引用未清理")
            for item in circular['analysis'][:5]:
                print(f"  {item['type']}: {item['repr']}")
        
        print("\n💡 内存泄漏调查完成")
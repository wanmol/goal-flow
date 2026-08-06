# memory_analyzer_final.py
import gc
import sys
import psutil
import os
import time
from datetime import datetime
from collections import defaultdict, Counter
from typing import Dict, List, Set, Any, Optional, Tuple
import threading

class RealisticMemoryAnalyzer:
    """
    现实的内存分析器 - 综合多种方法，提供准确估算
    
    关键理念：
    1. 不追求绝对准确，而是提供合理范围
    2. 重点关注趋势和相对值
    3. 识别内存异常模式
    4. 避免过度计算导致的性能问题
    """
    
    def __init__(self, app_name: str = "App"):
        self.app_name = app_name
        self.pid = os.getpid()
        self.process = psutil.Process(self.pid)
        self.cache = {}
        self.cache_timeout = 30  # 缓存30秒
        
    def get_memory_analysis(self, method: str = 'balanced') -> Dict:
        """
        获取内存分析（多种方法综合）
        
        Args:
            method: 'fast' - 快速估算
                   'balanced' - 平衡准确性和性能
                   'accurate' - 更准确但较慢
        
        Returns:
            内存分析报告
        """
        gc.collect()
        
        # 获取实际进程内存
        actual_mem = self._get_actual_memory()
        
        # 根据方法选择分析策略
        if method == 'fast':
            analysis = self._fast_analysis()
            accuracy = 'low'
            
        elif method == 'accurate':
            analysis = self._accurate_analysis()
            accuracy = 'high'
            
        else:  # balanced
            analysis = self._balanced_analysis()
            accuracy = 'medium'
        
        # 计算差异和效率
        estimated = analysis.get('estimated_total_bytes', 0)
        actual = actual_mem['rss_bytes']
        
        if actual > 0:
            efficiency = (estimated / actual) * 100
            difference = actual - estimated
        else:
            efficiency = 0
            difference = 0
        
        # 构建报告
        report = {
            'timestamp': datetime.now().isoformat(),
            'app_name': self.app_name,
            'method': method,
            'accuracy': accuracy,
            'process_memory': actual_mem,
            'analysis': analysis,
            'comparison': {
                'estimated_bytes': estimated,
                'actual_bytes': actual,
                'difference_bytes': difference,
                'difference_mb': difference / (1024 * 1024),
                'efficiency_percentage': efficiency,
                'interpretation': self._interpret_efficiency(efficiency)
            },
            'notes': [
                "注意：Python内存估算存在固有误差",
                "实际内存包含解释器、分配器、库等开销",
                "建议关注内存增长趋势而非绝对值"
            ]
        }
        
        return report
    
    def _get_actual_memory(self) -> Dict:
        """获取实际进程内存"""
        mem_info = self.process.memory_info()
        
        return {
            'rss_bytes': mem_info.rss,
            'rss_mb': mem_info.rss / (1024 * 1024),
            'vms_bytes': mem_info.vms,
            'vms_mb': mem_info.vms / (1024 * 1024),
            'percent': self.process.memory_percent()
        }
    
    def _fast_analysis(self) -> Dict:
        """快速分析（基于抽样）"""
        all_objects = gc.get_objects()
        total_objects = len(all_objects)
        
        if total_objects == 0:
            return {
                'estimated_total_bytes': 0,
                'object_count': 0,
                'method': 'fast_sampling',
                'sample_rate': 0
            }
        
        # 抽样率：对象越多，抽样率越低
        if total_objects > 100000:
            sample_rate = 0.01  # 1%
        elif total_objects > 10000:
            sample_rate = 0.05  # 5%
        elif total_objects > 1000:
            sample_rate = 0.1   # 10%
        else:
            sample_rate = 1.0   # 100%
        
        sample_size = max(100, int(total_objects * sample_rate))
        sample_size = min(sample_size, total_objects)
        
        # 随机抽样
        import random
        sampled_indices = random.sample(range(total_objects), sample_size)
        
        total_sampled_size = 0
        type_counter = Counter()
        
        for idx in sampled_indices:
            obj = all_objects[idx]
            try:
                obj_size = sys.getsizeof(obj)
                total_sampled_size += obj_size
                type_counter[type(obj).__name__] += 1
            except:
                continue
        
        # 估算总数
        avg_size = total_sampled_size / sample_size if sample_size > 0 else 0
        estimated_total = avg_size * total_objects
        
        # 类型统计（基于抽样）
        type_stats = []
        for obj_type, count in type_counter.most_common(10):
            # 估算该类型总数
            estimated_type_count = (count / sample_size) * total_objects
            type_stats.append({
                'type': obj_type,
                'estimated_count': int(estimated_type_count),
                'sampled_count': count
            })
        
        return {
            'estimated_total_bytes': int(estimated_total),
            'estimated_total_mb': estimated_total / (1024 * 1024),
            'object_count': total_objects,
            'sample_size': sample_size,
            'sample_rate': sample_rate,
            'avg_object_size_bytes': avg_size,
            'top_types': type_stats,
            'method': 'fast_sampling'
        }
    
    def _balanced_analysis(self) -> Dict:
        """平衡分析（分层抽样）"""
        all_objects = gc.get_objects()
        total_objects = len(all_objects)
        
        if total_objects == 0:
            return {'estimated_total_bytes': 0, 'object_count': 0}
        
        # 将对象按类型分组
        objects_by_type = defaultdict(list)
        for obj in all_objects:
            try:
                obj_type = type(obj).__name__
                objects_by_type[obj_type].append(obj)
            except:
                continue
        
        # 对每种类型进行抽样
        total_estimated = 0
        type_stats = []
        
        for obj_type, objects in objects_by_type.items():
            type_count = len(objects)
            
            # 确定抽样大小
            if type_count > 1000:
                sample_size = 100
            elif type_count > 100:
                sample_size = 50
            elif type_count > 10:
                sample_size = 10
            else:
                sample_size = type_count
            
            # 抽样计算平均大小
            import random
            if sample_size < type_count:
                sampled = random.sample(objects, sample_size)
            else:
                sampled = objects
            
            type_total = 0
            for obj in sampled:
                try:
                    type_total += sys.getsizeof(obj)
                except:
                    continue
            
            avg_size = type_total / len(sampled) if sampled else 0
            type_estimated = avg_size * type_count
            
            total_estimated += type_estimated
            
            type_stats.append({
                'type': obj_type,
                'count': type_count,
                'estimated_bytes': type_estimated,
                'estimated_mb': type_estimated / (1024 * 1024),
                'avg_bytes': avg_size,
                'sample_size': len(sampled)
            })
        
        # 排序
        type_stats.sort(key=lambda x: x['estimated_bytes'], reverse=True)
        
        return {
            'estimated_total_bytes': int(total_estimated),
            'estimated_total_mb': total_estimated / (1024 * 1024),
            'object_count': total_objects,
            'type_count': len(type_stats),
            'top_types': type_stats[:10],
            'method': 'balanced_stratified_sampling'
        }
    
    def _accurate_analysis(self) -> Dict:
        """准确分析（尝试避免重复计算）"""
        all_objects = gc.get_objects()
        
        # 使用已访问集合避免重复
        visited_ids: Set[int] = set()
        type_stats = defaultdict(lambda: {'count': 0, 'size': 0})
        total_size = 0
        
        # 先处理简单对象
        for obj in all_objects:
            obj_id = id(obj)
            if obj_id in visited_ids:
                continue
            
            obj_type = type(obj).__name__
            
            # 对于容器对象，特殊处理
            if self._is_complex_container(obj):
                # 标记为已访问，稍后处理
                continue
            
            try:
                obj_size = sys.getsizeof(obj)
                visited_ids.add(obj_id)
                
                total_size += obj_size
                type_stats[obj_type]['count'] += 1
                type_stats[obj_type]['size'] += obj_size
            except:
                continue
        
        # 处理容器对象（避免深度递归）
        container_stats = self._analyze_containers_smart(all_objects, visited_ids)
        
        # 合并结果
        for obj_type, data in container_stats.items():
            type_stats[obj_type]['count'] += data['count']
            type_stats[obj_type]['size'] += data['size']
            total_size += data['size']
        
        # 转换为列表
        stats_list = []
        for obj_type, data in type_stats.items():
            stats_list.append({
                'type': obj_type,
                'count': data['count'],
                'estimated_bytes': data['size'],
                'estimated_mb': data['size'] / (1024 * 1024),
                'avg_bytes': data['size'] / data['count'] if data['count'] > 0 else 0
            })
        
        stats_list.sort(key=lambda x: x['estimated_bytes'], reverse=True)
        
        return {
            'estimated_total_bytes': int(total_size),
            'estimated_total_mb': total_size / (1024 * 1024),
            'object_count': len(all_objects),
            'unique_objects_estimated': len(visited_ids),
            'duplication_ratio': 1 - (len(visited_ids) / len(all_objects)) if all_objects else 0,
            'top_types': stats_list[:10],
            'method': 'accurate_unique_calculation'
        }
    
    def _is_complex_container(self, obj: Any) -> bool:
        """判断是否为复杂容器（需要特殊处理）"""
        if isinstance(obj, (list, tuple, dict, set)):
            return True
        if hasattr(obj, '__dict__') and len(obj.__dict__) > 0:
            return True
        return False
    
    def _analyze_containers_smart(self, all_objects: List, visited_ids: Set[int]) -> Dict:
        """智能分析容器对象"""
        container_stats = defaultdict(lambda: {'count': 0, 'size': 0})
        
        # 按类型分组容器
        containers_by_type = defaultdict(list)
        for obj in all_objects:
            obj_id = id(obj)
            if obj_id in visited_ids:
                continue
            
            if self._is_complex_container(obj):
                obj_type = type(obj).__name__
                containers_by_type[obj_type].append(obj)
        
        # 对每种容器类型进行分析
        for obj_type, containers in containers_by_type.items():
            if len(containers) > 100:
                # 大量容器，抽样分析
                import random
                sample = random.sample(containers, min(100, len(containers)))
            else:
                sample = containers
            
            type_total_size = 0
            for container in sample:
                try:
                    # 计算容器本身大小（不递归）
                    container_size = sys.getsizeof(container)
                    container_id = id(container)
                    
                    if container_id not in visited_ids:
                        visited_ids.add(container_id)
                        type_total_size += container_size
                except:
                    continue
            
            # 估算总数
            avg_size = type_total_size / len(sample) if sample else 0
            total_estimated = avg_size * len(containers)
            
            container_stats[obj_type]['count'] = len(containers)
            container_stats[obj_type]['size'] = total_estimated
        
        return container_stats
    
    def _interpret_efficiency(self, efficiency: float) -> str:
        """解释内存效率"""
        if efficiency > 80:
            return "内存使用效率很高，对象内存占进程内存的大部分"
        elif efficiency > 60:
            return "内存使用效率良好"
        elif efficiency > 40:
            return "内存使用效率一般，有一定优化空间"
        elif efficiency > 20:
            return "内存使用效率较低，可能有较多开销"
        else:
            return "内存使用效率很低，建议优化内存使用"
    
    def track_memory_trend(self, interval: int = 60, duration: int = 3600):
        """跟踪内存趋势"""
        trends = []
        start_time = time.time()
        
        while time.time() - start_time < duration:
            analysis = self.get_memory_analysis(method='balanced')
            trends.append({
                'timestamp': analysis['timestamp'],
                'actual_mb': analysis['process_memory']['rss_mb'],
                'estimated_mb': analysis['analysis']['estimated_total_mb'],
                'efficiency': analysis['comparison']['efficiency_percentage']
            })
            
            time.sleep(interval)
        
        return trends
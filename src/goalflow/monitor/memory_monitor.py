# memory_monitor.py
import psutil
import os
import time
import gc
import sys
from collections import defaultdict, Counter
from typing import Dict, List, Optional, Tuple
import threading
from datetime import datetime
import json
import asyncio
from pympler import asizeof

class FastAPIMemoryMonitor:
    def __init__(self, app_name: str = "FastAPI"):
        """
        Initialize the memory monitor

        Args:
            app_name: application name, used for log identification
        """
        self.app_name = app_name
        self.pid = os.getpid()
        self.process = psutil.Process(self.pid)
        self.history = []
        self.leak_detected = False
        self.monitoring = False
        self.monitor_thread = None
        self.stop_event = threading.Event()

        # Configuration
        self.snapshot_limit = 1000  # maximum number of snapshots to keep
        self.leak_threshold_mb = 50  # memory leak threshold (MB)
        self.leak_check_interval = 60  # leak check interval (seconds)

        # Object type statistics cache
        self.type_stats_cache = None
        self.type_stats_timestamp = 0
        self.type_stats_cache_ttl = 30  # cache TTL (seconds)

    def snapshot(self, label: str = None, force_gc: bool = False) -> Dict:
        """
        Take a snapshot of the current memory

        Args:
            label: snapshot label, used to identify the current operation
            force_gc: run a full gc.collect() and count all live objects before
                snapshotting. This is expensive (holds the GIL, walks the whole
                heap) and must NOT be used on the per-request hot path; it is only
                appropriate for explicit leak analysis. Defaults to False.

        Returns:
            Memory data dictionary
        """
        if force_gc:
            gc.collect()

        mem_info = self.process.memory_info()
        memory_data = {
            'timestamp': time.time(),
            'datetime': datetime.now().isoformat(),
            'label': label,
            'rss_mb': mem_info.rss / 1024 / 1024,
            'vms_mb': mem_info.vms / 1024 / 1024,
            'percent': self.process.memory_percent(),
            # len(gc.get_objects()) walks the entire heap; only do it alongside a
            # forced collection so the cheap sampling path stays cheap.
            'objects': len(gc.get_objects()) if force_gc else None,
            'gc_collections': gc.get_count()
        }

        # Limit the history size
        if len(self.history) >= self.snapshot_limit:
            self.history.pop(0)
        self.history.append(memory_data)

        return memory_data

    def get_current_stats(self) -> Dict:
        """Get current memory statistics"""
        return self.snapshot("current")

    def start_background_monitoring(self, interval: int = 5):
        """
        Start the background monitoring thread

        Args:
            interval: monitoring interval (seconds)
        """
        if self.monitoring:
            return

        self.monitoring = True
        self.stop_event.clear()

        def monitor_loop():
            while not self.stop_event.is_set():
                try:
                    self.snapshot("background")
                    time.sleep(interval)
                except Exception as e:
                    print(f"监控线程出错: {e}")

        self.monitor_thread = threading.Thread(
            target=monitor_loop,
            daemon=True,
            name=f"MemoryMonitor-{self.app_name}"
        )
        self.monitor_thread.start()
        print(f"{self.app_name} 内存监控已启动，间隔 {interval} 秒")

    def stop_monitoring(self):
        """Stop monitoring"""
        self.monitoring = False
        self.stop_event.set()
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)

    def analyze_leak(self, window_seconds: int = 300) -> Dict:
        """
        Analyze memory leaks

        Args:
            window_seconds: analysis time window (seconds)

        Returns:
            Leak analysis report
        """
        if len(self.history) < 2:
            return {"error": "需要至少2个快照"}

        # Get snapshots within the time window
        now = time.time()
        window_start = now - window_seconds
        relevant_snapshots = [
            s for s in self.history
            if s['timestamp'] >= window_start
        ]

        if len(relevant_snapshots) < 2:
            return {"error": "时间窗口内数据不足"}

        start = relevant_snapshots[0]
        end = relevant_snapshots[-1]

        rss_growth = end['rss_mb'] - start['rss_mb']
        # Object counts are only captured on forced-GC snapshots; fall back to 0
        # growth when either endpoint didn't record a count (cheap sampling path).
        if start.get('objects') is not None and end.get('objects') is not None:
            obj_growth = end['objects'] - start['objects']
        else:
            obj_growth = 0
        time_range = end['timestamp'] - start['timestamp']

        # Calculate growth rates
        rss_growth_rate = rss_growth / time_range if time_range > 0 else 0
        obj_growth_rate = obj_growth / time_range if time_range > 0 else 0

        # Find large objects
        large_objects = self._find_large_objects(threshold_mb=1)

        # Determine whether there is a leak
        leak_detected = rss_growth > self.leak_threshold_mb
        
        report = {
            "app_name": self.app_name,
            "time_range_seconds": time_range,
            "snapshots_analyzed": len(relevant_snapshots),
            "memory_growth_mb": rss_growth,
            "object_growth": obj_growth,
            "rss_growth_rate_mb_per_sec": rss_growth_rate,
            "object_growth_rate_per_sec": obj_growth_rate,
            "leak_detected": leak_detected,
            "leak_threshold_mb": self.leak_threshold_mb,
            "large_objects_count": len(large_objects),
            "top_large_objects": large_objects[:10],
            "start_time": start['datetime'],
            "end_time": end['datetime']
        }
        
        if leak_detected:
            self.leak_detected = True
            print(f"⚠️  检测到内存泄漏: RSS增长 {rss_growth:.1f} MB")
        
        return report
    
    def _find_large_objects(self, threshold_mb: float = 1) -> List[Dict]:
        """Find large objects exceeding the given threshold"""
        large_objs = []
        try:
            for obj in gc.get_objects():
                try:
                    size = sys.getsizeof(obj)
                    if size > threshold_mb * 1024 * 1024:
                        large_objs.append({
                            'type': type(obj).__name__,
                            'size_mb': size / 1024 / 1024,
                            'id': id(obj),
                            'repr': repr(obj)[:200]  # truncated display
                        })
                except:
                    continue

            # Sort by size
            large_objs.sort(key=lambda x: x['size_mb'], reverse=True)
        except Exception as e:
            print(f"查找大对象时出错: {e}")
        
        return large_objs
    
    def analyze_object_types(self, top_n: int = 10, force_refresh: bool = False) -> Dict:
        """
        Break down memory usage by object type

        Args:
            top_n: return the top N object types
            force_refresh: whether to force a cache refresh

        Returns:
            Object type statistics report
        """
        current_time = time.time()

        # Check whether the cache is still valid
        if (not force_refresh and self.type_stats_cache is not None and
            current_time - self.type_stats_timestamp < self.type_stats_cache_ttl):
            return self.type_stats_cache

        print(f"🔍 开始分析对象类型统计 (top_n={top_n})...")
        start_time = time.time()

        try:
            # Force garbage collection
            gc.collect()

            # Get all objects
            all_objects = gc.get_objects()
            total_objects = len(all_objects)

            # Count object types
            type_counter = Counter()
            type_size_counter = defaultdict(int)
            type_examples = defaultdict(list)

            # Sample limit to avoid performance issues from analyzing too many objects
            max_objects_to_analyze = 500000
            objects_to_analyze = all_objects[:max_objects_to_analyze] if total_objects > max_objects_to_analyze else all_objects

            processed_count = 0
            for obj in objects_to_analyze:
                try:
                    obj_type = type(obj).__name__
                    obj_size = asizeof.asizeof(obj)

                    type_counter[obj_type] += 1
                    type_size_counter[obj_type] += obj_size

                    # Collect examples (at most 3 per type)
                    if len(type_examples[obj_type]) < 3:
                        type_examples[obj_type].append({
                            'id': id(obj),
                            'repr': repr(obj)[:800] if hasattr(obj, '__repr__') else str(obj)[:800],
                            'size_bytes': obj_size
                        })

                    processed_count += 1

                except Exception as e:
                    # Skip objects that cannot be processed
                    continue

            # Compute statistics
            total_memory_bytes = sum(type_size_counter.values())
            total_memory_mb = total_memory_bytes / (1024 * 1024)

            # Sort by memory usage
            sorted_types = sorted(
                type_size_counter.items(),
                key=lambda x: x[1],
                reverse=True
            )

            # Build the result
            type_stats = []
            for obj_type, total_size_bytes in sorted_types[:top_n]:
                count = type_counter[obj_type]
                size_mb = total_size_bytes / (1024 * 1024)
                percentage = (total_size_bytes / total_memory_bytes * 100) if total_memory_bytes > 0 else 0

                # Get module info
                module_name = "unknown"
                try:
                    module_name = obj.__class__.__module__ if hasattr(obj, '__class__') else "builtins"
                except:
                    # Try to get it from the examples
                    if type_examples[obj_type]:
                        try:
                            module_name = type_examples[obj_type][0]['repr'].split('<')[1].split('.')[0] if '<' in type_examples[obj_type][0]['repr'] else "unknown"
                        except:
                            pass

                type_stats.append({
                    'type': obj_type,
                    'count': count,
                    'size_bytes': total_size_bytes,
                    'size_mb': round(size_mb, 2),
                    'percentage': round(percentage, 2),
                    'avg_size_bytes': round(total_size_bytes / count, 2) if count > 0 else 0,
                    'module': module_name,
                    'examples': type_examples.get(obj_type, [])
                })

            # Build summary info
            summary = {
                'total_objects': total_objects,
                'analyzed_objects': processed_count,
                'total_memory_bytes': total_memory_bytes,
                'total_memory_mb': round(total_memory_mb, 2),
                'unique_types': len(type_counter),
                'analysis_time_ms': round((time.time() - start_time) * 1000, 2),
                'cache_status': 'fresh' if force_refresh else 'cached'
            }

            # Memory usage distribution analysis
            distribution = {
                'top_5_types_percentage': sum(stat['percentage'] for stat in type_stats[:5]),
                'top_10_types_percentage': sum(stat['percentage'] for stat in type_stats[:10]),
                'other_types_percentage': 100 - sum(stat['percentage'] for stat in type_stats),
                'dominant_type': type_stats[0]['type'] if type_stats else None,
                'dominant_percentage': type_stats[0]['percentage'] if type_stats else 0
            }

            result = {
                'summary': summary,
                'top_types': type_stats,
                'distribution': distribution,
                'timestamp': datetime.now().isoformat()
            }

            # Update the cache
            self.type_stats_cache = result
            self.type_stats_timestamp = current_time

            print(f"✅ 对象类型分析完成: 分析了 {processed_count}/{total_objects} 个对象, "
                  f"总内存 {total_memory_mb:.2f} MB, 耗时 {summary['analysis_time_ms']}ms")

            return result

        except Exception as e:
            error_result = {
                'error': f"分析对象类型时出错: {str(e)}",
                'summary': {
                    'total_objects': 0,
                    'analyzed_objects': 0,
                    'total_memory_bytes': 0,
                    'total_memory_mb': 0,
                    'unique_types': 0,
                    'analysis_time_ms': round((time.time() - start_time) * 1000, 2),
                    'cache_status': 'error'
                },
                'top_types': [],
                'distribution': {},
                'timestamp': datetime.now().isoformat()
            }
            print(f"❌ 对象类型分析失败: {e}")
            return error_result
        
        
    def analyze_object_types2(self, top_n: int = 10, force_refresh: bool = False) -> Dict:
        """
        Break down memory usage by object type

        Args:
            top_n: return the top N object types
            force_refresh: whether to force a cache refresh

        Returns:
            Object type statistics report
        """
        current_time = time.time()

        # Check whether the cache is still valid
        if (not force_refresh and self.type_stats_cache is not None and
            current_time - self.type_stats_timestamp < self.type_stats_cache_ttl):
            return self.type_stats_cache

        print(f"🔍 开始分析对象类型统计 (top_n={top_n})...")
        start_time = time.time()

        try:
            # Force garbage collection
            gc.collect()

            # Get all objects
            all_objects = gc.get_objects()
            total_objects = len(all_objects)

            # Count object types
            type_counter = Counter()
            type_size_counter = defaultdict(int)
            type_examples = defaultdict(list)

            # Sample limit to avoid performance issues from analyzing too many objects
            max_objects_to_analyze = 500000
            objects_to_analyze = all_objects[:max_objects_to_analyze] if total_objects > max_objects_to_analyze else all_objects

            processed_count = 0
            for obj in objects_to_analyze:
                try:
                    obj_type = type(obj).__name__
                    obj_size = asizeof.asizeof(obj)

                    type_counter[obj_type] += 1
                    type_size_counter[obj_type] += obj_size

                    # Collect examples (at most 3 per type)
                    if len(type_examples[obj_type]) < 3:
                        type_examples[obj_type].append({
                            'id': id(obj),
                            'repr': repr(obj)[:800] if hasattr(obj, '__repr__') else str(obj)[:800],
                            'size_bytes': obj_size
                        })

                    processed_count += 1

                except Exception as e:
                    # Skip objects that cannot be processed
                    continue

            # Compute statistics
            total_memory_bytes = sum(type_size_counter.values())
            total_memory_mb = total_memory_bytes / (1024 * 1024)

            # Sort by memory usage
            sorted_types = sorted(
                type_counter.items(),
                key=lambda x: x[1],
                reverse=True
            )

            # Build the result
            type_stats = []
            for obj_type, count in sorted_types[:top_n]:
                count = type_counter[obj_type]
                total_size_bytes = type_size_counter[obj_type]
                size_mb = total_size_bytes / (1024 * 1024)
                percentage = (total_size_bytes / total_memory_bytes * 100) if total_memory_bytes > 0 else 0

                # Get module info
                module_name = "unknown"
                try:
                    module_name = obj.__class__.__module__ if hasattr(obj, '__class__') else "builtins"
                except:
                    # Try to get it from the examples
                    if type_examples[obj_type]:
                        try:
                            module_name = type_examples[obj_type][0]['repr'].split('<')[1].split('.')[0] if '<' in type_examples[obj_type][0]['repr'] else "unknown"
                        except:
                            pass
                
                type_stats.append({
                    'type': obj_type,
                    'count': count,
                    'size_bytes': total_size_bytes,
                    'size_mb': round(size_mb, 2),
                    'percentage': round(percentage, 2),
                    'avg_size_bytes': round(total_size_bytes / count, 2) if count > 0 else 0,
                    'module': module_name,
                    'examples': type_examples.get(obj_type, [])
                })
            
            # Build summary info
            summary = {
                'total_objects': total_objects,
                'analyzed_objects': processed_count,
                'total_memory_bytes': total_memory_bytes,
                'total_memory_mb': round(total_memory_mb, 2),
                'unique_types': len(type_counter),
                'analysis_time_ms': round((time.time() - start_time) * 1000, 2),
                'cache_status': 'fresh' if force_refresh else 'cached'
            }

            # Memory usage distribution analysis
            distribution = {
                'top_5_types_percentage': sum(stat['percentage'] for stat in type_stats[:5]),
                'top_10_types_percentage': sum(stat['percentage'] for stat in type_stats[:10]),
                'other_types_percentage': 100 - sum(stat['percentage'] for stat in type_stats),
                'dominant_type': type_stats[0]['type'] if type_stats else None,
                'dominant_percentage': type_stats[0]['percentage'] if type_stats else 0
            }

            result = {
                'summary': summary,
                'top_types': type_stats,
                'distribution': distribution,
                'timestamp': datetime.now().isoformat()
            }

            # Update the cache
            self.type_stats_cache = result
            self.type_stats_timestamp = current_time

            print(f"✅ 对象类型分析完成: 分析了 {processed_count}/{total_objects} 个对象, "
                  f"总内存 {total_memory_mb:.2f} MB, 耗时 {summary['analysis_time_ms']}ms")

            return result

        except Exception as e:
            error_result = {
                'error': f"分析对象类型时出错: {str(e)}",
                'summary': {
                    'total_objects': 0,
                    'analyzed_objects': 0,
                    'total_memory_bytes': 0,
                    'total_memory_mb': 0,
                    'unique_types': 0,
                    'analysis_time_ms': round((time.time() - start_time) * 1000, 2),
                    'cache_status': 'error'
                },
                'top_types': [],
                'distribution': {},
                'timestamp': datetime.now().isoformat()
            }
            print(f"❌ 对象类型分析失败: {e}")
            return error_result

    def get_type_statistics_history(self, limit: int = 20) -> List[Dict]:
        """
        Get the object type statistics history

        Args:
            limit: limit on the number of history records returned

        Returns:
            History statistics records
        """
        # This could be extended to store historical type statistics
        # For now it returns the most recent analysis result
        current_stats = self.analyze_object_types(top_n=10, force_refresh=False)

        # Simplified history record format
        history_entry = {
            'timestamp': current_stats['timestamp'],
            'summary': current_stats['summary'],
            'dominant_type': current_stats['distribution']['dominant_type'],
            'dominant_percentage': current_stats['distribution']['dominant_percentage']
        }
        
        return [history_entry]
    
    def find_objects_by_type(self, target_type: str, limit: int = 20) -> Dict:
        """
        Find objects of a specified type

        Args:
            target_type: name of the target object type
            limit: limit on the number of objects returned

        Returns:
            List of matching objects
        """
        print(f"🔍 查找类型为 '{target_type}' 的对象...")
        start_time = time.time()
        
        try:
            gc.collect()
            all_objects = gc.get_objects()
            
            matching_objects = []
            total_size_bytes = 0
            
            for obj in all_objects:
                try:
                    if type(obj).__name__ == target_type:
                        obj_size = sys.getsizeof(obj)
                        
                        obj_info = {
                            'id': id(obj),
                            'size_bytes': obj_size,
                            'size_mb': round(obj_size / (1024 * 1024), 4),
                            'repr': repr(obj)[:200] if hasattr(obj, '__repr__') else str(obj)[:200],
                            'str': str(obj)[:100] if hasattr(obj, '__str__') else ''
                        }
                        
                        matching_objects.append(obj_info)
                        total_size_bytes += obj_size
                        
                        if len(matching_objects) >= limit:
                            break
                            
                except Exception:
                    continue
            
            result = {
                'type': target_type,
                'count': len(matching_objects),
                'total_size_bytes': total_size_bytes,
                'total_size_mb': round(total_size_bytes / (1024 * 1024), 2),
                'objects': matching_objects,
                'analysis_time_ms': round((time.time() - start_time) * 1000, 2),
                'timestamp': datetime.now().isoformat()
            }
            
            print(f"✅ 找到 {len(matching_objects)} 个类型为 '{target_type}' 的对象, "
                  f"总大小 {result['total_size_mb']:.2f} MB")
            
            return result
            
        except Exception as e:
            error_result = {
                'error': f"查找对象时出错: {str(e)}",
                'type': target_type,
                'count': 0,
                'total_size_bytes': 0,
                'total_size_mb': 0,
                'objects': [],
                'analysis_time_ms': round((time.time() - start_time) * 1000, 2),
                'timestamp': datetime.now().isoformat()
            }
            print(f"❌ 查找对象失败: {e}")
            return error_result
    
    def get_history_summary(self) -> Dict:
        """Get a summary of the history"""
        if not self.history:
            return {"error": "没有历史数据"}
        
        return {
            "total_snapshots": len(self.history),
            "first_timestamp": self.history[0]['datetime'],
            "last_timestamp": self.history[-1]['datetime'],
            "min_rss_mb": min(s['rss_mb'] for s in self.history),
            "max_rss_mb": max(s['rss_mb'] for s in self.history),
            "avg_rss_mb": sum(s['rss_mb'] for s in self.history) / len(self.history)
        }
    
    def clear_history(self):
        """Clear the history"""
        self.history.clear()
        self.type_stats_cache = None
        print("历史记录已清空")

    def clear_type_stats_cache(self):
        """Clear the type statistics cache"""
        self.type_stats_cache = None
        print("类型统计缓存已清空")

# Global monitor instance
memory_monitor = None

def init_memory_monitor(app_name: str = "FastAPI"):
    """Initialize the global memory monitor"""
    global memory_monitor
    if memory_monitor is None:
        memory_monitor = FastAPIMemoryMonitor(app_name)
    return memory_monitor

def get_memory_monitor() -> FastAPIMemoryMonitor:
    """Get the global memory monitor"""
    if memory_monitor is None:
        raise RuntimeError("内存监控器未初始化，请先调用 init_memory_monitor")
    return memory_monitor
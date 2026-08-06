# memory_routes_accurate.py
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from datetime import datetime
from typing import Optional,List

from goalflow.monitor.memory_analyzer_final import RealisticMemoryAnalyzer

router = APIRouter(prefix="/api/memory", tags=["内存监控-准确"])

# 创建分析器实例
_analyzer = None

def get_analyzer():
    global _analyzer
    if _analyzer is None:
        _analyzer = RealisticMemoryAnalyzer("FastAPI-App")
    return _analyzer

@router.get("/analysis/accurate", summary="准确内存分析")
async def accurate_memory_analysis(
    method: str = Query("balanced", description="分析方法: fast|balanced|accurate"),
    force_refresh: bool = Query(False, description="强制刷新缓存"),
    analyzer=Depends(get_analyzer)
):
    """
    获取准确的内存分析报告
    
    使用多种方法综合估算Python对象内存占用，
    避免asizeof和简单相加的误差。
    """
    try:
        # 清空缓存如果需要
        if force_refresh:
            analyzer.cache.clear()
        
        report = analyzer.get_memory_analysis(method=method)
        
        return {
            "success": True,
            "data": report,
            "disclaimer": "内存估算存在固有误差，建议关注趋势而非绝对值",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"内存分析失败: {str(e)}")

@router.get("/analysis/efficiency", summary="内存效率分析")
async def memory_efficiency_analysis(
    window_minutes: int = Query(5, description="分析时间窗口（分钟）"),
    analyzer=Depends(get_analyzer)
):
    """
    分析内存使用效率
    
    计算Python对象内存占进程总内存的比例，
    识别内存使用效率问题。
    """
    analyzer: RealisticMemoryAnalyzer = analyzer
    try:
        # 多次采样分析
        import time
        
        samples = []
        for _ in range(3):
            report = analyzer.get_memory_analysis(method='balanced')
            efficiency = report['comparison']['efficiency_percentage']
            
            samples.append({
                'timestamp': report['timestamp'],
                'efficiency': efficiency,
                'actual_mb': report['process_memory']['rss_mb'],
                'estimated_mb': report['analysis']['estimated_total_mb']
            })
            
            time.sleep(1)  # 间隔1秒
        
        # 计算平均值
        avg_efficiency = sum(s['efficiency'] for s in samples) / len(samples)
        
        return {
            "success": True,
            "data": {
                "samples": samples,
                "average_efficiency": avg_efficiency,
                "interpretation": analyzer._interpret_efficiency(avg_efficiency),
                "recommendations": _get_efficiency_recommendations(avg_efficiency)
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"效率分析失败: {str(e)}")

def _get_efficiency_recommendations(self, efficiency: float) -> List[str]:
    """根据效率给出优化建议"""
    recommendations = []
    
    if efficiency < 30:
        recommendations.extend([
            "内存效率低于30%，建议：",
            "1. 检查是否有大量小对象（考虑使用__slots__）",
            "2. 减少临时对象创建",
            "3. 使用更紧凑的数据结构（array, numpy）",
            "4. 实施对象池或缓存",
            "5. 考虑使用C扩展处理大数据"
        ])
    elif efficiency < 50:
        recommendations.extend([
            "内存效率一般，建议：",
            "1. 优化数据结构选择",
            "2. 减少对象复制",
            "3. 及时释放不再使用的对象"
        ])
    else:
        recommendations.append("内存效率良好，继续保持")
    
    return recommendations

@router.get("/analysis/trend", summary="内存趋势分析")
async def memory_trend_analysis(
    interval_seconds: int = Query(10, description="采样间隔（秒）", ge=5, le=300),
    samples: int = Query(6, description="采样次数", ge=1, le=60),
    analyzer=Depends(get_analyzer)
):
    """
    分析内存使用趋势
    
    多次采样分析内存变化趋势。
    """
    try:
        import time
        
        trends = []
        for i in range(samples):
            report = analyzer.get_memory_analysis(method='fast')
            
            trends.append({
                'sample': i + 1,
                'timestamp': report['timestamp'],
                'actual_mb': report['process_memory']['rss_mb'],
                'estimated_mb': report['analysis']['estimated_total_mb'],
                'efficiency': report['comparison']['efficiency_percentage'],
                'object_count': report['analysis']['object_count']
            })
            
            if i < samples - 1:  # 最后一次不等待
                time.sleep(interval_seconds)
        
        # 分析趋势
        if len(trends) >= 2:
            first = trends[0]
            last = trends[-1]
            
            actual_change = last['actual_mb'] - first['actual_mb']
            estimated_change = last['estimated_mb'] - first['estimated_mb']
            object_change = last['object_count'] - first['object_count']
            
            trend_analysis = {
                'actual_change_mb': actual_change,
                'estimated_change_mb': estimated_change,
                'object_count_change': object_change,
                'leak_suspected': actual_change > 10 and object_change > 1000,
                'trend': 'stable' if abs(actual_change) < 5 else 'growing' if actual_change > 0 else 'shrinking'
            }
        else:
            trend_analysis = {'message': '样本不足，无法分析趋势'}
        
        return {
            "success": True,
            "data": {
                "trends": trends,
                "analysis": trend_analysis,
                "sampling": {
                    "interval_seconds": interval_seconds,
                    "samples": samples,
                    "duration_seconds": interval_seconds * (samples - 1)
                }
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"趋势分析失败: {str(e)}")
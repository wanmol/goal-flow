# memory_routes.py
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, HTMLResponse
from typing import Optional, List
#import plotly.graph_objects as go
#import plotly.express as px
import pandas as pd
from datetime import datetime, timedelta

from goalflow.monitor.memory_monitor import get_memory_monitor, FastAPIMemoryMonitor

from goalflow.monitor.leak_detector import QuickLeakDetector
from goalflow.monitor.framework_leak_checker import FrameworkLeakChecker

router = APIRouter(prefix="/api/memory", tags=["内存监控"])

# 依赖注入
def get_monitor():
    try:
        return get_memory_monitor()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"监控器获取失败: {str(e)}")

@router.get("/types/stats/{top_n}", summary="按对象类型统计内存占用")
async def get_object_type_stats(
    top_n: int = 20,
    force_refresh: bool =False,
    include_examples: bool = False,
    monitor=Depends(get_monitor)
):
    """
    按对象类型统计内存占用大小
    
    返回内存占用最大的前N种对象类型的统计信息，
    包括每种类型的数量、总内存占用、平均大小等。
    """
    monitor : FastAPIMemoryMonitor = monitor
    try:
        stats = monitor.analyze_object_types(top_n=top_n, force_refresh=force_refresh)
        
        # 如果不包含示例，则从结果中移除
        if not include_examples and 'top_types' in stats:
            for type_stat in stats['top_types']:
                if 'examples' in type_stat:
                    del type_stat['examples']
        
        return {
            "success": True,
            "data": stats,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"对象类型统计失败: {str(e)}")
    
@router.get("/types/stats2/{top_n}", summary="按对象类型统计内存占用")
async def get_object_type_stats2(
    top_n: int = 20,
    force_refresh: bool =False,
    include_examples: bool = False,
    monitor=Depends(get_monitor)
):
    """
    按对象类型统计内存占用大小
    
    返回内存占用最大的前N种对象类型的统计信息，
    包括每种类型的数量、总内存占用、平均大小等。
    """
    monitor : FastAPIMemoryMonitor = monitor
    try:
        stats = monitor.analyze_object_types2(top_n=top_n, force_refresh=force_refresh)
        
        # 如果不包含示例，则从结果中移除
        if not include_examples and 'top_types' in stats:
            for type_stat in stats['top_types']:
                if 'examples' in type_stat:
                    del type_stat['examples']
        
        return {
            "success": True,
            "data": stats,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"对象类型统计失败: {str(e)}")

@router.get("/types/top10", summary="获取内存占用TOP10对象类型")
async def get_top10_object_types(
    force_refresh: bool = Query(False, description="是否强制刷新缓存"),
    monitor=Depends(get_monitor)
):
    """
    获取内存占用最大的前10种对象类型
    
    简化的TOP10接口，返回格式更简洁。
    """
    try:
        stats = monitor.analyze_object_types(top_n=10, force_refresh=force_refresh)
        
        # 简化结果格式
        top10 = []
        for type_stat in stats.get('top_types', []):
            top10.append({
                'rank': len(top10) + 1,
                'type': type_stat['type'],
                'count': type_stat['count'],
                'size_mb': type_stat['size_mb'],
                'percentage': type_stat['percentage'],
                'avg_size_kb': round(type_stat['avg_size_bytes'] / 1024, 2)
            })
        
        return {
            "success": True,
            "summary": stats.get('summary', {}),
            "top10": top10,
            "distribution": stats.get('distribution', {}),
            "timestamp": stats.get('timestamp', datetime.now().isoformat())
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取TOP10失败: {str(e)}")

@router.get("/types/search", summary="查找指定类型的对象")
async def search_objects_by_type(
    type_name: str = Query(..., description="要查找的对象类型名称"),
    limit: int = 20,
    monitor=Depends(get_monitor)
):
    """
    查找指定类型的所有对象
    
    返回指定类型的所有对象实例，包含每个对象的大小和表示。
    """
    monitor : FastAPIMemoryMonitor = monitor
    try:
        result = monitor.find_objects_by_type(target_type=type_name, limit=limit)
        
        if 'error' in result:
            return {
                "success": False,
                "error": result['error'],
                "data": result
            }
        
        return {
            "success": True,
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查找对象失败: {str(e)}")

@router.get("/types/common", summary="获取常见对象类型统计")
async def get_common_object_types(monitor=Depends(get_monitor)):
    """
    获取常见对象类型的统计
    
    返回一些预定义的常见对象类型的统计信息。
    """
    try:
        # 预定义的常见类型
        common_types = [
            'list', 'dict', 'str', 'tuple', 'int', 'float', 
            'bytes', 'bytearray', 'set', 'function', 'type',
            'module', 'instance', 'ndarray', 'DataFrame', 'Series'
        ]
        
        # 获取完整统计
        full_stats = monitor.analyze_object_types(top_n=50, force_refresh=False)
        
        # 筛选常见类型
        common_stats = []
        for type_stat in full_stats.get('top_types', []):
            if type_stat['type'] in common_types:
                common_stats.append(type_stat)
        
        # 添加缺失的常见类型（即使不在TOP50中）
        found_types = {stat['type'] for stat in common_stats}
        for missing_type in set(common_types) - found_types:
            # 尝试单独查找
            try:
                result = monitor.find_objects_by_type(target_type=missing_type, limit=1)
                if result['count'] > 0:
                    common_stats.append({
                        'type': missing_type,
                        'count': result['count'],
                        'size_bytes': result['total_size_bytes'],
                        'size_mb': result['total_size_mb'],
                        'percentage': 0,  # 需要计算
                        'avg_size_bytes': result['total_size_bytes'] / result['count'] if result['count'] > 0 else 0,
                        'module': 'unknown',
                        'examples': []
                    })
            except:
                continue
        
        # 重新计算百分比
        total_memory = full_stats['summary']['total_memory_bytes']
        for stat in common_stats:
            if total_memory > 0:
                stat['percentage'] = round(stat['size_bytes'] / total_memory * 100, 2)
        
        # 按大小排序
        common_stats.sort(key=lambda x: x['size_bytes'], reverse=True)
        
        return {
            "success": True,
            "data": {
                "common_types": common_stats,
                "total_common_memory_mb": sum(stat['size_mb'] for stat in common_stats),
                "total_common_percentage": sum(stat['percentage'] for stat in common_stats),
                "timestamp": datetime.now().isoformat()
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取常见类型统计失败: {str(e)}")

# @router.get("/types/visualization", summary="对象类型内存分布可视化")
# async def visualize_object_types(
#     top_n: int = Query(10, description="显示前N种对象类型", ge=1, le=20),
#     chart_type: str = Query("pie", description="图表类型: pie, bar, sunburst"),
#     monitor=Depends(get_monitor)
# ):
#     """
#     生成对象类型内存分布的可视化图表
    
#     返回HTML格式的图表页面。
#     """
#     try:
#         stats = monitor.analyze_object_types(top_n=top_n, force_refresh=False)
        
#         if not stats.get('top_types'):
#             return HTMLResponse(content="<h3>暂无数据</h3>")
        
#         # 准备数据
#         types = [t['type'] for t in stats['top_types']]
#         sizes_mb = [t['size_mb'] for t in stats['top_types']]
#         percentages = [t['percentage'] for t in stats['top_types']]
#         counts = [t['count'] for t in stats['top_types']]
        
#         # 创建图表
#         if chart_type == "pie":
#             fig = go.Figure(data=[go.Pie(
#                 labels=types,
#                 values=sizes_mb,
#                 textinfo='label+percent',
#                 texttemplate='%{label}<br>%{percent:.1%}<br>%{value:.1f} MB',
#                 hoverinfo='label+value+percent',
#                 hovertemplate='<b>%{label}</b><br>大小: %{value:.1f} MB<br>占比: %{percent:.1%}<br>数量: %{customdata}',
#                 customdata=counts
#             )])
            
#             fig.update_layout(
#                 title=f'对象类型内存占用分布 (TOP{top_n})',
#                 height=600
#             )
            
#         elif chart_type == "bar":
#             fig = go.Figure()
            
#             # 添加内存大小柱状图
#             fig.add_trace(go.Bar(
#                 x=types,
#                 y=sizes_mb,
#                 name='内存大小 (MB)',
#                 text=[f'{s:.1f} MB' for s in sizes_mb],
#                 textposition='auto',
#                 marker_color='lightblue'
#             ))
            
#             # 添加对象数量线图（次坐标轴）
#             fig.add_trace(go.Scatter(
#                 x=types,
#                 y=counts,
#                 name='对象数量',
#                 yaxis='y2',
#                 line=dict(color='red', width=2),
#                 marker=dict(size=8)
#             ))
            
#             fig.update_layout(
#                 title=f'对象类型内存占用详情 (TOP{top_n})',
#                 xaxis_title='对象类型',
#                 yaxis=dict(
#                     title='内存大小 (MB)',
#                     titlefont=dict(color='lightblue'),
#                     tickfont=dict(color='lightblue')
#                 ),
#                 yaxis2=dict(
#                     title='对象数量',
#                     titlefont=dict(color='red'),
#                     tickfont=dict(color='red'),
#                     anchor='x',
#                     overlaying='y',
#                     side='right'
#                 ),
#                 height=600
#             )
            
#         elif chart_type == "sunburst":
#             # 为sunburst图准备层次数据
#             labels = []
#             parents = []
#             values = []
            
#             # 添加根节点
#             labels.append('All Objects')
#             parents.append('')
#             values.append(stats['summary']['total_memory_mb'])
            
#             # 添加类型节点
#             for type_stat in stats['top_types']:
#                 labels.append(type_stat['type'])
#                 parents.append('All Objects')
#                 values.append(type_stat['size_mb'])
                
#                 # 添加详细信息作为子节点
#                 labels.append(f"{type_stat['type']}_details")
#                 parents.append(type_stat['type'])
#                 values.append(type_stat['size_mb'])
            
#             fig = go.Figure(go.Sunburst(
#                 labels=labels,
#                 parents=parents,
#                 values=values,
#                 branchvalues="total",
#                 hovertemplate='<b>%{label}</b><br>大小: %{value:.1f} MB<br>占比: %{percentParent:.1%}',
#                 textinfo='label+percent parent'
#             ))
            
#             fig.update_layout(
#                 title=f'对象类型内存占用层级图 (TOP{top_n})',
#                 height=600
#             )
        
#         # 生成HTML
#         plot_html = fig.to_html(full_html=False, include_plotlyjs='cdn')
        
#         # 构建摘要信息
#         summary = stats['summary']
#         distribution = stats['distribution']
        
#         html_content = f"""
#         <!DOCTYPE html>
#         <html>
#         <head>
#             <title>对象类型内存分布可视化</title>
#             <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
#             <style>
#                 body {{ font-family: Arial, sans-serif; margin: 20px; }}
#                 .container {{ max-width: 1200px; margin: 0 auto; }}
#                 .summary {{ 
#                     background: #f8f9fa; 
#                     padding: 20px; 
#                     border-radius: 10px; 
#                     margin-bottom: 20px; 
#                     border-left: 5px solid #007bff;
#                 }}
#                 .stats-grid {{ 
#                     display: grid; 
#                     grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); 
#                     gap: 15px; 
#                     margin: 20px 0;
#                 }}
#                 .stat-card {{ 
#                     background: white; 
#                     padding: 15px; 
#                     border-radius: 8px; 
#                     box-shadow: 0 2px 4px rgba(0,0,0,0.1);
#                     text-align: center;
#                 }}
#                 .stat-value {{ 
#                     font-size: 24px; 
#                     font-weight: bold; 
#                     color: #007bff;
#                     margin: 10px 0;
#                 }}
#                 .stat-label {{ 
#                     color: #6c757d; 
#                     font-size: 14px;
#                 }}
#                 .chart-controls {{ 
#                     margin: 20px 0; 
#                     padding: 15px; 
#                     background: #e9ecef; 
#                     border-radius: 8px;
#                 }}
#                 .control-group {{ 
#                     display: flex; 
#                     gap: 10px; 
#                     align-items: center;
#                     margin-bottom: 10px;
#                 }}
#                 .nav {{ 
#                     margin: 20px 0; 
#                     display: flex; 
#                     gap: 15px; 
#                     flex-wrap: wrap;
#                 }}
#                 .nav a {{ 
#                     padding: 8px 16px; 
#                     background: #007bff; 
#                     color: white; 
#                     text-decoration: none;
#                     border-radius: 4px;
#                 }}
#                 .nav a:hover {{ background: #0056b3; }}
#                 table {{ 
#                     width: 100%; 
#                     border-collapse: collapse; 
#                     margin: 20px 0;
#                 }}
#                 th, td {{ 
#                     padding: 10px; 
#                     text-align: left; 
#                     border-bottom: 1px solid #dee2e6;
#                 }}
#                 th {{ background: #f8f9fa; }}
#                 tr:hover {{ background: #f8f9fa; }}
#             </style>
#         </head>
#         <body>
#             <div class="container">
#                 <h1>对象类型内存分布可视化</h1>
                
#                 <div class="nav">
#                     <a href="/api/memory/types/top10">TOP10对象类型</a>
#                     <a href="/api/memory/types/common">常见类型统计</a>
#                     <a href="/api/memory/dashboard">内存监控仪表板</a>
#                     <a href="/api/memory/objects/large">大对象分析</a>
#                 </div>
                
#                 <div class="summary">
#                     <h2>分析摘要</h2>
#                     <div class="stats-grid">
#                         <div class="stat-card">
#                             <div class="stat-label">总内存</div>
#                             <div class="stat-value">{summary.get('total_memory_mb', 0):.1f} MB</div>
#                         </div>
#                         <div class="stat-card">
#                             <div class="stat-label">对象总数</div>
#                             <div class="stat-value">{summary.get('total_objects', 0):,}</div>
#                         </div>
#                         <div class="stat-card">
#                             <div class="stat-label">分析对象数</div>
#                             <div class="stat-value">{summary.get('analyzed_objects', 0):,}</div>
#                         </div>
#                         <div class="stat-card">
#                             <div class="stat-label">唯一类型数</div>
#                             <div class="stat-value">{summary.get('unique_types', 0):,}</div>
#                         </div>
#                         <div class="stat-card">
#                             <div class="stat-label">分析耗时</div>
#                             <div class="stat-value">{summary.get('analysis_time_ms', 0)} ms</div>
#                         </div>
#                         <div class="stat-card">
#                             <div class="stat-label">缓存状态</div>
#                             <div class="stat-value">{summary.get('cache_status', 'unknown')}</div>
#                         </div>
#                     </div>
                    
#                     <div class="stats-grid">
#                         <div class="stat-card">
#                             <div class="stat-label">TOP5类型占比</div>
#                             <div class="stat-value">{distribution.get('top_5_types_percentage', 0):.1f}%</div>
#                         </div>
#                         <div class="stat-card">
#                             <div class="stat-label">TOP10类型占比</div>
#                             <div class="stat-value">{distribution.get('top_10_types_percentage', 0):.1f}%</div>
#                         </div>
#                         <div class="stat-card">
#                             <div class="stat-label">其他类型占比</div>
#                             <div class="stat-value">{distribution.get('other_types_percentage', 0):.1f}%</div>
#                         </div>
#                         <div class="stat-card">
#                             <div class="stat-label">主导类型</div>
#                             <div class="stat-value">{distribution.get('dominant_type', 'N/A')}</div>
#                         </div>
#                         <div class="stat-card">
#                             <div class="stat-label">主导类型占比</div>
#                             <div class="stat-value">{distribution.get('dominant_percentage', 0):.1f}%</div>
#                         </div>
#                     </div>
#                 </div>
                
#                 <div class="chart-controls">
#                     <h3>图表控制</h3>
#                     <div class="control-group">
#                         <label>图表类型:</label>
#                         <select id="chartType" onchange="updateChart()">
#                             <option value="pie" {'selected' if chart_type == 'pie' else ''}>饼图</option>
#                             <option value="bar" {'selected' if chart_type == 'bar' else ''}>柱状图</option>
#                             <option value="sunburst" {'selected' if chart_type == 'sunburst' else ''}>旭日图</option>
#                         </select>
#                         <label>显示类型数:</label>
#                         <select id="topN" onchange="updateChart()">
#                             <option value="5" {'selected' if top_n == 5 else ''}>5</option>
#                             <option value="10" {'selected' if top_n == 10 else ''}>10</option>
#                             <option value="15" {'selected' if top_n == 15 else ''}>15</option>
#                             <option value="20" {'selected' if top_n == 20 else ''}>20</option>
#                         </select>
#                         <button onclick="refreshData()">刷新数据</button>
#                     </div>
#                 </div>
                
#                 <div id="plot">{plot_html}</div>
                
#                 <h3>详细数据表</h3>
#                 <table>
#                     <thead>
#                         <tr>
#                             <th>排名</th>
#                             <th>对象类型</th>
#                             <th>数量</th>
#                             <th>总内存 (MB)</th>
#                             <th>占比 (%)</th>
#                             <th>平均大小 (KB)</th>
#                             <th>模块</th>
#                         </tr>
#                     </thead>
#                     <tbody>
#         """
        
#         # 添加表格行
#         for i, type_stat in enumerate(stats['top_types']):
#             html_content += f"""
#                         <tr>
#                             <td>{i + 1}</td>
#                             <td><strong>{type_stat['type']}</strong></td>
#                             <td>{type_stat['count']:,}</td>
#                             <td>{type_stat['size_mb']:.1f}</td>
#                             <td>{type_stat['percentage']:.1f}%</td>
#                             <td>{type_stat['avg_size_bytes'] / 1024:.1f}</td>
#                             <td>{type_stat.get('module', 'unknown')}</td>
#                         </tr>
#             """
        
#         html_content += """
#                     </tbody>
#                 </table>
                
#                 <script>
#                     function updateChart() {
#                         const chartType = document.getElementById('chartType').value;
#                         const topN = document.getElementById('topN').value;
#                         window.location.href = `/api/memory/types/visualization?chart_type=${chartType}&top_n=${topN}`;
#                     }
                    
#                     function refreshData() {
#                         window.location.href = `/api/memory/types/visualization?chart_type=${document.getElementById('chartType').value}&top_n=${document.getElementById('topN').value}&force_refresh=true`;
#                     }
                    
#                     // 每30秒自动刷新数据
#                     setTimeout(() => {
#                         refreshData();
#                     }, 30000);
#                 </script>
#             </div>
#         </body>
#         </html>
#         """
        
#         return HTMLResponse(content=html_content)
        
#     except Exception as e:
#         error_html = f"""
#         <html>
#             <head><title>可视化错误</title></head>
#             <body>
#                 <h1>对象类型可视化</h1>
#                 <p style="color: red;">错误: {str(e)}</p>
#                 <button onclick="window.location.reload()">重试</button>
#             </body>
#         </html>
#         """
#         return HTMLResponse(content=error_html)

@router.get("/types/history", summary="对象类型统计历史")
async def get_object_type_history(
    limit: int = Query(10, description="返回的历史记录数量", ge=1, le=100),
    monitor=Depends(get_monitor)
):
    """
    获取对象类型统计的历史记录
    
    返回最近的对象类型统计历史。
    """
    try:
        history = monitor.get_type_statistics_history(limit=limit)
        
        return {
            "success": True,
            "data": {
                "count": len(history),
                "history": history
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取类型统计历史失败: {str(e)}")

@router.post("/types/cache/clear", summary="清空类型统计缓存")
async def clear_type_stats_cache(monitor=Depends(get_monitor)):
    """
    清空对象类型统计的缓存
    
    强制下次请求重新分析对象类型。
    """
    try:
        monitor.clear_type_stats_cache()
        return {
            "success": True,
            "message": "类型统计缓存已清空",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"清空缓存失败: {str(e)}")

# 保留原有的其他端点...
# [这里保留原有的所有其他路由函数，如/status, /history, /analyze等]

# 更新仪表板，添加类型统计链接
@router.get("/dashboard", response_class=HTMLResponse, summary="内存监控仪表板")
async def memory_dashboard(monitor=Depends(get_monitor)):
    """内存监控仪表板页面"""
    try:
        # ... [原有的仪表板代码保持不变]
        
        # 在仪表板的导航部分添加类型统计链接
        # 修改导航部分，添加：
        """
        <div class="nav">
            <a href="/api/memory/status">当前状态</a>
            <a href="/api/memory/types/top10">对象类型TOP10</a>
            <a href="/api/memory/types/visualization">类型可视化</a>
            <a href="/api/memory/analyze">泄漏分析</a>
            <a href="/api/memory/objects/large">大对象</a>
            <a href="/api/memory/gc/stats">GC统计</a>
            <a href="/health">健康检查</a>
            <a href="/system/status">系统状态</a>
        </div>
        """
        
        # ... [其余原有代码]
        
    except Exception as e:
        # ... [原有的错误处理]
        pass
    

@router.get("/status", summary="获取当前内存状态")
async def get_memory_status():
    """获取当前内存使用情况"""
    monitor = get_memory_monitor()
    stats = monitor.get_current_stats()
    return stats

@router.get("/history", summary="获取内存历史记录")
async def get_memory_history(limit: int = 50):
    """获取最近的内存历史记录"""
    monitor = get_memory_monitor()
    history = monitor.history[-limit:] if limit > 0 else monitor.history
    return {
        "count": len(history),
        "history": history
    }
    
@router.get("/analyze", summary="分析内存泄漏")
async def analyze_memory_leak(
    window_seconds: int = 180,
    threshold_mb: float = 10
):
    """分析指定时间窗口内的内存泄漏情况"""
    monitor = get_memory_monitor()
    monitor.leak_threshold_mb = threshold_mb
    report = monitor.analyze_leak(window_seconds)
    return report

@router.get("/objects/large/{threshold_mb}", summary="查找大对象")
async def find_large_objects(threshold_mb: float = 1):
    """查找内存中的大对象"""
    monitor = get_memory_monitor()
    large_objects = monitor._find_large_objects(threshold_mb)
    return {
        "threshold_mb": threshold_mb,
        "count": len(large_objects),
        "objects": large_objects
    }
    
@router.get("/gc/stats", summary="获取GC统计")
async def get_gc_stats():
    """获取垃圾回收统计信息"""
    import gc
    return {
        "enabled": gc.isenabled(),
        "threshold": gc.get_threshold(),
        "count": gc.get_count(),
        "objects_tracked": len(gc.get_objects())
    }
    
@router.post("/gc/collect", summary="手动触发GC")
async def trigger_gc():
    """手动触发垃圾回收"""
    import gc
    collected = gc.collect()
    return {
        "collected": collected,
        "message": "垃圾回收已执行"
    }
    
@router.get("/summary", summary="获取内存摘要")
async def get_memory_summary():
    """获取内存使用摘要"""
    monitor = get_memory_monitor()
    summary = monitor.get_history_summary()
    return summary


@router.get("/leak_detector", summary="内存检查")
async def leak_detector():
    result = QuickLeakDetector.quick_check()
    return result



@router.get("/framework_leak_detector", summary="常见框架内存检查")
async def leak_detector():
    result = FrameworkLeakChecker.check_all_frameworks()
    return result

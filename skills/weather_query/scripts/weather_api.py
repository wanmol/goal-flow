"""
天气查询工具示例脚本。
"""


def get_weather(city: str) -> dict:
    """查询指定城市的天气信息（示例）。"""
    # TODO: 替换为实际的天气 API 调用
    return {
        "city": city,
        "temperature": "25°C",
        "humidity": "60%",
        "wind": "东南风 3 级",
        "condition": "晴",
    }

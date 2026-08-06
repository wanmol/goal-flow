#!/usr/bin/env python3
"""
演示运行脚本 - 提供交互式和批量测试两种模式

<这个最优,选它>
这个输出格式符合要求。需要安装
pip install langchain-tavily
"""
import os
from langchain_tavily import TavilySearch
#from langchain_community.retrievers import TavilySearchAPIRetriever
#from docx import Document

def main():
    os.environ["TAVILY_API_KEY"] = "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"

    # 1. 初始化搜索工具（API Key 优先级：代码指定 > 环境变量）
    search = TavilySearch(
        #api_key="你的Tavily API Key",  # 若已设环境变量可省略
        search_depth="advanced",  # 搜索深度：basic（基础，快）/advanced（高级，全量结果）
        max_results=3,  # 返回最大结果数，默认5，范围1-10
        # 可选：是否返回直接答案（而非仅网页片段，默认False）
        include_answer=True,
        # 可选：是否返回图片结果（默认False）
        include_images=False,
        days=10000,
        country="china",
        exclude_domains=[],
        include_domains=[],
        topic="general",
        time_range="month",

    )

    # 2. 执行搜索（支持中文/英文等多语言）
    query = "2025年北京公积金的提取流程是什么"
    results = search.invoke(query)

    # 3. 输出结果（结构化字符串，可直接喂给LLM）
    print("全文打印开始================================================\n")
    print(results)
    print("全文打印结束================================================\n")

    # 4 解析结果（结构化数据，易处理）
    print("搜索结果总数：", len(results))
'''    for idx, res in enumerate(results, 1):
        print(f"\n===== 结果 {idx} =====")
        print("标题：", res["title"])
        print("链接：", res["url"])
        print("摘要：", res["content"])
        # 若开启 include_answer，会有 AI 总结的答案
        if "answer" in res:
            print("AI 总结答案：", res["answer"])'''

if __name__ == "__main__":
    main()

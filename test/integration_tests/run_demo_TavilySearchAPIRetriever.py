#!/usr/bin/env python3
"""
演示运行脚本 - 提供交互式和批量测试两种模式
这个不需要安装任何包,但输出格式不符合要求
"""
import os
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_community.retrievers import TavilySearchAPIRetriever
from docx import Document

def main():
    os.environ["TAVILY_API_KEY"] = "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"

    # 1. 初始化检索器
    retriever = TavilySearchAPIRetriever(
        # 核心参数：返回的搜索结果数量（默认5）
        k=3,
        # 可选：搜索深度（basic=快速，advanced=深度，默认basic）
        search_depth="advanced",
        # 可选：是否返回Tavily总结的直接答案（默认False）
        include_answer=True,
        # 可选：限定搜索域名（仅返回指定域名结果）
        #include_domains=["gov.cn", "beijing.gov.cn"],
        # 可选：排除搜索域名
        exclude_domains=["weibo.com"],
        # 可选：限定时间范围（1d=1天，1w=1周，1m=1月，1y=1年）
        time_range="1m",
    )

    # 2. 核心调用：检索与用户查询相关的实时文档
    # 方式1：同步检索（最常用）
    docs = retriever.invoke("2025年北京新能源汽车上牌政策")

    print("全文打印开始======================\n")
    full_text = "\n\n".join(doc.page_content for doc in docs)
    print(full_text)
    print("全文打结束========================\n")

    # 3. 解析返回的Document对象
    for i, doc in enumerate(docs):
        print(f"\n=== 检索结果 {i+1} ===")
        print(f"标题：{doc.metadata.get('title', '无')}")
        print(f"URL：{doc.metadata.get('url', '无')}")
        print(f"内容：{doc.page_content[:200]}...")  # 截取前200字

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
演示运行脚本 - 提供交互式和批量测试两种模式
这个输出格式符合要求,但需要安装
pip install tavily-python

且新版本的 langchain 已经不再支持，生产环境必须要换成 (pip install langchain-tavily)
from langchain_tavily import TavilySearch

"""
import os
from langchain_community.tools.tavily_search import TavilySearchResults

from langchain_community.retrievers import TavilySearchAPIRetriever
from docx import Document

def main():
    os.environ["TAVILY_API_KEY"] = "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"

    # 1. 初始化Tavily搜索工具
    tavily_tool = TavilySearchResults(
        # 核心参数：搜索结果数量（默认5）
        max_results=3,
        # 可选：搜索深度（"basic"=快速轻量，"advanced"=深度搜索，默认basic）
        search_depth="advanced",
        # 可选：是否返回直接答案（而非仅网页片段，默认False）
        include_answer=True,
        # 可选：是否返回图片结果（默认False）
        include_images=False,
    )

    # 2. 调用搜索（传入查询字符串）
    # 方式1：直接调用__call__方法（最常用）
    #results = tavily_tool.run("2025年北京新能源汽车上牌政策")

    # 方式2：通过invoke方法（LangChain标准接口，兼容Chain/Agent）
    results = tavily_tool.invoke("2025年北京公积金的提取流程是什么")

    # 3. 输出结果（结构化字符串，可直接喂给LLM）
    print(results)

if __name__ == "__main__":
    main()

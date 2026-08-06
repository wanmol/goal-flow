"""
CodeNode 测试用例
测试 CodeNode 的动态代码执行功能
"""

import sys
import os

# 添加项目根目录到路径 (从 unit_tests -> test -> project_root)
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from langgraph.graph import StateGraph, START, END

from goalflow.workflow_types import Case, Condition, ToolProviderConfig, ToolProviderType, HttpNodeRetryConfig, ToolParamSchema
from goalflow.node import IfElseNode, LLMNode, ToolNode
from goalflow.state import BaseState, GenericState

from typing import Dict, Any
from goalflow.state import BaseState
from goalflow.workflow_types import NodeVarConfig
from goalflow.constants import WfNodeType, ErrorStrategy


class ToolNodeTest:
    """ ToolNodeTest 测试类"""

    def __init__(self):
        print("🧪 ToolNodeTest 测试初始化")

    def test_tool_node(self):
        """
        tool 节点测试
        """
        try:
            def node_start(state: GenericState):
                print("开始节点")
                return {
                    "sys_query": state["sys_query"],
                    "sys_files": ["https://assets.wanlabai.com/industry_assistant/20250912/042b5eda2ff0c5c9ce2fb3532825fa10.pdf"],
                    "input_variables": {"iv": state["sys_query"], "sys.query": state["sys_query"]},
                    "output_variables": {"sov": {"inputs": "你好"}},
                    "conversation_variables": {"sys_files": ["http://www.baidu.com"]}
                }

            def node_a(state: GenericState):
                print("节点 A")
                return {
                    "sys_query": "节点 A",
                }

            def node_b(state: GenericState):
                print("节点 B")
                return {
                    "sys_query": "节点 B",
                }

            tool_provider_config = ToolProviderConfig()
            tool_provider_config.provider_type = ToolProviderType.WORKFLOW
            tool_provider_config.tool_parameters = {
                "file_name": {
                    "type": "constant",
                    "value": "1111"
                },
                "raw_text": {
                    "type": "mixed",
                    "value": "{{#sys.query#}}"
                },
                "files": {
                    "type": "variable",
                    "value": ["sys", "files"]
                }
            }

            tool = ToolNode(
                id="tool_node",
                desc="",
                selected="true",
                title="tool_node",
                type="tool",
                # error_strategy="default-value" ,
                # default_value=[{
                #     "value":"出现错误了", "type":"a", "key":"b"
                # }],
                # error_strategy="fail-branch",
                # fail_branch_node_ids=["a"],
                # next_node_ids=["b", "c"],
                retry_config=HttpNodeRetryConfig(
                    max_retries=3,
                    retry_enabled=True,
                    retry_interval=1000,
                ),
                is_team_authorization=True,
                tool_provider_config=tool_provider_config,

            )

            builder = StateGraph(BaseState)

            builder.add_node("node_a", node_a)
            builder.add_node("node_b", node_b)
            builder.add_node("node_start", node_start)
            builder.add_node("tool", tool)

            builder.add_edge(START, "node_start")
            builder.add_edge("node_start", "tool")
            builder.add_edge("node_a", END)
            builder.add_edge("node_b", END)

            graph = builder.compile()

            graph.invoke({
                "sys.query": "Java",
                "sys_query": "Java",
                "sys.dialogue_count": "你好",
            })
            return True
        except Exception as e:
            print(f"❌ 测试执行异常: {e}")
            return False

    def test_json_tool_node(self):
        """
        tool 节点测试
        """
        try:
            def node_start(state: GenericState):
                print("开始节点")
                return {
                    "sys_query": state["sys_query"],
                    "sys_files": ["http://www.baidu.com"],
                    "input_variables": { "sys_query":  """
                    {
    "reasoning": "Provide a detailed explanation of why you chose this specific search query based on the current knowledge gaps, previous findings, and what information is still needed to thoroughly address the research topic",
    "search_query": "A specific, targeted search query designed to fill the most critical knowledge gap identified. This should be a follow-up question that builds on previous research and addresses missing information",
    "knowledge_gap": "List the specific information that is still needed to comprehensively answer the original research topic, taking into account what has already been discovered and what remains unknown",
    "should_continue": "If sufficient information has been obtained, set should_continue to false. type: bool | true or false"
}"""},
                    "output_variables": {"sov": {"inputs": "你好"}},
                    "conversation_variables": {"sys_files": ["http://www.baidu.com"]}
                }

            def node_a(state: GenericState):
                print("节点 A")
                return {
                    "sys_query": """
                    {
    "reasoning": "Provide a detailed explanation of why you chose this specific search query based on the current knowledge gaps, previous findings, and what information is still needed to thoroughly address the research topic",
    "search_query": "A specific, targeted search query designed to fill the most critical knowledge gap identified. This should be a follow-up question that builds on previous research and addresses missing information",
    "knowledge_gap": "List the specific information that is still needed to comprehensively answer the original research topic, taking into account what has already been discovered and what remains unknown"
    "should_continue": "If sufficient information has been obtained, set should_continue to false. type: bool | true or false"
}""",
                }

            def node_b(state: GenericState):
                print("节点 B")
                return {
                    "sys_query": "节点 B",
                }

            tool_provider_config = ToolProviderConfig()
            tool_provider_config.provider_type = ToolProviderType.BUILT_IN
            tool_provider_config.tool_name = "parse"
            tool_provider_config.tool_parameters = {
                "content": {
                    "type": "constant",
                    "value": "{{#sys.query#}}"
                },
                "json_filter": {
                    "type": "mixed",
                    "value": "search_query"
                }
            }
            tool_param_schema1 = ToolParamSchema(
                auto_generate=None,
                default=None,
                form="llm",
                human_description={
                    "en_US": "JSON data",
                    "ja_JP": "JSON data",
                    "pt_BR": "JSON data",
                    "zh_Hans": "JSON data",
                },
                label={
                    "en_US": "JSON data",
                    "ja_JP": "JSON data",
                    "pt_BR": "JSON data",
                    "zh_Hans": "JSON data",
                },
                llm_description="JSON data to be processed",
                max=None,
                min=None,
                options=[],
                placeholder=None,
                scope=None,
                template=None,
                name="content",
                required=True,
                type="string",
                precision=None,
            )

            ##########################################
            tool_param_schema2 = ToolParamSchema(
                auto_generate=None,
                default=None,
                form="llm",
                human_description={
                    "en_US": "JSON data",
                    "ja_JP": "JSON data",
                    "pt_BR": "JSON data",
                    "zh_Hans": "JSON data",
                },
                label={
                    "en_US": "JSON data",
                    "ja_JP": "JSON data",
                    "pt_BR": "JSON data",
                    "zh_Hans": "JSON data",
                },
                llm_description="JSON data to be processed",
                max=None,
                min=None,
                options=[],
                placeholder=None,
                scope=None,
                template=None,
                precision=None,
                name="json_filter",
                required=True,
                type="string",
            )

            ##########################################
            tool_param_schema3 = ToolParamSchema(
                auto_generate=None,
                default=1,
                form="form",
                human_description={
                    "en_US": "确保输出的 JSON 是 ASCII 编码",
                    "ja_JP": "确保输出的 JSON 是 ASCII 编码",
                    "pt_BR": "确保输出的 JSON 是 ASCII 编码",
                    "zh_Hans": "J确保输出的 JSON 是 ASCII 编码",
                },
                label={
                    "en_US": "确保输出的 JSON 是 ASCII 编码",
                    "ja_JP": "确保输出的 JSON 是 ASCII 编码",
                    "pt_BR": "确保输出的 JSON 是 ASCII 编码",
                    "zh_Hans": "确保输出的 JSON 是 ASCII 编码",
                },
                llm_description="JSON data to be processed",
                max=None,
                min=None,
                options=[],
                placeholder=None,
                scope=None,
                template=None,
                name="ensure_ascii",
                required=False,
                type="boolean",
                precision=None,
            )

            paramschemas = [tool_param_schema1, tool_param_schema2, tool_param_schema3]

            tool = ToolNode(
                id="tool_node",
                desc="",
                selected="true",
                title="tool_node",
                type="tool",
                retry_config=HttpNodeRetryConfig(
                    max_retries=3,
                    retry_enabled=True,
                    retry_interval=1000,
                ),
                param_schemas=paramschemas,
                is_team_authorization=True,
                tool_provider_config=tool_provider_config,
                next_node_ids=["node_b"]
            )

            builder = StateGraph(BaseState)

            builder.add_node("node_a", node_a)
            builder.add_node("node_b", node_b)
            builder.add_node("node_start", node_start)
            builder.add_node("tool", tool)

            builder.add_edge(START, "node_start")
            builder.add_edge("node_start", "tool")
            builder.add_edge("node_a", END)
            builder.add_edge("node_b", END)

            graph = builder.compile()

            graph.invoke({
                "sys.query": "Java",
                "sys_query": "Java",
                "sys.dialogue_count": "你好",
            })
            return True
        except Exception as e:
            print(f"❌ 测试执行异常: {e}")
            return False

    def run_all_tests(self):
        """运行所有测试"""
        print("🚀 开始运行 CodeNode 测试套件")
        print("=" * 60)

        tests = [
            # self.test_tool_node,
            self.test_json_tool_node,
        ]

        passed = 0
        failed = 0

        for test in tests:
            try:
                if test():
                    passed += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"❌ 测试执行异常: {e}")
                failed += 1

        print("\n" + "=" * 60)
        print(f"📊 测试结果汇总:")
        print(f"✅ 通过: {passed}")
        print(f"❌ 失败: {failed}")
        print(f"📈 成功率: {passed / (passed + failed) * 100:.1f}%")

        if failed == 0:
            print("🎉 所有测试都通过了！")
        else:
            print("⚠️ 有测试失败，请检查上述输出")

        return failed == 0


def main():
    """主函数"""
    print("🧪 LLM Node 执行测试")
    print("=" * 60)

    tester = ToolNodeTest()
    success = tester.run_all_tests()

    if success:
        exit(0)
    else:
        exit(1)


if __name__ == "__main__":
    main()

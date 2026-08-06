"""
CodeNode 测试用例
测试 CodeNode 的动态代码执行功能
"""

import sys
import os

# 添加项目根目录到路径 (从 unit_tests -> test -> project_root)
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from langgraph.graph import StateGraph, START, END

from goalflow.workflow_types import Case, Condition, ContextConfig, LLMNodeModelConfig, LLmNodePromptTemplate, MemoryConfig, PromptConfig
from goalflow.node import IfElseNode, LLMNode
from goalflow.state import BaseState, GenericState


from typing import Dict, Any
from goalflow.state import BaseState
from goalflow.workflow_types import NodeVarConfig
from goalflow.constants import WfNodeType, ErrorStrategy

# 直接导入 CodeNode
from goalflow.node.code_node import CodeNode


class LlmNodeTest:
    """ LlmNodeTest 测试类"""

    def __init__(self):
        print("🧪 LlmNodeTest 测试初始化")

    def test_llm_case(self):
        """
        llm 节点测试
        """
        try:
            def node_start(state: GenericState):
                print("开始节点")
                return {
                    "sys_query": state["sys_query"],
                    "input_variables": {"iv": state["sys_query"], "sys.query": state["sys_query"]},
                    "output_variables": {"sov": {"inputs": "你好"}},
                    "conversation_variables": {"cv": 1111}
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

            content= ContextConfig(
                enabled=True , 
                variable_selector=["1755499252086", "result"]
            )
            memory = MemoryConfig(
                 query_prompt_template="{{#sys.query#}}" ,
                 role_prefix={
                     "assistant": "",
                     "user": ""
                 },
                 window={
                     "enabled": "false",
                     "size": 50
                 }
            )

            model = LLMNodeModelConfig(
                mode="chat",
                name="deepseek-v3", #"qwen2.5-14b-instruct",
                provider= "langgenius/tongyi/tongyi",
                completion_params={
                    "response_format": "json_object"
                }
            )
            # model = LLMNodeModelConfig(
            #     mode="chat",
            #     name="gpt-4o-mini",  # "qwen2.5-14b-instruct",
            #     provider="langgenius/azure_openai/azure_openai",
            #     completion_params={
            #         "response_format": "json_object"
            #     }
            # )


            prompt_config = PromptConfig(
                jinja2_variables=[
                    NodeVarConfig(
                        value_selector=["sys", "query"],
                        variable="query"
                    )
                ]
            )
            prompt_templates = [
                LLmNodePromptTemplate(
                    id="1",
                    edition_type="jinja2",
                    jinja2_text="你是一个只返回JSON格式数据的助手。不要包含任何Markdown格式，只输出纯JSON字符串，不要有任何额外的文本。",
                    role="system",
                    text="你是一名优秀的行政专员，能够根据行政服务指南中的描述，改为口语化的表达，给用户"
                ) ,
                # LLmNodePromptTemplate(
                #     id="2",
                #     role="user",
                #     text="{{#sys.query#}} 还流行吗？"
                # ),
                # LLmNodePromptTemplate(
                #     id="3",
                #     role="user",
                #     text="{{#sys.query#}} 还会继续流行下去吗？"
                # ),
                # LLmNodePromptTemplate(
                #     id="4",
                #     role="assistant",
                #     text="是的，{{#sys.query#}}还活着，而且很流行。"
                # )
                LLmNodePromptTemplate(
                    id="4",
                    role="user",
                    text="Return a JSON object  with key 'random_ints' and a value of 10 random ints in[0-99]"
                )

            ]

            llm = LLMNode(
                context=content,
                memory= memory,
                # model={
                #     "mode": "chat",
                #     "name": "gpt-4o-mini",
                #     "provider": "langgenius/azure_openai/azure_openai",
                #     "completion_params": {}
                # },
                model=model,
                prompt_config=prompt_config,
                prompt_template=prompt_templates,
                vision={
                    "enabled": False,
                },
                desc="",
                selected="true",
                title="LLM",
                type="llm",
                # error_strategy="default-value" ,
                # default_value=[{
                #     "value":"出现错误了", "type":"a", "key":"b"
                # }],
                error_strategy="fail-branch",
                fail_branch_node_ids=["a"],
                next_node_ids=["b", "c"],
                id="llm"

            )

            builder = StateGraph(BaseState)

            builder.add_node("node_a", node_a)
            builder.add_node("node_b", node_b)
            builder.add_node("node_start", node_start)

            builder.add_edge(START, "node_start")
            builder.add_conditional_edges("node_start", llm)
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
            self.test_llm_case,
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

    tester = LlmNodeTest()
    success = tester.run_all_tests()

    if success:
        exit(0)
    else:
        exit(1)


if __name__ == "__main__":
    main()

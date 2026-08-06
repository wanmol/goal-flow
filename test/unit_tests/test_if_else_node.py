"""
CodeNode 测试用例
测试 CodeNode 的动态代码执行功能
"""

import sys
import os
from langgraph.graph import StateGraph, START,END

from goalflow.workflow_types import Case, Condition
from goalflow.node import IfElseNode
from goalflow.state import BaseState, GenericState
# 添加项目根目录到路径 (从 unit_tests -> test -> project_root)
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from typing import Dict, Any
from goalflow.state import BaseState
from goalflow.workflow_types import NodeVarConfig
from goalflow.constants import WfNodeType

# 直接导入 CodeNode
from goalflow.node.code_node import CodeNode


class IfElseNodeTest:
    """IfElseNodeTest 测试类"""

    def __init__(self):
        print("🧪 IfElseNodeTest 测试初始化")

    def test_one_case(self):
        """
        单条件
        """
        try:
            def node_start(state: GenericState):
                print("开始节点")
                return {
                    "sys_query": state["sys_query"],
                    "input_variables": {"iv": state["sys_query"]},
                    "output_variables": {"sov": {"inputs":"你好"}},
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

            condition = Condition(
                variable_selector=["sys", "query"],
                comparison_operator="contains",
                value="{{#sys.dialogue_count#}}",
                varType="string",
                sub_variable_condition=None
            )

            case = Case(case_id="node_b", logical_operator="and", conditions=[condition])

            conditional = IfElseNode(
                id="conditional",
                conditions=None,
                cases=[case],
                logical_operator="and",
                # 这里可以添加更多的配置
                desc="",
                selected="false",
                title="Conditional Node",
                type="type"
            )

            builder = StateGraph(BaseState)

            builder.add_node("node_a", node_a)
            builder.add_node("node_b", node_b)
            builder.add_node("node_start", node_start)

            builder.add_edge(START, "node_start")
            builder.add_conditional_edges("node_start", conditional)
            builder.add_edge("node_a", END)
            builder.add_edge("node_b", END)

            graph = builder.compile()

            graph.invoke({
                "sys_query": "你好" ,
                "sys.dialogue_count":"你好" ,
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
            self.test_one_case,
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
    print("🧪 IF_ELSE_NODE 执行测试")
    print("=" * 60)

    tester = IfElseNodeTest()
    success = tester.run_all_tests()

    if success:
        exit(0)
    else:
        exit(1)


if __name__ == "__main__":
    main()

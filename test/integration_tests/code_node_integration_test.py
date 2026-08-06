#!/usr/bin/env python3
"""
CodeNode 集成测试
基于 langgraph 的 Start -> Code -> Answer 工作流测试
"""

import sys
import os
# 添加项目根目录到路径 (从 integration_tests -> test -> project_root)
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from typing import Dict, Any
from goalflow.state import BaseState
from goalflow.node.code_node import CodeNode
from goalflow.workflow_types import NodeVarConfig
from goalflow.constants import WfNodeType, DefaultValueType
from langgraph.graph import StateGraph


class SimpleStartNode:
    """简单的开始节点"""
    def __init__(self, **kwargs):
        self.config = kwargs

class SimpleAnswerNode:
    """简单的答案节点"""
    def __init__(self, **kwargs):
        self.config = kwargs

class SimpleDifyWfVariableConfig:
    def __init__(self, variable, label, type, required, max_length):
        self.variable = variable
        self.label = label
        self.type = type
        self.required = required
        self.max_length = max_length


class CodeNodeIntegrationWorkflow:
    """CodeNode 集成测试工作流：Start -> Code -> Answer"""
    
    def __init__(self):
        self.graph = StateGraph(BaseState)
        self._setup_nodes()
        self._setup_edges()
    
    def _setup_nodes(self):
        """设置工作流节点"""
        
        # 1. Start节点 - 初始化工作流
        self.start_node = SimpleStartNode(
            id="start_001",
            desc="工作流开始节点",
            selected=True,
            title="开始",
            type="start",
            wf_inputs=[
                SimpleDifyWfVariableConfig(
                    variable="numbers",
                    label="数字列表",
                    type=DefaultValueType.STRING,
                    required=True,
                    max_length=1000
                ),
                SimpleDifyWfVariableConfig(
                    variable="operation",
                    label="操作类型",
                    type=DefaultValueType.STRING,
                    required=True,
                    max_length=100
                )
            ]
        )
        
        # 2. Code节点 - 动态执行代码
        self.code_node = CodeNode(
            desc="数据处理代码节点",
            selected=True,
            title="数据处理器",
            type="code",
            code="""
import json

def main(numbers_str, operation):
    \"\"\"动态数据处理函数\"\"\"
    try:
        # 解析数字列表
        if isinstance(numbers_str, str):
            numbers = json.loads(numbers_str)
        else:
            numbers = numbers_str
        
        if not isinstance(numbers, list):
            return {'error': 'Invalid numbers format', 'result': None}
        
        # 根据操作类型执行不同的计算
        if operation == "sum":
            result = sum(numbers)
            description = f"计算 {numbers} 的总和"
        elif operation == "average":
            result = sum(numbers) / len(numbers) if numbers else 0
            description = f"计算 {numbers} 的平均值"
        elif operation == "max":
            result = max(numbers) if numbers else None
            description = f"计算 {numbers} 的最大值"
        elif operation == "min":
            result = min(numbers) if numbers else None
            description = f"计算 {numbers} 的最小值"
        elif operation == "sort":
            result = sorted(numbers)
            description = f"对 {numbers} 进行排序"
        elif operation == "analyze":
            result = {
                'count': len(numbers),
                'sum': sum(numbers),
                'avg': sum(numbers) / len(numbers) if numbers else 0,
                'max': max(numbers) if numbers else None,
                'min': min(numbers) if numbers else None,
                'sorted': sorted(numbers)
            }
            description = f"全面分析 {numbers}"
        else:
            result = None
            description = f"不支持的操作: {operation}"
        
        return {
            'result': result,
            'description': description,
            'operation': operation,
            'input_data': numbers,
            'success': True
        }
        
    except Exception as e:
        return {
            'result': None,
            'description': f"执行出错: {str(e)}",
            'operation': operation,
            'input_data': numbers_str,
            'success': False,
            'error': str(e)
        }
""",
            code_language="python",
            variables=[
                NodeVarConfig(
                    variable="numbers_str",
                    value_selector=["start_001", "numbers"]
                ),
                NodeVarConfig(
                    variable="operation",
                    value_selector=["start_001", "operation"]
                )
            ],
            outputs={
                "result": {"type": "any"},
                "description": {"type": "string"},
                "operation": {"type": "string"},
                "input_data": {"type": "any"},
                "success": {"type": "boolean"},
                "error": {"type": "string"}
            }
        )
        
        # 3. Answer节点 - 输出结果
        self.answer_node = SimpleAnswerNode(
            id="answer_001",
            desc="答案输出节点",
            selected=True,
            title="结果",
            type="answer",
            variables=[
                NodeVarConfig(
                    variable="final_result",
                    value_selector=["code_001", "result"]
                ),
                NodeVarConfig(
                    variable="description",
                    value_selector=["code_001", "description"]
                )
            ]
        )
        
        # 添加节点到图中
        self.graph.add_node("start", self._start_wrapper)
        self.graph.add_node("code", self._code_wrapper)
        self.graph.add_node("answer", self._answer_wrapper)
        
        # 设置入口点
        self.graph.set_entry_point("start")
    
    def _setup_edges(self):
        """设置节点之间的连接"""
        self.graph.add_edge("start", "code")
        self.graph.add_edge("code", "answer")
        self.graph.set_finish_point("answer")
    
    def _start_wrapper(self, state: BaseState) -> BaseState:
        """Start节点包装器"""
        input_data = state.get("input_variables", {})
        print(f"[Start] 接收输入: {input_data}")
        
        return {
            **state,
            "output_variables": {
                **state.get("output_variables", {}),
                "numbers": input_data.get("numbers"),
                "operation": input_data.get("operation")
            }
        }
    
    def _code_wrapper(self, state: BaseState) -> BaseState:
        """Code节点包装器"""
        print(f"[Code] 开始执行动态代码...")
        
        # 使用 CodeNode 执行代码
        result = self.code_node(state)
        
        output_vars = result.get("output_variables", {})
        print(f"[Code] 执行完成: {output_vars.get('description', 'N/A')}")
        
        return result
    
    def _answer_wrapper(self, state: BaseState) -> BaseState:
        """Answer节点包装器"""
        output_vars = state.get("output_variables", {})
        
        # 格式化最终答案
        if output_vars.get("success", False):
            final_answer = f"✅ {output_vars.get('description', '执行成功')}\n结果: {output_vars.get('result', 'N/A')}"
        else:
            final_answer = f"❌ {output_vars.get('description', '执行失败')}"
        
        print(f"[Answer] 最终结果: {final_answer}")
        
        # 设置最终答案
        final_vars = output_vars.copy()
        final_vars["final_answer"] = final_answer
        
        return {
            **state,
            "output_variables": final_vars
        }
    
    def execute(self, numbers, operation) -> Dict[str, Any]:
        """执行工作流"""
        print("=== 开始执行 CodeNode 集成测试工作流 ===")
        print(f"输入数据: {numbers}")
        print(f"操作类型: {operation}")
        
        # 初始化状态
        initial_state = BaseState(
            sys_query=f"执行{operation}操作",
            sys_user_id="integration_test_user",
            sys_app_id="integration_test_app",
            sys_workflow_id="code_node_integration",
            sys_workflow_run_id="run_001",
            input_variables={
                "numbers": numbers,
                "operation": operation
            },
            output_variables={},
            conversation_variables={}
        )
        
        # 编译并执行图
        compiled_graph = self.graph.compile()
        result = compiled_graph.invoke(initial_state)
        
        print("=== CodeNode 集成测试工作流执行完成 ===")
        return result


class CodeNodeIntegrationTest:
    """CodeNode 集成测试类"""
    
    def __init__(self):
        print("🧪 CodeNode 集成测试初始化")
    
    def test_sum_operation(self):
        """测试求和操作"""
        print("\n=== 集成测试1: 求和操作 ===")
        
        workflow = CodeNodeIntegrationWorkflow()
        numbers = [1, 2, 3, 4, 5]
        
        try:
            result = workflow.execute(numbers, "sum")
            final_answer = result.get("output_variables", {}).get("final_answer", "")
            output_vars = result.get("output_variables", {})
            
            print(f"最终答案: {final_answer}")
            
            # 验证结果
            expected_result = 15
            actual_result = output_vars.get("result")
            
            if actual_result == expected_result:
                print("✅ 求和测试通过")
                return True
            else:
                print(f"❌ 求和测试失败: 期望 {expected_result}, 实际 {actual_result}")
                return False
                
        except Exception as e:
            print(f"❌ 求和测试异常: {e}")
            return False
    
    def test_analyze_operation(self):
        """测试分析操作"""
        print("\n=== 集成测试2: 数据分析操作 ===")
        
        workflow = CodeNodeIntegrationWorkflow()
        numbers = [10, 5, 8, 3, 12, 7]
        
        try:
            result = workflow.execute(numbers, "analyze")
            final_answer = result.get("output_variables", {}).get("final_answer", "")
            output_vars = result.get("output_variables", {})
            
            print(f"最终答案: {final_answer}")
            
            # 验证结果
            actual_result = output_vars.get("result")
            if isinstance(actual_result, dict):
                expected_checks = {
                    'count': 6,
                    'sum': 45,
                    'max': 12,
                    'min': 3
                }
                
                all_correct = True
                for key, expected_value in expected_checks.items():
                    if actual_result.get(key) == expected_value:
                        print(f"✓ {key}: {actual_result.get(key)} (正确)")
                    else:
                        print(f"✗ {key}: 期望 {expected_value}, 实际 {actual_result.get(key)}")
                        all_correct = False
                
                if all_correct:
                    print("✅ 分析测试通过")
                    return True
                else:
                    print("❌ 分析测试部分失败")
                    return False
            else:
                print(f"❌ 分析测试失败: 结果格式不正确")
                return False
                
        except Exception as e:
            print(f"❌ 分析测试异常: {e}")
            return False
    
    def test_error_handling(self):
        """测试错误处理"""
        print("\n=== 集成测试3: 错误处理 ===")
        
        workflow = CodeNodeIntegrationWorkflow()
        invalid_numbers = "invalid_data"
        
        try:
            result = workflow.execute(invalid_numbers, "sum")
            output_vars = result.get("output_variables", {})
            
            # 验证错误处理
            success = output_vars.get("success", True)
            if not success and "error" in output_vars:
                print("✅ 错误处理测试通过")
                print(f"错误信息: {output_vars.get('error', 'N/A')}")
                return True
            else:
                print("❌ 错误处理测试失败: 应该返回错误但没有")
                return False
                
        except Exception as e:
            print(f"❌ 错误处理测试异常: {e}")
            return False
    
    def test_string_input(self):
        """测试字符串输入（JSON格式）"""
        print("\n=== 集成测试4: 字符串输入处理 ===")
        
        workflow = CodeNodeIntegrationWorkflow()
        numbers_str = "[2, 4, 6, 8, 10]"
        
        try:
            result = workflow.execute(numbers_str, "average")
            output_vars = result.get("output_variables", {})
            
            # 验证结果
            expected_result = 6.0
            actual_result = output_vars.get("result")
            
            if actual_result == expected_result:
                print("✅ 字符串输入测试通过")
                return True
            else:
                print(f"❌ 字符串输入测试失败: 期望 {expected_result}, 实际 {actual_result}")
                return False
                
        except Exception as e:
            print(f"❌ 字符串输入测试异常: {e}")
            return False
    
    def run_all_tests(self):
        """运行所有集成测试"""
        print("🚀 开始运行 CodeNode 集成测试套件")
        print("=" * 60)
        
        tests = [
            self.test_sum_operation,
            self.test_analyze_operation,
            self.test_error_handling,
            self.test_string_input
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
        print(f"📊 集成测试结果汇总:")
        print(f"✅ 通过: {passed}")
        print(f"❌ 失败: {failed}")
        print(f"📈 成功率: {passed/(passed+failed)*100:.1f}%")
        
        if failed == 0:
            print("🎉 所有集成测试都通过了！")
        else:
            print("⚠️ 有集成测试失败，请检查上述输出")
        
        return failed == 0


def main():
    """主函数"""
    print("🧪 CodeNode 集成测试 - 基于 LangGraph 工作流")
    print("=" * 60)
    
    tester = CodeNodeIntegrationTest()
    success = tester.run_all_tests()
    
    if success:
        exit(0)
    else:
        exit(1)


if __name__ == "__main__":
    main()

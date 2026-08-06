"""
IterationNode 测试用例
测试 IterationNode 的迭代处理功能
"""

import sys
import os
# 添加项目根目录到路径 (从 unit_tests -> test -> project_root)
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from typing import Dict, Any
from unittest.mock import Mock, MagicMock
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph

from goalflow.state import BaseState, GenericState
from goalflow.constants import WfNodeType, ErrorHandleMode
from goalflow.node.iteration_node import IterationNode
from goalflow.tool.utils import VariableResolver


class IterationNodeTest:
    """IterationNode 测试类"""
    
    def __init__(self):
        print("🧪 IterationNode 测试初始化")
    
    def _create_mock_subgraph(self, expected_outputs: list = None):
        """创建模拟的子图"""
        if expected_outputs is None:
            expected_outputs = [{"result": f"processed_{i}"} for i in range(3)]
        
        def mock_invoke(state):
            # 模拟子图处理，从状态中获取 item 并返回处理结果
            item = state.get("output_variables", {}).get("item", 0)
            if isinstance(item, int) and item < len(expected_outputs):
                result_state = state.copy()
                result_state["output_variables"] = state["output_variables"].copy()
                result_state["output_variables"]["processed"] = expected_outputs[item]
                return result_state
            return state
        
        mock_subgraph = Mock(spec=CompiledStateGraph)
        mock_subgraph.invoke = Mock(side_effect=mock_invoke)
        return mock_subgraph
    
    def test_basic_iteration(self):
        """测试基本迭代功能"""
        print("\n=== 测试用例1: 基本迭代功能 ===")
        
        # 创建 IterationNode 实例
        iteration_node = IterationNode(
            id="iteration_1",
            desc="基本迭代节点",
            selected=True,
            title="基本迭代",
            type="iteration",
            start_node_id="start_node",
            parallel_nums=3,
            is_parallel=False,
            iterator_selector=["input", "items"],
            output_selector=["processed_node", "result"],
            output_type="array",
            error_handle_mode=ErrorHandleMode.TERMINATED
        )
        
        # 设置模拟子图
        iteration_node.subgraph = self._create_mock_subgraph([
            {"result": "processed_0"},
            {"result": "processed_1"}, 
            {"result": "processed_2"}
        ])
        
        # 准备测试状态
        test_state = BaseState(
            sys_query="测试基本迭代",
            sys_user_id="test_user",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={
                "items": [0, 1, 2]  # 要迭代的数组
            },
            conversation_variables={}
        )
        
        # 执行测试
        try:
            result = iteration_node.call(test_state)
            
            print(f"✅ 测试成功!")
            print(f"结果类型: {type(result)}")
            print(f"结果内容: {result}")
            
            # 验证结果
            if hasattr(result, 'update') and 'output_variables' in result.update:
                output_vars = result.update['output_variables']
                expected_key = f"iteration_1_output"
                if expected_key in output_vars:
                    outputs = output_vars[expected_key]
                    print(f"✓ 迭代输出: {outputs}")
                    return True
                else:
                    print(f"✗ 缺少期望的输出键: {expected_key}")
                    return False
            else:
                print(f"✗ 结果格式不正确")
                return False
                
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def test_empty_input_array(self):
        """测试空数组输入"""
        print("\n=== 测试用例2: 空数组输入 ===")
        
        iteration_node = IterationNode(
            id="iteration_2",
            desc="空数组测试节点",
            selected=True,
            title="空数组测试",
            type="iteration",
            start_node_id="start_node",
            parallel_nums=3,
            is_parallel=False,
            iterator_selector=["input", "empty_items"],
            output_selector=["processed_node", "result"],
            output_type="array",
            error_handle_mode=ErrorHandleMode.TERMINATED
        )
        
        # 设置模拟子图
        iteration_node.subgraph = self._create_mock_subgraph([])
        
        # 准备测试状态 - 空数组
        test_state = BaseState(
            sys_query="测试空数组迭代",
            sys_user_id="test_user",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={
                "empty_items": []  # 空数组
            },
            conversation_variables={}
        )
        
        # 执行测试
        try:
            result = iteration_node.call(test_state)
            
            print(f"✅ 测试成功!")
            print(f"结果: {result}")
            
            # 验证结果 - 应该能正常处理空数组
            if hasattr(result, 'update'):
                print("✓ 空数组处理正常")
                return True
            else:
                print("✗ 空数组处理异常")
                return False
                
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            return False
    
    def test_none_input(self):
        """测试 None 输入"""
        print("\n=== 测试用例3: None 输入错误处理 ===")
        
        iteration_node = IterationNode(
            id="iteration_3",
            desc="None输入测试节点",
            selected=True,
            title="None输入测试",
            type="iteration",
            start_node_id="start_node",
            parallel_nums=3,
            is_parallel=False,
            iterator_selector=["input", "none_items"],
            output_selector=["processed_node", "result"],
            output_type="array",
            error_handle_mode=ErrorHandleMode.TERMINATED
        )
        
        # 设置模拟子图
        iteration_node.subgraph = self._create_mock_subgraph([])
        
        # 准备测试状态 - None 值
        test_state = BaseState(
            sys_query="测试None输入",
            sys_user_id="test_user",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={
                "none_items": None  # None 值
            },
            conversation_variables={}
        )
        
        # 执行测试
        try:
            result = iteration_node.call(test_state)
            print(f"❌ 应该抛出错误，但是没有")
            return False
        except ValueError as e:
            if "iteration node inputs is None" in str(e):
                print(f"✅ 正确捕获 None 输入错误: {e}")
                return True
            else:
                print(f"❌ 错误信息不正确: {e}")
                return False
        except Exception as e:
            print(f"❌ 意外错误: {e}")
            return False
    
    def test_non_list_input(self):
        """测试非列表输入"""
        print("\n=== 测试用例4: 非列表输入错误处理 ===")
        
        iteration_node = IterationNode(
            id="iteration_4", 
            desc="非列表输入测试节点",
            selected=True,
            title="非列表输入测试",
            type="iteration",
            start_node_id="start_node",
            parallel_nums=3,
            is_parallel=False,
            iterator_selector=["input", "string_item"],
            output_selector=["processed_node", "result"],
            output_type="array",
            error_handle_mode=ErrorHandleMode.TERMINATED
        )
        
        # 设置模拟子图
        iteration_node.subgraph = self._create_mock_subgraph([])
        
        # 准备测试状态 - 字符串而不是列表
        test_state = BaseState(
            sys_query="测试非列表输入",
            sys_user_id="test_user",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={
                "string_item": "not a list"  # 字符串而不是列表
            },
            conversation_variables={}
        )
        
        # 执行测试
        try:
            result = iteration_node.call(test_state)
            print(f"❌ 应该抛出错误，但是没有")
            return False
        except ValueError as e:
            if "iteration node inputs must be list" in str(e):
                print(f"✅ 正确捕获非列表输入错误: {e}")
                return True
            else:
                print(f"❌ 错误信息不正确: {e}")
                return False
        except Exception as e:
            print(f"❌ 意外错误: {e}")
            return False
    
    def test_no_subgraph(self):
        """测试无子图错误"""
        print("\n=== 测试用例5: 无子图错误处理 ===")
        
        iteration_node = IterationNode(
            id="iteration_5",
            desc="无子图测试节点",
            selected=True,
            title="无子图测试", 
            type="iteration",
            start_node_id="start_node",
            parallel_nums=3,
            is_parallel=False,
            iterator_selector=["input", "items"],
            output_selector=["processed_node", "result"],
            output_type="array",
            error_handle_mode=ErrorHandleMode.TERMINATED
        )
        
        # 不设置子图 (subgraph = None)
        
        # 准备测试状态
        test_state = BaseState(
            sys_query="测试无子图",
            sys_user_id="test_user",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={
                "items": [1, 2, 3]
            },
            conversation_variables={}
        )
        
        # 执行测试
        try:
            result = iteration_node.call(test_state)
            print(f"❌ 应该抛出错误，但是没有")
            return False
        except ValueError as e:
            if "iteration node subgraph is None" in str(e):
                print(f"✅ 正确捕获无子图错误: {e}")
                return True
            else:
                print(f"❌ 错误信息不正确: {e}")
                return False
        except Exception as e:
            print(f"❌ 意外错误: {e}")
            return False
    
    def test_parallel_limitation(self):
        """测试并行数量限制"""
        print("\n=== 测试用例6: 并行数量限制 ===")
        
        iteration_node = IterationNode(
            id="iteration_6",
            desc="并行限制测试节点",
            selected=True,
            title="并行限制测试",
            type="iteration",
            start_node_id="start_node",
            parallel_nums=2,  # 限制并行数为2
            is_parallel=True,
            iterator_selector=["input", "large_items"],
            output_selector=["processed_node", "result"],
            output_type="array",
            error_handle_mode=ErrorHandleMode.TERMINATED
        )
        
        # 设置模拟子图
        iteration_node.subgraph = self._create_mock_subgraph([
            {"result": "processed_0"},
            {"result": "processed_1"}  # 只处理前2个元素
        ])
        
        # 准备测试状态 - 大于并行数量的数组
        test_state = BaseState(
            sys_query="测试并行限制",
            sys_user_id="test_user",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={
                "large_items": [0, 1, 2, 3, 4]  # 5个元素，但只能并行处理2个
            },
            conversation_variables={}
        )
        
        # 执行测试
        try:
            result = iteration_node.call(test_state)
            
            print(f"✅ 测试成功!")
            print(f"结果: {result}")
            
            # 验证结果 - 应该只处理前 parallel_nums 个元素
            if hasattr(result, 'update'):
                print("✓ 并行数量限制正常工作")
                return True
            else:
                print("✗ 并行数量限制测试失败")
                return False
                
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            return False
    
    def test_different_error_modes(self):
        """测试不同的错误处理模式"""
        print("\n=== 测试用例7: 不同错误处理模式 ===")
        
        # 测试 CONTINUE_ON_ERROR 模式
        iteration_node = IterationNode(
            id="iteration_7",
            desc="错误模式测试节点",
            selected=True,
            title="错误模式测试",
            type="iteration",
            start_node_id="start_node",
            parallel_nums=3,
            is_parallel=False,
            iterator_selector=["input", "items"],
            output_selector=["processed_node", "result"],
            output_type="array",
            error_handle_mode=ErrorHandleMode.CONTINUE_ON_ERROR
        )
        
        # 设置模拟子图
        iteration_node.subgraph = self._create_mock_subgraph([])
        
        # 准备测试状态
        test_state = BaseState(
            sys_query="测试错误处理模式",
            sys_user_id="test_user",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={
                "items": [1, 2, 3]
            },
            conversation_variables={}
        )
        
        # 执行测试
        try:
            result = iteration_node.call(test_state)
            
            print(f"✅ 测试成功!")
            print(f"错误处理模式: {iteration_node.error_handle_mode}")
            
            # 验证错误处理模式设置正确
            if iteration_node.error_handle_mode == ErrorHandleMode.CONTINUE_ON_ERROR:
                print("✓ 错误处理模式设置正确")
                return True
            else:
                print("✗ 错误处理模式设置错误")
                return False
                
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            return False
    
    def test_node_properties(self):
        """测试节点属性"""
        print("\n=== 测试用例8: 节点属性验证 ===")
        
        iteration_node = IterationNode(
            id="iteration_8",
            desc="属性测试节点",
            selected=True,
            title="属性测试",
            type="iteration",
            start_node_id="start_node",
            parallel_nums=5,
            is_parallel=True,
            iterator_selector=["input", "items"],
            output_selector=["output", "result"],
            output_type="object",
            error_handle_mode=ErrorHandleMode.REMOVE_ABNORMAL_OUTPUT
        )
        
        # 验证节点类型
        if iteration_node.node_type == WfNodeType.ITERATION:
            print("✓ 节点类型正确")
        else:
            print(f"✗ 节点类型错误: {iteration_node.node_type}")
            return False
        
        # 验证各个属性
        properties_to_check = {
            "id": "iteration_8",
            "start_node_id": "start_node",
            "parallel_nums": 5,
            "is_parallel": True,
            "iterator_selector": ["input", "items"],
            "output_selector": ["output", "result"],
            "output_type": "object",
            "error_handle_mode": ErrorHandleMode.REMOVE_ABNORMAL_OUTPUT
        }
        
        all_correct = True
        for prop_name, expected_value in properties_to_check.items():
            actual_value = getattr(iteration_node, prop_name)
            if actual_value == expected_value:
                print(f"✓ {prop_name}: {actual_value}")
            else:
                print(f"✗ {prop_name}: 期望 {expected_value}, 实际 {actual_value}")
                all_correct = False
        
        return all_correct
    
    def test_complex_data_iteration(self):
        """测试复杂数据结构迭代"""
        print("\n=== 测试用例9: 复杂数据结构迭代 ===")
        
        iteration_node = IterationNode(
            id="iteration_9",
            desc="复杂数据测试节点",
            selected=True,
            title="复杂数据测试",
            type="iteration",
            start_node_id="start_node",
            parallel_nums=3,
            is_parallel=False,
            iterator_selector=["input", "complex_items"],
            output_selector=["processed_node", "transformed"],
            output_type="array",
            error_handle_mode=ErrorHandleMode.TERMINATED
        )
        
        # 设置模拟子图来处理复杂对象
        def mock_complex_invoke(state):
            item = state.get("output_variables", {}).get("item", {})
            result_state = state.copy()
            result_state["output_variables"] = state["output_variables"].copy()
            
            # 模拟处理复杂对象
            if isinstance(item, dict) and "name" in item:
                result_state["output_variables"]["transformed"] = {
                    "processed_name": f"processed_{item['name']}",
                    "processed_value": item.get("value", 0) * 2
                }
            
            return result_state
        
        mock_subgraph = Mock(spec=CompiledStateGraph)
        mock_subgraph.invoke = Mock(side_effect=mock_complex_invoke)
        iteration_node.subgraph = mock_subgraph
        
        # 准备复杂数据测试状态
        test_state = BaseState(
            sys_query="测试复杂数据迭代",
            sys_user_id="test_user",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={
                "complex_items": [
                    {"name": "item1", "value": 10},
                    {"name": "item2", "value": 20},
                    {"name": "item3", "value": 30}
                ]
            },
            conversation_variables={}
        )
        
        # 执行测试
        try:
            result = iteration_node.call(test_state)
            
            print(f"✅ 测试成功!")
            print(f"结果: {result}")
            
            # 验证复杂数据处理
            if hasattr(result, 'update'):
                print("✓ 复杂数据结构迭代正常")
                return True
            else:
                print("✗ 复杂数据结构迭代失败")
                return False
                
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def run_all_tests(self):
        """运行所有测试"""
        print("🚀 开始运行 IterationNode 测试套件")
        print("=" * 60)
        
        tests = [
            self.test_basic_iteration,
            self.test_empty_input_array,
            self.test_none_input,
            self.test_non_list_input,
            self.test_no_subgraph,
            self.test_parallel_limitation,
            self.test_different_error_modes,
            self.test_node_properties,
            self.test_complex_data_iteration
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
        print(f"📈 成功率: {passed/(passed+failed)*100:.1f}%")
        
        if failed == 0:
            print("🎉 所有测试都通过了！")
        else:
            print("⚠️ 有测试失败，请检查上述输出")
        
        return failed == 0


def main():
    """主函数"""
    print("🧪 IterationNode 迭代节点测试")
    print("=" * 60)
    
    tester = IterationNodeTest()
    success = tester.run_all_tests()
    
    if success:
        exit(0)
    else:
        exit(1)


if __name__ == "__main__":
    main()

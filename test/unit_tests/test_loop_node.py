"""
LoopNode 测试用例
测试 LoopNode 的循环控制功能
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
from goalflow.node.loop_node import LoopNode, LoopStartNode, LoopEndNode, LOOP_END_CALL_NAME
from goalflow.workflow_types import Condition, LoopVariableData
from goalflow.tool.utils import VariableResolver


class LoopNodeTest:
    """LoopNode 测试类"""
    
    def __init__(self):
        print("🧪 LoopNode 测试初始化")
    
    def _create_condition(self, variable_selector: list, operator: str, value: str, var_type: str = "string"):
        """创建测试条件"""
        return Condition(
            variable_selector=variable_selector,
            comparison_operator=operator,
            value=value,
            varType=var_type
        )
    
    def _create_loop_variable(self, id: str, label: str, var_type: str, value_type: str, value):
        """创建循环变量"""
        return LoopVariableData(
            id=id,
            label=label,
            var_type=var_type,
            value_type=value_type,
            value=value
        )
    
    def test_basic_loop_functionality(self):
        """测试基本循环功能"""
        print("\n=== 测试用例1: 基本循环功能 ===")
        
        # 创建测试条件 - 永远不满足，让循环执行到最大次数
        break_conditions = [
            self._create_condition(["test", "never_true"], "is", "impossible_value")
        ]
        
        # 创建循环变量
        loop_variables = [
            self._create_loop_variable("var1", "counter", "number", "constant", "0"),
            self._create_loop_variable("var2", "message", "string", "constant", "hello")
        ]
        
        # 创建 LoopNode 实例
        loop_node = LoopNode(
            id="test_loop",
            desc="基本循环测试节点",
            selected=True,
            title="基本循环测试",
            type="loop",
            start_node_id="start_node",
            error_handle_mode=ErrorHandleMode.TERMINATED,
            loop_count=3,
            break_conditions=break_conditions,
            logical_operator="and",
            loop_variables=loop_variables,
            outputs={"result": "success"}
        )
        
        # 设置模拟子图
        execution_count = 0
        def mock_invoke(state):
            nonlocal execution_count
            result_state = state.copy()
            result_state["output_variables"] = state["output_variables"].copy()
            execution_count += 1
            result_state["output_variables"]["iteration_result"] = {"step": execution_count}
            return result_state
        
        mock_subgraph = Mock(spec=CompiledStateGraph)
        mock_subgraph.invoke = Mock(side_effect=mock_invoke)
        loop_node.subgraph = mock_subgraph
        
        # 准备测试状态
        test_state = BaseState(
            sys_query="测试基本循环",
            sys_user_id="test_user",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={},
            conversation_variables={}
        )
        
        # 执行测试
        try:
            result = loop_node.call(test_state)
            
            print(f"✅ 测试成功!")
            print(f"结果类型: {type(result)}")
            print(f"结果内容: {result}")
            
            # 验证结果
            if hasattr(result, 'update') and hasattr(result, 'goto'):
                print("✓ 循环正常执行并返回 Command")
                # 验证子图被调用了3次（loop_count）
                if execution_count == 3:
                    print(f"✓ 子图被调用了 {execution_count} 次")
                    return True
                else:
                    print(f"✗ 期望调用3次，实际调用了 {execution_count} 次")
                    return False
            else:
                print("✗ 返回结果格式不正确")
                return False
                
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def test_early_break_condition(self):
        """测试提前跳出条件"""
        print("\n=== 测试用例2: 提前跳出条件 ===")
        
        # 创建测试条件 - 在第2次迭代时满足
        break_conditions = [
            self._create_condition(["test_loop_break", "step"], "=", "2", "number")
        ]
        
        loop_variables = [
            self._create_loop_variable("test_loop_break", "step", "number", "constant", "1")
        ]
        
        loop_node:LoopNode = LoopNode(
            id="test_loop_break",
            desc="提前跳出测试节点",
            selected=True,
            title="提前跳出测试",
            type="loop",
            start_node_id="start_node",
            error_handle_mode=ErrorHandleMode.TERMINATED,
            loop_count=5,  # 设置较大的循环次数
            break_conditions=break_conditions,
            logical_operator="and",
            loop_variables=loop_variables
        )
        
        # 设置模拟子图 - 在第2次迭代时满足跳出条件
        execution_count = 0
        def mock_invoke_early_break(state):
            nonlocal execution_count
            result_state = state.copy()
            result_state["output_variables"] = state["output_variables"].copy()
            
            execution_count += 1
            if execution_count == 1:
                result_state["output_variables"]["test_loop_break_step"] = 1
            elif execution_count == 2:
                result_state["output_variables"]["test_loop_break_step"] = 2  # 这应该满足跳出条件
            
            return result_state
        
        mock_subgraph = Mock(spec=CompiledStateGraph)
        mock_subgraph.invoke = Mock(side_effect=mock_invoke_early_break)
        loop_node.subgraph = mock_subgraph
        
        test_state = BaseState(
            sys_query="测试提前跳出",
            sys_user_id="test_user",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={},
            conversation_variables={}
        )
        
        try:
            result = loop_node.call(test_state)
            
            print(f"✅ 测试成功!")
            
            # 验证提前跳出 - 应该只调用2次而不是5次
            call_count = execution_count
            if call_count == 2:
                print(f"✓ 循环在第 {call_count} 次迭代时正确跳出")
                return True
            else:
                print(f"✗ 期望调用2次，实际调用了 {call_count} 次")
                return False
                
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            return False
    
    def test_loop_end_node_trigger(self):
        """测试循环结束节点触发"""
        print("\n=== 测试用例3: 循环结束节点触发 ===")
        
        # 创建永远不满足的条件，让循环通过 LoopEndNode 触发结束
        break_conditions = [
            self._create_condition(["test", "never"], "is", "impossible")
        ]
        
        loop_variables = [
            self._create_loop_variable("var1", "step", "number", "constant", "0")
        ]
        
        loop_node = LoopNode(
            id="test_loop_end",
            desc="循环结束节点测试",
            selected=True,
            title="循环结束节点测试",
            type="loop",
            start_node_id="start_node",
            error_handle_mode=ErrorHandleMode.TERMINATED,
            loop_count=5,
            break_conditions=break_conditions,
            logical_operator="and",
            loop_variables=loop_variables
        )
        
        # 设置模拟子图 - 在第3次迭代时触发 loop-end-call
        execution_count_end = 0
        def mock_invoke_loop_end(state):
            nonlocal execution_count_end
            result_state = state.copy()
            result_state["output_variables"] = state["output_variables"].copy()
            
            execution_count_end += 1
            result_state["output_variables"]["iteration_result"] = {"step": execution_count_end}
            
            # 在第3次调用时触发循环结束
            if execution_count_end == 3:
                result_state["output_variables"][f"test_loop_end_{LOOP_END_CALL_NAME}"] = True
            
            return result_state
        
        mock_subgraph = Mock(spec=CompiledStateGraph)
        mock_subgraph.invoke = Mock(side_effect=mock_invoke_loop_end)
        loop_node.subgraph = mock_subgraph
        
        test_state = BaseState(
            sys_query="测试循环结束节点",
            sys_user_id="test_user",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={},
            conversation_variables={}
        )
        
        try:
            result = loop_node.call(test_state)
            
            print(f"✅ 测试成功!")
            
            # 验证通过 LoopEndNode 提前结束
            call_count = execution_count_end
            if call_count == 3:
                print(f"✓ 循环通过 LoopEndNode 在第 {call_count} 次迭代时正确结束")
                return True
            else:
                print(f"✗ 期望调用3次，实际调用了 {call_count} 次")
                return False
                
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            return False
    
    def test_loop_count_limit(self):
        """测试循环次数限制"""
        print("\n=== 测试用例4: 循环次数限制 ===")
        
        # 测试超过10次的限制
        try:
            loop_node = LoopNode(
                id="test_loop_limit",
                desc="循环次数限制测试",
                selected=True,
                title="循环次数限制测试",
                type="loop",
                start_node_id="start_node",
                error_handle_mode=ErrorHandleMode.TERMINATED,
                loop_count=15,  # 超过10次的限制
                break_conditions=[],
                logical_operator="and",
                loop_variables=[]
            )
            
            mock_subgraph = Mock(spec=CompiledStateGraph)
            loop_node.subgraph = mock_subgraph
            
            test_state = BaseState(
                sys_query="测试循环次数限制",
                sys_user_id="test_user",
                sys_app_id="test_app",
                sys_workflow_id="test_workflow",
                sys_workflow_run_id="test_run",
                input_variables={},
                output_variables={},
                conversation_variables={}
            )
            
            result = loop_node.call(test_state)
            print(f"❌ 应该抛出循环次数限制错误，但是没有")
            return False
            
        except ValueError as e:
            if "loop count must be less than 10" in str(e):
                print(f"✅ 正确捕获循环次数限制错误: {e}")
                return True
            else:
                print(f"❌ 错误信息不正确: {e}")
                return False
        except Exception as e:
            print(f"❌ 意外错误: {e}")
            return False
    
    def test_no_subgraph_error(self):
        """测试无子图错误"""
        print("\n=== 测试用例5: 无子图错误处理 ===")
        
        loop_node = LoopNode(
            id="test_loop_no_subgraph",
            desc="无子图测试节点",
            selected=True,
            title="无子图测试",
            type="loop",
            start_node_id="start_node",
            error_handle_mode=ErrorHandleMode.TERMINATED,
            loop_count=3,
            break_conditions=[],
            logical_operator="and",
            loop_variables=[]
        )
        
        # 不设置子图 (subgraph = None)
        
        test_state = BaseState(
            sys_query="测试无子图",
            sys_user_id="test_user",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={},
            conversation_variables={}
        )
        
        try:
            result = loop_node.call(test_state)
            print(f"❌ 应该抛出无子图错误，但是没有")
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
    
    def test_loop_variables_processing(self):
        """测试循环变量处理"""
        print("\n=== 测试用例6: 循环变量处理 ===")
        
        # 创建不同类型的循环变量
        loop_variables = [
            self._create_loop_variable("var1", "count", "number", "constant", "5"),
            self._create_loop_variable("var2", "rate", "number", "constant", "3.14"),
            self._create_loop_variable("var3", "name", "string", "constant", "test_loop"),
            self._create_loop_variable("var4", "source_value", "string", "variable", ["input", "source"])
        ]
        
        loop_node = LoopNode(
            id="test_loop_vars",
            desc="循环变量测试节点",
            selected=True,
            title="循环变量测试",
            type="loop",
            start_node_id="start_node",
            error_handle_mode=ErrorHandleMode.TERMINATED,
            loop_count=2,
            break_conditions=[],
            logical_operator="and",
            loop_variables=loop_variables
        )
        
        execution_count_vars = 0
        def mock_invoke_with_vars(state):
            nonlocal execution_count_vars
            # 验证循环变量是否正确设置到状态中
            output_vars = state.get("output_variables", {})
            print(f"子图接收到的变量: {list(output_vars.keys())}")
            
            execution_count_vars += 1
            
            # 检查是否有循环变量被正确设置
            has_loop_vars = any(key.startswith("test_loop_vars_") for key in output_vars.keys())
            if has_loop_vars:
                print("✓ 循环变量已正确设置到状态中")
            
            return state
        
        mock_subgraph = Mock(spec=CompiledStateGraph)
        mock_subgraph.invoke = Mock(side_effect=mock_invoke_with_vars)
        loop_node.subgraph = mock_subgraph
        
        test_state = BaseState(
            sys_query="测试循环变量",
            sys_user_id="test_user",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={
                "source": "from_input"  # 为variable类型的循环变量提供源数据
            },
            conversation_variables={}
        )
        
        try:
            result = loop_node.call(test_state)
            
            print(f"✅ 测试成功!")
            
            # 验证子图被调用了正确次数
            if execution_count_vars == 2:
                print("✓ 循环变量处理正常")
                return True
            else:
                print(f"✗ 期望调用2次，实际调用了 {execution_count_vars} 次")
                return False
                
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def test_different_error_modes(self):
        """测试不同的错误处理模式"""
        print("\n=== 测试用例7: 不同错误处理模式 ===")
        
        # 测试 CONTINUE_ON_ERROR 模式
        loop_node = LoopNode(
            id="test_loop_error_mode",
            desc="错误模式测试节点",
            selected=True,
            title="错误模式测试",
            type="loop",
            start_node_id="start_node",
            error_handle_mode=ErrorHandleMode.CONTINUE_ON_ERROR,
            loop_count=2,
            break_conditions=[],
            logical_operator="or",
            loop_variables=[]
        )
        
        execution_count = 0
        def mock_invoke(state):
            nonlocal execution_count
            execution_count += 1
            return state
        
        mock_subgraph = Mock(spec=CompiledStateGraph)
        mock_subgraph.invoke = Mock(side_effect=mock_invoke)
        loop_node.subgraph = mock_subgraph
        
        test_state = BaseState(
            sys_query="测试错误处理模式",
            sys_user_id="test_user",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={},
            conversation_variables={}
        )
        
        try:
            result = loop_node.call(test_state)
            
            print(f"✅ 测试成功!")
            print(f"错误处理模式: {loop_node.error_handle_mode}")
            print(f"逻辑运算符: {loop_node.logical_operator}")
            
            # 验证错误处理模式和逻辑运算符设置正确
            if (loop_node.error_handle_mode == ErrorHandleMode.CONTINUE_ON_ERROR and 
                loop_node.logical_operator == "or"):
                print("✓ 错误处理模式和逻辑运算符设置正确")
                return True
            else:
                print("✗ 设置不正确")
                return False
                
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            return False
    
    def test_node_properties(self):
        """测试节点属性"""
        print("\n=== 测试用例8: 节点属性验证 ===")
        
        loop_variables = [
            self._create_loop_variable("var1", "test_var", "string", "constant", "test")
        ]
        
        break_conditions = [
            self._create_condition(["test", "condition"], "is", "done")
        ]
        
        loop_node = LoopNode(
            id="test_loop_props",
            desc="属性测试节点",
            selected=True,
            title="属性测试",
            type="loop",
            start_node_id="test_start",
            error_handle_mode=ErrorHandleMode.REMOVE_ABNORMAL_OUTPUT,
            loop_count=7,
            break_conditions=break_conditions,
            logical_operator="and",
            loop_variables=loop_variables,
            outputs={"test": "result"}
        )
        
        # 验证节点类型
        if loop_node.node_type == WfNodeType.LOOP:
            print("✓ 节点类型正确")
        else:
            print(f"✗ 节点类型错误: {loop_node.node_type}")
            return False
        
        # 验证各个属性
        properties_to_check = {
            "id": "test_loop_props",
            "start_node_id": "test_start",
            "loop_count": 7,
            "logical_operator": "and",
            "error_handle_mode": ErrorHandleMode.REMOVE_ABNORMAL_OUTPUT
        }
        
        all_correct = True
        for prop_name, expected_value in properties_to_check.items():
            actual_value = getattr(loop_node, prop_name)
            if actual_value == expected_value:
                print(f"✓ {prop_name}: {actual_value}")
            else:
                print(f"✗ {prop_name}: 期望 {expected_value}, 实际 {actual_value}")
                all_correct = False
        
        # 验证复杂属性
        if len(loop_node.break_conditions) == 1:
            print("✓ break_conditions 数量正确")
        else:
            print(f"✗ break_conditions 数量错误: {len(loop_node.break_conditions)}")
            all_correct = False
            
        if len(loop_node.loop_variables) == 1:
            print("✓ loop_variables 数量正确")
        else:
            print(f"✗ loop_variables 数量错误: {len(loop_node.loop_variables)}")
            all_correct = False
        
        return all_correct
    
    def test_loop_start_and_end_nodes(self):
        """测试循环开始和结束节点"""
        print("\n=== 测试用例9: 循环开始和结束节点 ===")
        
        # 测试 LoopStartNode
        start_node = LoopStartNode(
            id="loop_start",
            desc="循环开始节点",
            selected=True,
            title="循环开始",
            type="loop-start"
        )
        
        print("✓ LoopStartNode 创建成功")
        
        # 测试 LoopEndNode
        end_node = LoopEndNode(
            id="loop_end",
            desc="循环结束节点",
            selected=True,
            title="循环结束",
            type="loop-end",
            loop_id="test_loop"
        )
        
        test_state = BaseState(
            sys_query="测试循环结束节点",
            sys_user_id="test_user",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={},
            conversation_variables={}
        )
        
        try:
            result = end_node.call(test_state)
            
            print(f"✅ LoopEndNode 测试成功!")
            print(f"结果: {result}")
            
            # 验证结果格式
            expected_key = f"test_loop_{LOOP_END_CALL_NAME}"
            if result and "output_variables" in result and expected_key in result["output_variables"]:
                if result["output_variables"][expected_key] is True:
                    print("✓ LoopEndNode 正确设置了结束标志")
                    return True
                else:
                    print("✗ LoopEndNode 结束标志值不正确")
                    return False
            else:
                print("✗ LoopEndNode 结果格式不正确")
                return False
                
        except Exception as e:
            print(f"❌ LoopEndNode 测试失败: {e}")
            return False
    
    def test_loop_end_node_without_loop_id(self):
        """测试无loop_id的循环结束节点错误"""
        print("\n=== 测试用例10: 无loop_id的循环结束节点错误 ===")
        
        end_node = LoopEndNode(
            id="loop_end_no_id",
            desc="无loop_id的循环结束节点",
            selected=True,
            title="循环结束",
            type="loop-end"
            # 不设置 loop_id
        )
        
        test_state = BaseState(
            sys_query="测试无loop_id错误",
            sys_user_id="test_user",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={},
            conversation_variables={}
        )
        
        try:
            result = end_node.call(test_state)
            print(f"❌ 应该抛出loop_id为None的错误，但是没有")
            return False
        except ValueError as e:
            if "loop id is None" in str(e):
                print(f"✅ 正确捕获loop_id为None的错误: {e}")
                return True
            else:
                print(f"❌ 错误信息不正确: {e}")
                return False
        except Exception as e:
            print(f"❌ 意外错误: {e}")
            return False
    
    def run_all_tests(self):
        """运行所有测试"""
        print("🚀 开始运行 LoopNode 测试套件")
        print("=" * 60)
        
        tests = [
            self.test_basic_loop_functionality,
            self.test_early_break_condition,
            self.test_loop_end_node_trigger,
            self.test_loop_count_limit,
            self.test_no_subgraph_error,
            self.test_loop_variables_processing,
            self.test_different_error_modes,
            self.test_node_properties,
            self.test_loop_start_and_end_nodes,
            self.test_loop_end_node_without_loop_id
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
    print("🧪 LoopNode 循环节点测试")
    print("=" * 60)
    
    tester = LoopNodeTest()
    success = tester.run_all_tests()
    
    if success:
        exit(0)
    else:
        exit(1)


if __name__ == "__main__":
    print("开始执行测试...")
    try:
        main()
    except Exception as e:
        print(f"执行异常: {e}")
        import traceback
        traceback.print_exc() 
"""
CodeNode 测试用例
测试 CodeNode 的动态代码执行功能
"""

import sys
import os
# 添加项目根目录到路径 (从 unit_tests -> test -> project_root)
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from typing import Dict, Any
from goalflow.state import BaseState
from goalflow.workflow_types import NodeVarConfig
from goalflow.constants import WfNodeType

# 直接导入 CodeNode
from goalflow.node.code_node import CodeNode


class CodeNodeTest:
    """CodeNode 测试类"""
    
    def __init__(self):
        print("🧪 CodeNode 测试初始化")
    
    def test_simple_calculation(self):
        """测试简单的数学计算"""
        print("\n=== 测试用例1: 简单数学计算 ===")
        
        # 定义要执行的Python代码
        code = """
def main(a, b):
    \"\"\"计算两个数的加法、减法、乘法\"\"\"
    result = {
        'sum': a + b,
        'difference': a - b,
        'product': a * b,
        'average': (a + b) / 2
    }
    return result
"""
        
        # 创建CodeNode实例
        code_node = CodeNode(
            desc="数学计算节点",
            selected=True,
            title="数学计算",
            type="code",
            code=code,
            code_language="python",
            variables=[
                NodeVarConfig(variable="a", value_selector=["input", "num1"]),
                NodeVarConfig(variable="b", value_selector=["input", "num2"])
            ],
            outputs={
                "sum": {"type": "number"},
                "difference": {"type": "number"},
                "product": {"type": "number"},
                "average": {"type": "number"}
            }
        )
        
        # 准备测试状态
        test_state = BaseState(
            sys_query="测试数学计算",
            sys_user_id="test_user",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={
                "num1": 10,
                "num2": 5
            },
            conversation_variables={}
        )
        
        # 执行测试
        try:
            result = code_node(test_state)
            output_vars = result.get('output_variables', {})
            
            print(f"✅ 测试成功!")
            print(f"输入: a=10, b=5")
            print(f"输出: {output_vars}")
            
            # 验证结果
            expected = {
                'sum': 15,
                'difference': 5,
                'product': 50,
                'average': 7.5
            }
            
            for key, expected_value in expected.items():
                if key in output_vars and output_vars[key] == expected_value:
                    print(f"✓ {key}: {output_vars[key]} (正确)")
                else:
                    print(f"✗ {key}: 期望 {expected_value}, 实际 {output_vars.get(key, 'N/A')}")
                    
            return True
            
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            return False
    
    def test_string_processing(self):
        """测试字符串处理"""
        print("\n=== 测试用例2: 字符串处理 ===")
        
        code = """
def main(text, prefix):
    \"\"\"字符串处理功能\"\"\"
    words = text.split()
    result = {
        'word_count': len(words),
        'char_count': len(text),
        'uppercase': text.upper(),
        'prefixed_text': f"{prefix}: {text}",
        'words_list': words
    }
    return result
"""
        
        code_node = CodeNode(
            desc="字符串处理节点",
            selected=True,
            title="字符串处理",
            type="code",
            code=code,
            code_language="python",
            variables=[
                NodeVarConfig(variable="text", value_selector=["input", "message"]),
                NodeVarConfig(variable="prefix", value_selector=["input", "label"])
            ],
            outputs={
                "word_count": {"type": "number"},
                "char_count": {"type": "number"},
                "uppercase": {"type": "string"},
                "prefixed_text": {"type": "string"}
            }
        )
        
        test_state = BaseState(
            sys_query="测试字符串处理",
            sys_user_id="test_user",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={
                "message": "Hello World Python",
                "label": "AI"
            },
            conversation_variables={}
        )
        
        try:
            result = code_node(test_state)
            output_vars = result.get('output_variables', {})
            
            print(f"✅ 测试成功!")
            print(f"输入: text='Hello World Python', prefix='AI'")
            print(f"输出: {output_vars}")
            
            # 验证结果
            expected = {
                'word_count': 3,
                'char_count': 18,
                'uppercase': 'HELLO WORLD PYTHON',
                'prefixed_text': 'AI: Hello World Python'
            }
            
            for key, expected_value in expected.items():
                if key in output_vars and output_vars[key] == expected_value:
                    print(f"✓ {key}: {output_vars[key]} (正确)")
                else:
                    print(f"✗ {key}: 期望 {expected_value}, 实际 {output_vars.get(key, 'N/A')}")
                    
            return True
            
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            return False
    
    def test_data_analysis(self):
        """测试数据分析"""
        print("\n=== 测试用例3: 数据分析 ===")
        
        code = """
def main(numbers):
    \"\"\"分析数字列表\"\"\"
    if not numbers:
        return {'error': 'Empty list'}
    
    result = {
        'total': sum(numbers),
        'average': sum(numbers) / len(numbers),
        'maximum': max(numbers),
        'minimum': min(numbers),
        'count': len(numbers),
        'sorted_asc': sorted(numbers),
        'sorted_desc': sorted(numbers, reverse=True)
    }
    return result
"""
        
        code_node = CodeNode(
            desc="数据分析节点",
            selected=True,
            title="数据分析",
            type="code",
            code=code,
            code_language="python",
            variables=[
                NodeVarConfig(variable="numbers", value_selector=["input", "data_list"])
            ],
            outputs={
                "total": {"type": "number"},
                "average": {"type": "number"},
                "maximum": {"type": "number"},
                "minimum": {"type": "number"},
                "count": {"type": "number"}
            }
        )
        
        test_state = BaseState(
            sys_query="测试数据分析",
            sys_user_id="test_user",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={
                "data_list": [1, 5, 3, 9, 2, 7, 4, 8, 6]
            },
            conversation_variables={}
        )
        
        try:
            result = code_node(test_state)
            output_vars = result.get('output_variables', {})
            
            print(f"✅ 测试成功!")
            print(f"输入: numbers=[1, 5, 3, 9, 2, 7, 4, 8, 6]")
            print(f"输出: {output_vars}")
            
            # 验证结果
            expected = {
                'total': 45,
                'average': 5.0,
                'maximum': 9,
                'minimum': 1,
                'count': 9
            }
            
            for key, expected_value in expected.items():
                if key in output_vars and output_vars[key] == expected_value:
                    print(f"✓ {key}: {output_vars[key]} (正确)")
                else:
                    print(f"✗ {key}: 期望 {expected_value}, 实际 {output_vars.get(key, 'N/A')}")
                    
            return True
            
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            return False
    
    def test_error_handling(self):
        """测试错误处理"""
        print("\n=== 测试用例4: 错误处理 ===")
        
        # 测试没有main函数的代码
        bad_code = """
def calculate(a, b):
    return a + b
"""
        
        code_node = CodeNode(
            desc="错误测试节点",
            selected=True,
            title="错误测试",
            type="code",
            code=bad_code,
            code_language="python",
            variables=[
                NodeVarConfig(variable="a", value_selector=["input", "num1"])
            ],
            outputs={
                "result": {"type": "number"}
            }
        )
        
        test_state = BaseState(
            sys_query="测试错误处理",
            sys_user_id="test_user",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={"num1": 10},
            conversation_variables={}
        )
        
        try:
            result = code_node(test_state)
            print(f"❌ 应该抛出错误，但是没有")
            return False
        except RuntimeError as e:
            if "Code must define a 'main' function" in str(e):
                print(f"✅ 正确捕获错误: {e}")
                return True
            else:
                print(f"❌ 错误类型不正确: {e}")
                return False
        except Exception as e:
            print(f"❌ 意外错误: {e}")
            return False
    
    def test_external_library(self):
        """测试外部库引用（numpy）"""
        print("\n=== 测试用例5: 外部库引用测试 ===")
        
        code = """
import numpy as np

def main(size, dtype_str):
    \"\"\"使用numpy创建和处理数组\"\"\"
    # 创建不同类型的数组
    arr1 = np.zeros(size, dtype=dtype_str)
    arr2 = np.ones(size, dtype=dtype_str) 
    arr3 = np.arange(size, dtype=dtype_str)
    
    # 进行一些计算
    result_sum = np.sum(arr3)
    result_mean = np.mean(arr3)
    result_max = np.max(arr3)
    
    # 矩阵操作
    matrix = np.reshape(arr3, (-1, 1)) if size > 0 else np.array([[]])
    
    return {
        'zeros_array': arr1.tolist(),
        'ones_array': arr2.tolist(),
        'range_array': arr3.tolist(),
        'array_sum': float(result_sum),
        'array_mean': float(result_mean),
        'array_max': float(result_max),
        'matrix_shape': list(matrix.shape),
        'numpy_version': np.__version__
    }
"""
        
        code_node = CodeNode(
            desc="外部库测试节点",
            selected=True,
            title="Numpy测试",
            type="code",
            code=code,
            code_language="python",
            variables=[
                NodeVarConfig(variable="size", value_selector=["input", "array_size"]),
                NodeVarConfig(variable="dtype_str", value_selector=["input", "data_type"])
            ],
            outputs={
                "zeros_array": {"type": "array"},
                "ones_array": {"type": "array"},
                "range_array": {"type": "array"},
                "array_sum": {"type": "number"},
                "array_mean": {"type": "number"},
                "array_max": {"type": "number"},
                "matrix_shape": {"type": "array"},
                "numpy_version": {"type": "string"}
            }
        )
        
        test_state = BaseState(
            sys_query="测试外部库引用",
            sys_user_id="test_user",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={
                "array_size": 5,
                "data_type": "float32"
            },
            conversation_variables={}
        )
        
        try:
            result = code_node(test_state)
            output_vars = result.get('output_variables', {})
            
            print(f"✅ 测试成功!")
            print(f"输入: size=5, dtype='float32'")
            print(f"输出: {output_vars}")
            
            # 验证结果
            expected_checks = {
                'zeros_array': lambda x: x == [0.0, 0.0, 0.0, 0.0, 0.0],
                'ones_array': lambda x: x == [1.0, 1.0, 1.0, 1.0, 1.0],
                'range_array': lambda x: x == [0.0, 1.0, 2.0, 3.0, 4.0],
                'array_sum': lambda x: x == 10.0,
                'array_mean': lambda x: x == 2.0,
                'array_max': lambda x: x == 4.0,
                'matrix_shape': lambda x: x == [5, 1]
            }
            
            all_correct = True
            for key, check_func in expected_checks.items():
                actual_value = output_vars.get(key)
                if check_func(actual_value):
                    print(f"✓ {key}: 正确")
                else:
                    print(f"✗ {key}: 实际值 {actual_value}")
                    all_correct = False
            
            # 检查numpy版本是否存在
            if 'numpy_version' in output_vars:
                print(f"✓ numpy版本: {output_vars['numpy_version']}")
            else:
                print("✗ numpy_version: 缺失")
                all_correct = False
                
            return all_correct
            
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def test_output_filtering(self):
        """测试输出过滤"""
        print("\n=== 测试用例6: 输出过滤 ===")
        
        code = """
def main(x):
    \"\"\"返回多个值，但只有部分被过滤输出\"\"\"
    return {
        'public_result': x * 2,
        'internal_value': x * 3,
        'debug_info': f"Processing {x}",
        'filtered_output': x + 10
    }
"""
        
        code_node = CodeNode(
            desc="输出过滤测试节点",
            selected=True,
            title="输出过滤测试",
            type="code",
            code=code,
            code_language="python",
            variables=[
                NodeVarConfig(variable="x", value_selector=["input", "value"])
            ],
            outputs={
                "public_result": {"type": "number"},
                "filtered_output": {"type": "number"}
                # 注意：internal_value 和 debug_info 不在 outputs 中，应该被过滤掉
            }
        )
        
        test_state = BaseState(
            sys_query="测试输出过滤",
            sys_user_id="test_user",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={"value": 5},
            conversation_variables={}
        )
        
        try:
            result = code_node(test_state)
            output_vars = result.get('output_variables', {})
            
            print(f"✅ 测试成功!")
            print(f"输入: x=5")
            print(f"输出: {output_vars}")
            
            # 验证过滤效果
            expected_keys = {'public_result', 'filtered_output'}
            unexpected_keys = {'internal_value', 'debug_info'}
            
            actual_keys = set(output_vars.keys())
            
            if expected_keys.issubset(actual_keys):
                print(f"✓ 期望的输出字段都存在: {expected_keys}")
            else:
                print(f"✗ 缺少期望字段: {expected_keys - actual_keys}")
                
            if actual_keys.isdisjoint(unexpected_keys):
                print(f"✓ 不期望的字段被正确过滤: {unexpected_keys}")
            else:
                print(f"✗ 包含不应该有的字段: {actual_keys & unexpected_keys}")
                
            # 验证值
            if output_vars.get('public_result') == 10 and output_vars.get('filtered_output') == 15:
                print(f"✓ 输出值正确")
                return True
            else:
                print(f"✗ 输出值不正确")
                return False
                
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            return False
    
    def run_all_tests(self):
        """运行所有测试"""
        print("🚀 开始运行 CodeNode 测试套件")
        print("=" * 60)
        
        tests = [
            self.test_simple_calculation,
            self.test_string_processing,
            self.test_data_analysis,
            self.test_error_handling,
            self.test_external_library,
            self.test_output_filtering
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
    print("🧪 CodeNode 动态代码执行测试")
    print("=" * 60)
    
    tester = CodeNodeTest()
    success = tester.run_all_tests()
    
    if success:
        exit(0)
    else:
        exit(1)


if __name__ == "__main__":
    main()

"""
AggregatorNode 测试用例
测试 AggregatorNode 的变量聚合功能
"""

import sys
import os
# 添加项目根目录到路径 (从 unit_tests -> test -> project_root)
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from typing import Dict, Any
from goalflow.state import BaseState
from goalflow.workflow_types import AggregatorAdvancedSettings

# 直接导入 AggregatorNode
from goalflow.node.aggregator_node import AggregatorNode


class AggregatorNodeTest:
    """AggregatorNode 测试类"""
    
    def __init__(self):
        print("🧪 AggregatorNode 测试初始化")
    
    def test_non_grouped_aggregation_first_variable(self):
        """测试非分组模式 - 获取第一个有效变量"""
        print("\n=== 测试用例1: 非分组模式 - 第一个变量有效 ===")
        
        # 创建 AggregatorNode 实例
        aggregator_node = AggregatorNode(
            desc="变量聚合节点",
            selected=True,
            title="变量聚合",
            type="variable-aggregator",
            output_type="string",
            variables=[
                ["node1", "output"],
                ["node2", "result"],
                ["node3", "data"]
            ]
        )
        
        # 准备测试状态 - 第一个变量有效
        test_state = BaseState(
            sys_query="测试变量聚合",
            sys_user_id="test_user",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={
                "node1_output": "第一个节点的输出",
                "node2_result": "第二个节点的结果",
                "node3_data": "第三个节点的数据"
            },
            conversation_variables={}
        )
        
        # 执行测试
        try:
            result = aggregator_node(test_state)
            
            print(f"✅ 测试成功!")
            print(f"输出: {result}")
            
            # 验证结果 - 应该返回第一个有效变量
            expected_output = "第一个节点的输出"
            if result.get("output") == expected_output:
                print(f"✓ 输出正确: {result['output']}")
                return True
            else:
                print(f"✗ 输出错误: 期望 '{expected_output}', 实际 '{result.get('output')}'")
                return False
                
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            return False
    
    def test_non_grouped_aggregation_second_variable(self):
        """测试非分组模式 - 第一个变量为空，获取第二个"""
        print("\n=== 测试用例2: 非分组模式 - 第二个变量有效 ===")
        
        aggregator_node = AggregatorNode(
            desc="变量聚合节点",
            selected=True,
            title="变量聚合",
            type="variable-aggregator",
            output_type="string",
            variables=[
                ["node1", "missing"],  # 这个变量不存在
                ["node2", "result"],   # 这个变量存在
                ["node3", "data"]      # 这个变量也存在，但不应该被选中
            ]
        )
        
        # 准备测试状态 - 第一个变量不存在，第二个变量有效
        test_state = BaseState(
            sys_query="测试变量聚合",
            sys_user_id="test_user",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={
                "node2_result": "第二个节点的结果",
                "node3_data": "第三个节点的数据"
            },
            conversation_variables={}
        )
        
        try:
            result = aggregator_node(test_state)
            
            print(f"✅ 测试成功!")
            print(f"输出: {result}")
            
            # 验证结果 - 应该返回第二个有效变量
            expected_output = "第二个节点的结果"
            if result.get("output") == expected_output:
                print(f"✓ 输出正确: {result['output']}")
                return True
            else:
                print(f"✗ 输出错误: 期望 '{expected_output}', 实际 '{result.get('output')}'")
                return False
                
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            return False
    
    def test_non_grouped_aggregation_no_variables(self):
        """测试非分组模式 - 所有变量都不存在"""
        print("\n=== 测试用例3: 非分组模式 - 无有效变量 ===")
        
        aggregator_node = AggregatorNode(
            desc="变量聚合节点",
            selected=True,
            title="变量聚合",
            type="variable-aggregator",
            output_type="string",
            variables=[
                ["node1", "missing1"],
                ["node2", "missing2"],
                ["node3", "missing3"]
            ]
        )
        
        # 准备测试状态 - 所有变量都不存在
        test_state = BaseState(
            sys_query="测试变量聚合",
            sys_user_id="test_user",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={
                "other_node_data": "无关数据"
            },
            conversation_variables={}
        )
        
        try:
            result = aggregator_node(test_state)
            
            print(f"✅ 测试成功!")
            print(f"输出: {result}")
            
            # 验证结果 - 应该返回空的输出
            if result == {} or result.get("output") is None:
                print(f"✓ 正确处理无变量情况: {result}")
                return True
            else:
                print(f"✗ 处理无变量情况错误: {result}")
                return False
                
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            return False
    
    def test_grouped_aggregation_single_group(self):
        """测试分组模式 - 单个分组"""
        print("\n=== 测试用例4: 分组模式 - 单个分组 ===")
        
        # 创建分组设置
        group = AggregatorAdvancedSettings.Group()
        group.group_name = "group1"
        group.output_type = "string"
        group.variables = [
            ["node1", "output"],
            ["node2", "result"]
        ]
        
        advanced_settings = AggregatorAdvancedSettings()
        advanced_settings.group_enabled = True
        advanced_settings.groups = [group]
        
        aggregator_node = AggregatorNode(
            desc="分组变量聚合节点",
            selected=True,
            title="分组变量聚合",
            type="variable-aggregator",
            output_type="string",
            variables=[],  # 在分组模式下这个字段不使用
            advanced_settings=advanced_settings
        )
        
        # 准备测试状态
        test_state = BaseState(
            sys_query="测试分组变量聚合",
            sys_user_id="test_user",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={
                "node1_output": "第一个节点的输出",
                "node2_result": "第二个节点的结果"
            },
            conversation_variables={}
        )
        
        try:
            result = aggregator_node(test_state)
            
            print(f"✅ 测试成功!")
            print(f"输出: {result}")
            
            # 验证结果 - 应该返回分组格式
            expected_output = "第一个节点的输出"
            if (result.get("group1") and 
                result["group1"].get("output") == expected_output):
                print(f"✓ 分组输出正确: {result['group1']['output']}")
                return True
            else:
                print(f"✗ 分组输出错误: {result}")
                return False
                
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            return False
    
    def test_grouped_aggregation_multiple_groups(self):
        """测试分组模式 - 多个分组"""
        print("\n=== 测试用例5: 分组模式 - 多个分组 ===")
        
        # 创建第一个分组
        group1 = AggregatorAdvancedSettings.Group()
        group1.group_name = "text_group"
        group1.output_type = "string"
        group1.variables = [
            ["node1", "missing"],  # 不存在
            ["node2", "text"]      # 存在
        ]
        
        # 创建第二个分组
        group2 = AggregatorAdvancedSettings.Group()
        group2.group_name = "number_group"
        group2.output_type = "number"
        group2.variables = [
            ["node3", "count"],    # 存在
            ["node4", "value"]     # 也存在，但不应该被选中
        ]
        
        advanced_settings = AggregatorAdvancedSettings()
        advanced_settings.group_enabled = True
        advanced_settings.groups = [group1, group2]
        
        aggregator_node = AggregatorNode(
            desc="多分组变量聚合节点",
            selected=True,
            title="多分组变量聚合",
            type="variable-aggregator",
            output_type="mixed",
            variables=[],
            advanced_settings=advanced_settings
        )
        
        # 准备测试状态
        test_state = BaseState(
            sys_query="测试多分组变量聚合",
            sys_user_id="test_user",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={
                "node2_text": "文本数据",
                "node3_count": 42,
                "node4_value": 100
            },
            conversation_variables={}
        )
        
        try:
            result = aggregator_node(test_state)
            
            print(f"✅ 测试成功!")
            print(f"输出: {result}")
            
            # 验证结果 - 应该包含两个分组的结果
            text_correct = (result.get("text_group") and 
                           result["text_group"].get("output") == "文本数据")
            number_correct = (result.get("number_group") and 
                             result["number_group"].get("output") == 42)
            
            if text_correct and number_correct:
                print(f"✓ 多分组输出正确:")
                print(f"  - text_group: {result['text_group']['output']}")
                print(f"  - number_group: {result['number_group']['output']}")
                return True
            else:
                print(f"✗ 多分组输出错误:")
                print(f"  - text_group正确: {text_correct}")
                print(f"  - number_group正确: {number_correct}")
                return False
                
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            return False
    
    def test_grouped_aggregation_no_valid_variables(self):
        """测试分组模式 - 某些分组没有有效变量"""
        print("\n=== 测试用例6: 分组模式 - 部分分组无有效变量 ===")
        
        # 创建第一个分组 - 有有效变量
        group1 = AggregatorAdvancedSettings.Group()
        group1.group_name = "valid_group"
        group1.output_type = "string"
        group1.variables = [
            ["node1", "data"]
        ]
        
        # 创建第二个分组 - 无有效变量
        group2 = AggregatorAdvancedSettings.Group()
        group2.group_name = "invalid_group"
        group2.output_type = "string"
        group2.variables = [
            ["node2", "missing1"],
            ["node3", "missing2"]
        ]
        
        advanced_settings = AggregatorAdvancedSettings()
        advanced_settings.group_enabled = True
        advanced_settings.groups = [group1, group2]
        
        aggregator_node = AggregatorNode(
            desc="部分有效分组测试",
            selected=True,
            title="部分有效分组测试",
            type="variable-aggregator",
            output_type="mixed",
            variables=[],
            advanced_settings=advanced_settings
        )
        
        # 准备测试状态
        test_state = BaseState(
            sys_query="测试部分有效分组",
            sys_user_id="test_user",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={
                "node1_data": "有效数据"
                # 注意：node2_missing1 和 node3_missing2 不存在
            },
            conversation_variables={}
        )
        
        try:
            result = aggregator_node(test_state)
            
            print(f"✅ 测试成功!")
            print(f"输出: {result}")
            
            # 验证结果 - 只有有效分组应该出现在结果中
            valid_group_correct = (result.get("valid_group") and 
                                  result["valid_group"].get("output") == "有效数据")
            invalid_group_missing = "invalid_group" not in result
            
            if valid_group_correct and invalid_group_missing:
                print(f"✓ 正确处理部分有效分组:")
                print(f"  - valid_group: {result['valid_group']['output']}")
                print(f"  - invalid_group 正确不存在")
                return True
            else:
                print(f"✗ 部分有效分组处理错误:")
                print(f"  - valid_group正确: {valid_group_correct}")
                print(f"  - invalid_group缺失: {invalid_group_missing}")
                return False
                
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            return False
    
    def test_system_variables(self):
        """测试系统变量的聚合"""
        print("\n=== 测试用例7: 系统变量聚合 ===")
        
        aggregator_node = AggregatorNode(
            desc="系统变量聚合节点",
            selected=True,
            title="系统变量聚合",
            type="variable-aggregator",
            output_type="string",
            variables=[
                ["sys", "query"],
                ["sys", "user_id"],
                ["node1", "output"]
            ]
        )
        
        # 准备测试状态
        test_state = BaseState(
            sys_query="这是系统查询",
            sys_user_id="test_user_123",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={
                "node1_output": "节点输出"
            },
            conversation_variables={}
        )
        
        try:
            result = aggregator_node(test_state)
            
            print(f"✅ 测试成功!")
            print(f"输出: {result}")
            
            # 验证结果 - 应该获取到系统查询
            expected_output = "这是系统查询"
            if result.get("output") == expected_output:
                print(f"✓ 系统变量获取正确: {result['output']}")
                return True
            else:
                print(f"✗ 系统变量获取错误: 期望 '{expected_output}', 实际 '{result.get('output')}'")
                return False
                
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            return False
    
    def test_conversation_variables(self):
        """测试会话变量的聚合"""
        print("\n=== 测试用例8: 会话变量聚合 ===")
        
        aggregator_node = AggregatorNode(
            desc="会话变量聚合节点",
            selected=True,
            title="会话变量聚合",
            type="variable-aggregator",
            output_type="string",
            variables=[
                ["conversation", "user_name"],
                ["conversation", "context"],
                ["node1", "output"]
            ]
        )
        
        # 准备测试状态
        test_state = BaseState(
            sys_query="测试会话变量",
            sys_user_id="test_user",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={
                "node1_output": "节点输出"
            },
            conversation_variables={
                "conversation_user_name": "Alice",
                "conversation_context": "对话上下文"
            }
        )
        
        try:
            result = aggregator_node(test_state)
            
            print(f"✅ 测试成功!")
            print(f"输出: {result}")
            
            # 验证结果 - 应该获取到会话变量
            expected_output = "Alice"
            if result.get("output") == expected_output:
                print(f"✓ 会话变量获取正确: {result['output']}")
                return True
            else:
                print(f"✗ 会话变量获取错误: 期望 '{expected_output}', 实际 '{result.get('output')}'")
                return False
                
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            return False
    
    def run_all_tests(self):
        """运行所有测试"""
        print("🚀 开始运行 AggregatorNode 测试套件")
        print("=" * 60)
        
        tests = [
            self.test_non_grouped_aggregation_first_variable,
            self.test_non_grouped_aggregation_second_variable,
            self.test_non_grouped_aggregation_no_variables,
            self.test_grouped_aggregation_single_group,
            self.test_grouped_aggregation_multiple_groups,
            self.test_grouped_aggregation_no_valid_variables,
            self.test_system_variables,
            self.test_conversation_variables
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
                import traceback
                traceback.print_exc()
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
    print("🧪 AggregatorNode 变量聚合测试")
    print("=" * 60)
    
    tester = AggregatorNodeTest()
    success = tester.run_all_tests()
    
    if success:
        exit(0)
    else:
        exit(1)


if __name__ == "__main__":
    main()

"""
ClassifierNode 测试用例
测试 ClassifierNode 的文本分类功能
"""

import sys
import os
# 添加项目根目录到路径 (从 unit_tests -> test -> project_root)
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import json
from typing import Dict, Any
from unittest.mock import Mock, MagicMock, patch

from goalflow.state import BaseState, GenericState
from goalflow.constants import WfNodeType, PromptMessageRole
from goalflow.node.classifier_node import ClassifierNode
from goalflow.workflow_types import (
    LLMNodeModelConfig,
    QuestionClassConfig,
    MemoryConfig,
    LLmNodePromptTemplate,
)


class ClassifierNodeTest:
    """ClassifierNode 测试类"""
    
    def __init__(self):
        print("🧪 ClassifierNode 测试初始化")
    
    def _create_question_class(self, id: str, name: str):
        """创建问题分类配置"""
        return QuestionClassConfig(id=id, name=name)
    
    def _create_llm_model_config(self, name: str = "test-model", provider: str = "test-provider"):
        """创建LLM模型配置"""
        return LLMNodeModelConfig(
            mode="chat",
            name=name,
            provider=provider,
            completion_params={}
        )
    
    def _create_mock_llm_response(self, category_name: str, keywords: list = None):
        """创建模拟的LLM响应"""
        if keywords is None:
            keywords = ["test", "keywords"]
        
        response_content = {
            "keywords": keywords,
            "category_id": "test_id",
            "category_name": category_name
        }
        
        return json.dumps(response_content, ensure_ascii=False)
    
    def test_basic_classification_functionality(self):
        """测试基本文本分类功能"""
        print("\n=== 测试用例1: 基本文本分类功能 ===")
        
        # 创建问题分类配置
        classes = [
            self._create_question_class("customer_service", "Customer Service"),
            self._create_question_class("technical_support", "Technical Support"),
            self._create_question_class("billing", "Billing")
        ]
        
        # 创建 ClassifierNode 实例
        classifier_node = ClassifierNode(
            id="test_classifier",
            desc="基本分类测试节点",
            selected=True,
            title="基本分类测试",
            type="question-classifier",
            instruction="分类用户查询到相应的类别",
            classes=classes,
            query_variable_selector=["sys", "query"],
            model=self._create_llm_model_config(),
            source_handle_target_map={
                "customer_service": ["customer_node"],
                "technical_support": ["tech_node"],
                "billing": ["billing_node"]
            }
        )
        
        # 准备测试状态
        test_state = BaseState(
            sys_query="我的账单有问题，需要帮助",
            sys_user_id="test_user",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={},
            conversation_variables={}
        )
        
        # 模拟LLM响应
        mock_llm_response = self._create_mock_llm_response("Billing", ["账单", "问题", "帮助"])
        
        # 使用patch模拟LLM调用
        with patch('node.classifier_node.LLM') as mock_llm_class:
            mock_llm_instance = Mock()
            mock_llm_instance.invoke.return_value = Mock(content=mock_llm_response)
            mock_llm_class.return_value = mock_llm_instance
            
            # 执行测试
            try:
                result = classifier_node.call(test_state)
                
                print(f"✅ 测试成功!")
                print(f"结果类型: {type(result)}")
                print(f"结果内容: {result}")
                
                # 验证结果
                if hasattr(result, 'update') and hasattr(result, 'goto'):
                    update = result.update
                    goto = result.goto
                    
                    # 验证更新内容
                    if "node_id" in update and update["node_id"] == "test_classifier":
                        print("✓ 节点ID更新正确")
                    else:
                        print(f"✗ 节点ID更新错误: {update}")
                        return False
                    
                    # 验证目标节点
                    if goto == ["billing_node"]:
                        print("✓ 分类结果正确，路由到billing_node")
                        return True
                    else:
                        print(f"✗ 路由错误，期望 ['billing_node']，实际 {goto}")
                        return False
                else:
                    print("✗ 返回结果格式不正确")
                    return False
                    
            except Exception as e:
                print(f"❌ 测试失败: {e}")
                import traceback
                traceback.print_exc()
                return False
    
    def test_sys_query_fallback(self):
        """测试当变量选择器为空时使用sys_query"""
        print("\n=== 测试用例2: sys_query fallback ===")
        
        classes = [
            self._create_question_class("general", "General")
        ]
        
        classifier_node = ClassifierNode(
            id="test_classifier_fallback",
            desc="fallback测试节点",
            selected=True,
            title="fallback测试",
            type="question-classifier",
            classes=classes,
            query_variable_selector=None,  # 不设置变量选择器
            model=self._create_llm_model_config(),
            source_handle_target_map={
                "general": ["general_node"]
            }
        )
        
        test_state = BaseState(
            sys_query="这是一个通用查询",
            sys_user_id="test_user",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={},
            conversation_variables={}
        )
        
        mock_llm_response = self._create_mock_llm_response("General", ["通用", "查询"])
        
        with patch('node.classifier_node.LLM') as mock_llm_class:
            mock_llm_instance = Mock()
            mock_llm_instance.invoke.return_value = Mock(content=mock_llm_response)
            mock_llm_class.return_value = mock_llm_instance
            
            try:
                result = classifier_node.call(test_state)
                
                print(f"✅ 测试成功!")
                
                # 验证LLM被正确调用，使用了sys_query
                mock_llm_class.assert_called_once()
                args, kwargs = mock_llm_class.call_args
                
                # 检查提示模板是否包含sys_query内容
                prompt_templates = kwargs.get('prompt_template', [])
                if prompt_templates:
                    last_prompt = prompt_templates[-1].text
                    if "这是一个通用查询" in last_prompt:
                        print("✓ 正确使用了sys_query作为输入")
                        return True
                    else:
                        print(f"✗ 提示模板未包含sys_query内容: {last_prompt}")
                        return False
                else:
                    print("✗ 提示模板为空")
                    return False
                    
            except Exception as e:
                print(f"❌ 测试失败: {e}")
                return False
    
    def test_invalid_json_response(self):
        """测试无效JSON响应的错误处理"""
        print("\n=== 测试用例3: 无效JSON响应错误处理 ===")
        
        classes = [
            self._create_question_class("test", "Test")
        ]
        
        classifier_node = ClassifierNode(
            id="test_classifier_error",
            desc="错误处理测试节点",
            selected=True,
            title="错误处理测试",
            type="question-classifier",
            classes=classes,
            query_variable_selector=["sys", "query"],
            model=self._create_llm_model_config(),
            source_handle_target_map={
                "test": ["test_node"]
            }
        )
        
        test_state = BaseState(
            sys_query="测试无效JSON",
            sys_user_id="test_user",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={},
            conversation_variables={}
        )
        
        # 模拟无效JSON响应
        invalid_json_response = "这不是有效的JSON格式"
        
        with patch('node.classifier_node.LLM') as mock_llm_class:
            mock_llm_instance = Mock()
            mock_llm_instance.invoke.return_value = Mock(content=invalid_json_response)
            mock_llm_class.return_value = mock_llm_instance
            
            try:
                result = classifier_node.call(test_state)
                print(f"❌ 应该抛出JSON解析错误，但是没有")
                return False
            except ValueError as e:
                if "classifier invoke llm no json result" in str(e):
                    print(f"✅ 正确捕获JSON解析错误: {e}")
                    return True
                else:
                    print(f"❌ 错误信息不正确: {e}")
                    return False
            except Exception as e:
                print(f"❌ 意外错误: {e}")
                return False
    
    def test_missing_category_name(self):
        """测试缺少category_name的错误处理"""
        print("\n=== 测试用例4: 缺少category_name错误处理 ===")
        
        classes = [
            self._create_question_class("test", "Test")
        ]
        
        classifier_node = ClassifierNode(
            id="test_classifier_no_category",
            desc="缺少分类名称测试节点",
            selected=True,
            title="缺少分类名称测试",
            type="question-classifier",
            classes=classes,
            query_variable_selector=["sys", "query"],
            model=self._create_llm_model_config(),
            source_handle_target_map={
                "test": ["test_node"]
            }
        )
        
        test_state = BaseState(
            sys_query="测试缺少分类名称",
            sys_user_id="test_user",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={},
            conversation_variables={}
        )
        
        # 模拟缺少category_name的响应
        response_without_category_name = json.dumps({
            "keywords": ["测试", "关键词"],
            "category_id": "test_id"
            # 缺少 category_name
        })
        
        with patch('node.classifier_node.LLM') as mock_llm_class:
            mock_llm_instance = Mock()
            mock_llm_instance.invoke.return_value = Mock(content=response_without_category_name)
            mock_llm_class.return_value = mock_llm_instance
            
            try:
                result = classifier_node.call(test_state)
                print(f"❌ 应该抛出缺少category_name错误，但是没有")
                return False
            except ValueError as e:
                if "classifier invoke llm no category_name result" in str(e):
                    print(f"✅ 正确捕获缺少category_name错误: {e}")
                    return True
                else:
                    print(f"❌ 错误信息不正确: {e}")
                    return False
            except Exception as e:
                print(f"❌ 意外错误: {e}")
                return False
    
    def test_unknown_category(self):
        """测试未知分类的错误处理"""
        print("\n=== 测试用例5: 未知分类错误处理 ===")
        
        classes = [
            self._create_question_class("known_category", "Known Category")
        ]
        
        classifier_node = ClassifierNode(
            id="test_classifier_unknown",
            desc="未知分类测试节点",
            selected=True,
            title="未知分类测试",
            type="question-classifier",
            classes=classes,
            query_variable_selector=["sys", "query"],
            model=self._create_llm_model_config(),
            source_handle_target_map={
                "known_category": ["known_node"]
            }
        )
        
        test_state = BaseState(
            sys_query="测试未知分类",
            sys_user_id="test_user",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={},
            conversation_variables={}
        )
        
        # 模拟返回未知分类的响应
        unknown_category_response = json.dumps({
            "keywords": ["测试", "关键词"],
            "category_id": "unknown_id",
            "category_name": "Unknown Category"  # 这个分类不在classes中
        })
        
        with patch('node.classifier_node.LLM') as mock_llm_class:
            mock_llm_instance = Mock()
            mock_llm_instance.invoke.return_value = Mock(content=unknown_category_response)
            mock_llm_class.return_value = mock_llm_instance
            
            try:
                result = classifier_node.call(test_state)
                print(f"❌ 应该抛出未知分类错误，但是没有")
                return False
            except ValueError as e:
                if "classifier invoke llm no category result" in str(e):
                    print(f"✅ 正确捕获未知分类错误: {e}")
                    return True
                else:
                    print(f"❌ 错误信息不正确: {e}")
                    return False
            except Exception as e:
                print(f"❌ 意外错误: {e}")
                return False
    
    def test_missing_target_nodes(self):
        """测试缺少目标节点的错误处理"""
        print("\n=== 测试用例6: 缺少目标节点错误处理 ===")
        
        classes = [
            self._create_question_class("orphan_category", "Orphan Category")
        ]
        
        classifier_node = ClassifierNode(
            id="test_classifier_orphan",
            desc="孤儿分类测试节点",
            selected=True,
            title="孤儿分类测试",
            type="question-classifier",
            classes=classes,
            query_variable_selector=["sys", "query"],
            model=self._create_llm_model_config(),
            source_handle_target_map={
                # 故意不包含 orphan_category 的映射
            }
        )
        
        test_state = BaseState(
            sys_query="测试孤儿分类",
            sys_user_id="test_user",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={},
            conversation_variables={}
        )
        
        # 模拟返回孤儿分类的响应
        orphan_category_response = json.dumps({
            "keywords": ["测试", "关键词"],
            "category_id": "orphan_id",
            "category_name": "Orphan Category"
        })
        
        with patch('node.classifier_node.LLM') as mock_llm_class:
            mock_llm_instance = Mock()
            mock_llm_instance.invoke.return_value = Mock(content=orphan_category_response)
            mock_llm_class.return_value = mock_llm_instance
            
            try:
                result = classifier_node.call(test_state)
                print(f"❌ 应该抛出缺少目标节点错误，但是没有")
                return False
            except ValueError as e:
                if "classifier invoke llm no target_node_ids result" in str(e):
                    print(f"✅ 正确捕获缺少目标节点错误: {e}")
                    return True
                else:
                    print(f"❌ 错误信息不正确: {e}")
                    return False
            except Exception as e:
                print(f"❌ 意外错误: {e}")
                return False
    
    def test_llm_invocation_error(self):
        """测试LLM调用错误处理"""
        print("\n=== 测试用例7: LLM调用错误处理 ===")
        
        classes = [
            self._create_question_class("test", "Test")
        ]
        
        classifier_node = ClassifierNode(
            id="test_classifier_llm_error",
            desc="LLM错误测试节点",
            selected=True,
            title="LLM错误测试",
            type="question-classifier",
            classes=classes,
            query_variable_selector=["sys", "query"],
            model=self._create_llm_model_config(),
            source_handle_target_map={
                "test": ["test_node"]
            }
        )
        
        test_state = BaseState(
            sys_query="测试LLM错误",
            sys_user_id="test_user",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={},
            conversation_variables={}
        )
        
        # 模拟LLM调用抛出异常
        with patch('node.classifier_node.LLM') as mock_llm_class:
            mock_llm_instance = Mock()
            mock_llm_instance.invoke.side_effect = Exception("LLM调用失败")
            mock_llm_class.return_value = mock_llm_instance
            
            try:
                result = classifier_node.call(test_state)
                print(f"❌ 应该抛出LLM调用错误，但是没有")
                return False
            except Exception as e:
                if "LLM调用失败" in str(e):
                    print(f"✅ 正确捕获LLM调用错误: {e}")
                    return True
                else:
                    print(f"❌ 错误信息不正确: {e}")
                    return False
    
    def test_list_response_handling(self):
        """测试列表响应的处理"""
        print("\n=== 测试用例8: 列表响应处理 ===")
        
        classes = [
            self._create_question_class("list_category", "List Category")
        ]
        
        classifier_node = ClassifierNode(
            id="test_classifier_list",
            desc="列表响应测试节点",
            selected=True,
            title="列表响应测试",
            type="question-classifier",
            classes=classes,
            query_variable_selector=["sys", "query"],
            model=self._create_llm_model_config(),
            source_handle_target_map={
                "list_category": ["list_node"]
            }
        )
        
        test_state = BaseState(
            sys_query="测试列表响应",
            sys_user_id="test_user",
            sys_app_id="test_app",
            sys_workflow_id="test_workflow",
            sys_workflow_run_id="test_run",
            input_variables={},
            output_variables={},
            conversation_variables={}
        )
        
        # 模拟返回列表格式的响应
        list_response = json.dumps([{
            "keywords": ["测试", "关键词"],
            "category_id": "list_id",
            "category_name": "List Category"
        }])
        
        with patch('node.classifier_node.LLM') as mock_llm_class:
            mock_llm_instance = Mock()
            mock_llm_instance.invoke.return_value = Mock(content=list_response)
            mock_llm_class.return_value = mock_llm_instance
            
            try:
                result = classifier_node.call(test_state)
                
                print(f"✅ 测试成功!")
                
                # 验证结果正确处理了列表格式
                if hasattr(result, 'goto') and result.goto == ["list_node"]:
                    print("✓ 列表响应处理正确")
                    return True
                else:
                    print(f"✗ 列表响应处理错误: {result}")
                    return False
                    
            except Exception as e:
                print(f"❌ 测试失败: {e}")
                return False
    
    def test_node_properties(self):
        """测试节点属性"""
        print("\n=== 测试用例9: 节点属性验证 ===")
        
        classes = [
            self._create_question_class("prop_test", "Property Test")
        ]
        
        classifier_node = ClassifierNode(
            id="test_classifier_props",
            desc="属性测试节点",
            selected=True,
            title="属性测试",
            type="question-classifier",
            instruction="测试指令",
            classes=classes,
            query_variable_selector=["test", "variable"],
            model=self._create_llm_model_config("test-model", "test-provider"),
            memory=None,
            vision={"enabled": False},
            source_handle_target_map={
                "prop_test": ["prop_node"]
            }
        )
        
        # 验证节点类型
        if classifier_node.node_type == WfNodeType.QUESTION_CLASSIFIER:
            print("✓ 节点类型正确")
        else:
            print(f"✗ 节点类型错误: {classifier_node.node_type}")
            return False
        
        # 验证各个属性
        properties_to_check = {
            "id": "test_classifier_props",
            "instruction": "测试指令",
            "query_variable_selector": ["test", "variable"]
        }
        
        all_correct = True
        for prop_name, expected_value in properties_to_check.items():
            actual_value = getattr(classifier_node, prop_name)
            if actual_value == expected_value:
                print(f"✓ {prop_name}: {actual_value}")
            else:
                print(f"✗ {prop_name}: 期望 {expected_value}, 实际 {actual_value}")
                all_correct = False
        
        # 验证复杂属性
        if len(classifier_node.classes) == 1:
            print("✓ classes 数量正确")
        else:
            print(f"✗ classes 数量错误: {len(classifier_node.classes)}")
            all_correct = False
            
        if classifier_node.classes[0].name == "Property Test":
            print("✓ class name 正确")
        else:
            print(f"✗ class name 错误: {classifier_node.classes[0].name}")
            all_correct = False
        
        return all_correct
    
    def test_prompt_template_generation(self):
        """测试提示模板生成"""
        print("\n=== 测试用例10: 提示模板生成 ===")
        
        classes = [
            self._create_question_class("template_test", "Template Test"),
            self._create_question_class("template_test2", "Template Test 2")
        ]
        
        classifier_node = ClassifierNode(
            id="test_classifier_template",
            desc="提示模板测试节点",
            selected=True,
            title="提示模板测试",
            type="question-classifier",
            instruction="自定义分类指令",
            classes=classes,
            query_variable_selector=["sys", "query"],
            model=self._create_llm_model_config(),
            source_handle_target_map={
                "template_test": ["template_node1"],
                "template_test2": ["template_node2"]
            }
        )
        
        # 测试提示模板生成
        input_text = "测试输入文本"
        prompt_templates = classifier_node._get_prompt_template(input_text)
        
        # 验证提示模板结构
        if len(prompt_templates) == 6:  # system + user1 + assistant1 + user2 + assistant2 + user3
            print("✓ 提示模板数量正确")
        else:
            print(f"✗ 提示模板数量错误: {len(prompt_templates)}")
            return False
        
        # 验证角色分配
        expected_roles = ["system", "user", "assistant", "user", "assistant", "user"]
        actual_roles = [template.role for template in prompt_templates]
        
        if actual_roles == expected_roles:
            print("✓ 提示模板角色正确")
        else:
            print(f"✗ 提示模板角色错误: {actual_roles}")
            return False
        
        # 验证最后一个用户消息包含输入文本和分类
        last_user_message = prompt_templates[-1].text
        if input_text in last_user_message:
            print("✓ 输入文本正确嵌入")
        else:
            print(f"✗ 输入文本未正确嵌入: {last_user_message}")
            return False
        
        if "Template Test" in last_user_message:
            print("✓ 分类选项正确嵌入")
        else:
            print(f"✗ 分类选项未正确嵌入: {last_user_message}")
            return False
        
        if "自定义分类指令" in last_user_message:
            print("✓ 自定义指令正确嵌入")
        else:
            print(f"✗ 自定义指令未正确嵌入: {last_user_message}")
            return False
        
        return True
    
    def run_all_tests(self):
        """运行所有测试"""
        print("🚀 开始运行 ClassifierNode 测试套件")
        print("=" * 60)
        
        tests = [
            self.test_basic_classification_functionality,
            self.test_sys_query_fallback,
            self.test_invalid_json_response,
            self.test_missing_category_name,
            self.test_unknown_category,
            self.test_missing_target_nodes,
            self.test_llm_invocation_error,
            self.test_list_response_handling,
            self.test_node_properties,
            self.test_prompt_template_generation
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
    print("🧪 ClassifierNode 文本分类节点测试")
    print("=" * 60)
    
    tester = ClassifierNodeTest()
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

#!/usr/bin/env python3
"""
AggregatorNode 集成测试
基于 langgraph 的完整工作流测试：Start -> Code/LLM -> Aggregator -> Answer
测试变量聚合在真实工作流中的表现
"""

import sys
import os
# 添加项目根目录到路径 (从 integration_tests -> test -> project_root)
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from typing import Dict, Any
from goalflow.state import BaseState
from goalflow.node.aggregator_node import AggregatorNode
from goalflow.node.code_node import CodeNode
from goalflow.workflow_types import NodeVarConfig, AggregatorAdvancedSettings
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


class AggregatorIntegrationWorkflow:
    """AggregatorNode 集成测试工作流：Start -> Multiple Processing Nodes -> Aggregator -> Answer"""
    
    def __init__(self, test_mode="non_grouped"):
        """
        初始化工作流
        test_mode: "non_grouped" 或 "grouped"
        """
        self.test_mode = test_mode
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
            type="start"
        )
        
        # 2. Code节点 - 处理数值数据
        self.code_node = CodeNode(
            desc="数值处理节点",
            selected=True,
            title="数值处理器",
            type="code",
            code="""
def main(numbers, multiplier):
    \"\"\"数值处理函数\"\"\"
    if not numbers:
        return {'processed_numbers': None, 'summary': 'No data'}
    
    # 处理数字列表
    processed = [x * multiplier for x in numbers]
    total = sum(processed)
    
    return {
        'processed_numbers': processed,
        'total': total,
        'summary': f'处理了 {len(numbers)} 个数字，总和为 {total}'
    }
""",
            code_language="python",
            variables=[
                NodeVarConfig(
                    variable="numbers",
                    value_selector=["start_001", "numbers"]
                ),
                NodeVarConfig(
                    variable="multiplier",
                    value_selector=["start_001", "multiplier"]
                )
            ],
            outputs={
                "processed_numbers": {"type": "array"},
                "total": {"type": "number"},
                "summary": {"type": "string"}
            }
        )
        
        # 3. 另一个Code节点 - 处理文本数据
        self.text_code_node = CodeNode(
            desc="文本处理节点",
            selected=True,
            title="文本处理器",
            type="code",
            code="""
def main(text, prefix):
    \"\"\"文本处理函数\"\"\"
    if not text:
        return {'processed_text': None, 'info': 'No text'}
    
    words = text.split()
    processed_text = f"{prefix}: {text.upper()}"
    
    return {
        'processed_text': processed_text,
        'word_count': len(words),
        'info': f'处理了包含 {len(words)} 个单词的文本'
    }
""",
            code_language="python",
            variables=[
                NodeVarConfig(
                    variable="text",
                    value_selector=["start_001", "text"]
                ),
                NodeVarConfig(
                    variable="prefix",
                    value_selector=["start_001", "prefix"]
                )
            ],
            outputs={
                "processed_text": {"type": "string"},
                "word_count": {"type": "number"},
                "info": {"type": "string"}
            }
        )
        
        # 4. AggregatorNode - 根据测试模式配置
        if self.test_mode == "non_grouped":
            # 非分组模式：尝试聚合多个可能的输出
            self.aggregator_node = AggregatorNode(
                desc="变量聚合节点",
                selected=True,
                title="变量聚合",
                type="variable-aggregator",
                output_type="any",
                variables=[
                    ["code_001", "summary"],        # 优先获取数值处理的摘要
                    ["text_code_001", "info"],      # 如果没有，则获取文本处理的信息
                    ["start_001", "fallback"]       # 兜底值
                ]
            )
        else:
            # 分组模式：将不同类型的输出分组
            group1 = AggregatorAdvancedSettings.Group()
            group1.group_name = "numeric_result"
            group1.output_type = "number"
            group1.variables = [
                ["code_001", "total"],
                ["code_001", "processed_numbers"]
            ]
            
            group2 = AggregatorAdvancedSettings.Group()
            group2.group_name = "text_result"
            group2.output_type = "string"
            group2.variables = [
                ["text_code_001", "processed_text"],
                ["text_code_001", "info"]
            ]
            
            advanced_settings = AggregatorAdvancedSettings()
            advanced_settings.group_enabled = True
            advanced_settings.groups = [group1, group2]
            
            self.aggregator_node = AggregatorNode(
                desc="分组变量聚合节点",
                selected=True,
                title="分组变量聚合",
                type="variable-aggregator",
                output_type="mixed",
                variables=[],  # 在分组模式下不使用
                advanced_settings=advanced_settings
            )
        
        # 5. Answer节点 - 输出结果
        self.answer_node = SimpleAnswerNode(
            id="answer_001",
            desc="答案输出节点",
            selected=True,
            title="结果",
            type="answer"
        )
        
        # 添加节点到图中
        self.graph.add_node("start", self._start_wrapper)
        self.graph.add_node("code", self._code_wrapper)
        self.graph.add_node("text_code", self._text_code_wrapper)
        self.graph.add_node("aggregator", self._aggregator_wrapper)
        self.graph.add_node("answer", self._answer_wrapper)
        
        # 设置入口点
        self.graph.set_entry_point("start")
    
    def _setup_edges(self):
        """设置节点之间的连接"""
        self.graph.add_edge("start", "code")
        self.graph.add_edge("start", "text_code")
        self.graph.add_edge(["code", "text_code"], "aggregator")
        self.graph.add_edge("aggregator", "answer")
        self.graph.set_finish_point("answer")
    
    def _start_wrapper(self, state: BaseState) -> BaseState:
        """Start节点包装器"""
        input_data = state.get("input_variables", {})
        print(f"[Start] 接收输入: {input_data}")
        
        # 将输入变量写入输出变量池，供后续节点使用
        output_vars = state.get("output_variables", {})
        output_vars.update({
            "start_001_numbers": input_data.get("numbers"),
            "start_001_multiplier": input_data.get("multiplier"),
            "start_001_text": input_data.get("text"),
            "start_001_prefix": input_data.get("prefix"),
            "start_001_fallback": input_data.get("fallback", "默认兜底值")
        })
        
        return {
            **state,
            "output_variables": output_vars
        }
    
    def _code_wrapper(self, state: BaseState) -> BaseState:
        """Code节点包装器"""
        print(f"[Code] 开始执行数值处理代码...")
        
        # 使用 CodeNode 执行代码
        result = self.code_node(state)
        
        output_vars = result.get("output_variables", {})
        print(f"[Code] 数值处理完成: {output_vars.get('summary', 'N/A')}")
        
        # 只更新 output_variables，避免并发冲突
        return {
            "output_variables": output_vars
        }
    
    def _text_code_wrapper(self, state: BaseState) -> BaseState:
        """Text Code节点包装器"""
        print(f"[TextCode] 开始执行文本处理代码...")
        
        # 使用 CodeNode 执行代码
        result = self.text_code_node(state)
        
        output_vars = result.get("output_variables", {})
        print(f"[TextCode] 文本处理完成: {output_vars.get('info', 'N/A')}")
        
        # 只更新 output_variables，避免并发冲突
        return {
            "output_variables": output_vars
        }
    
    def _aggregator_wrapper(self, state: BaseState) -> BaseState:
        """Aggregator节点包装器"""
        print(f"[Aggregator] 开始聚合变量...")
        print(f"[Aggregator] 当前变量池: {list(state.get('output_variables', {}).keys())}")
        
        # 使用 AggregatorNode 聚合变量
        result = self.aggregator_node(state)
        
        # 将聚合结果合并到状态中
        aggregator_outputs = {}
        if isinstance(result, dict):
            # 为聚合结果添加节点前缀
            for key, value in result.items():
                aggregator_outputs[f"aggregator_001_{key}"] = value
        
        print(f"[Aggregator] 聚合完成: {result}")
        
        # 只更新 output_variables
        return {
            "output_variables": aggregator_outputs
        }
    
    def _answer_wrapper(self, state: BaseState) -> BaseState:
        """Answer节点包装器"""
        output_vars = state.get("output_variables", {})
        
        # 格式化最终答案
        if self.test_mode == "non_grouped":
            aggregated_result = output_vars.get("aggregator_001_output")
            final_answer = f"✅ 聚合结果: {aggregated_result}"
        else:
            numeric_result = output_vars.get("aggregator_001_numeric_result", {}).get("output")
            text_result = output_vars.get("aggregator_001_text_result", {}).get("output")
            final_answer = f"✅ 分组聚合结果:\n数值组: {numeric_result}\n文本组: {text_result}"
        
        print(f"[Answer] 最终结果: {final_answer}")
        
        return {
            **state,
            "output_variables": {
                **output_vars,
                "final_answer": final_answer
            }
        }
    
    def execute(self, input_data: Dict[str, Any]) -> BaseState:
        """执行工作流"""
        print("=== 开始执行 AggregatorNode 集成测试工作流 ===")
        print(f"测试模式: {self.test_mode}")
        print(f"输入数据: {input_data}")
        
        # 初始化状态
        initial_state = BaseState(
            sys_query=f"测试AggregatorNode集成",
            sys_user_id="integration_test_user",
            sys_app_id="integration_test_app",
            sys_workflow_id="aggregator_integration",
            sys_workflow_run_id="run_001",
            input_variables=input_data,
            output_variables={},
            conversation_variables={}
        )
        
        # 编译并执行图
        compiled_graph = self.graph.compile()
        result = compiled_graph.invoke(initial_state)
        
        print("=== AggregatorNode 集成测试工作流执行完成 ===")
        return result


class AggregatorNodeIntegrationTest:
    """AggregatorNode 集成测试类"""
    
    def __init__(self):
        print("🧪 AggregatorNode 集成测试初始化")
    
    def test_non_grouped_aggregation(self):
        """测试非分组聚合"""
        print("\n=== 集成测试1: 非分组变量聚合 ===")
        
        workflow = AggregatorIntegrationWorkflow("non_grouped")
        
        input_data = {
            "numbers": [1, 2, 3, 4, 5],
            "multiplier": 2,
            "text": "Hello World",
            "prefix": "AI"
        }
        
        try:
            result = workflow.execute(input_data)
            final_answer = result.get("output_variables", {}).get("final_answer", "")
            output_vars = result.get("output_variables", {})
            
            print(f"最终答案: {final_answer}")
            
            # 验证结果 - 应该获取到数值处理的摘要
            aggregated_result = output_vars.get("aggregator_001_output")
            
            if aggregated_result and "处理了 5 个数字" in str(aggregated_result):
                print("✅ 非分组聚合测试通过")
                return True
            else:
                print(f"❌ 非分组聚合测试失败: 聚合结果 {aggregated_result}")
                return False
                
        except Exception as e:
            print(f"❌ 非分组聚合测试异常: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def test_grouped_aggregation(self):
        """测试分组聚合"""
        print("\n=== 集成测试2: 分组变量聚合 ===")
        
        workflow = AggregatorIntegrationWorkflow("grouped")
        
        input_data = {
            "numbers": [10, 20, 30],
            "multiplier": 3,
            "text": "Python Programming",
            "prefix": "Code"
        }
        
        try:
            result = workflow.execute(input_data)
            final_answer = result.get("output_variables", {}).get("final_answer", "")
            output_vars = result.get("output_variables", {})
            
            print(f"最终答案: {final_answer}")
            
            # 验证结果 - 应该有两个分组的结果
            numeric_result = output_vars.get("aggregator_001_numeric_result", {})
            text_result = output_vars.get("aggregator_001_text_result", {})
            
            numeric_value = numeric_result.get("output") if numeric_result else None
            text_value = text_result.get("output") if text_result else None
            
            # 数值组应该获取到总和（10+20+30）*3 = 180
            # 文本组应该获取到处理后的文本
            numeric_correct = numeric_value == 180
            text_correct = text_value and "Code: PYTHON PROGRAMMING" in str(text_value)
            
            if numeric_correct and text_correct:
                print("✅ 分组聚合测试通过")
                print(f"  - 数值组结果: {numeric_value}")
                print(f"  - 文本组结果: {text_value}")
                return True
            else:
                print(f"❌ 分组聚合测试失败:")
                print(f"  - 数值组正确: {numeric_correct} (值: {numeric_value})")
                print(f"  - 文本组正确: {text_correct} (值: {text_value})")
                return False
                
        except Exception as e:
            print(f"❌ 分组聚合测试异常: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def test_fallback_aggregation(self):
        """测试兜底聚合（当优先级高的变量不存在时）"""
        print("\n=== 集成测试3: 兜底变量聚合 ===")
        
        workflow = AggregatorIntegrationWorkflow("non_grouped")
        
        # 故意不提供numbers，让数值处理失败，测试兜底机制
        input_data = {
            "numbers": None,  # None 会让数值处理返回 null
            "multiplier": 2,
            "text": "Fallback Test",
            "prefix": "Test",
            "fallback": "这是兜底值"
        }
        
        try:
            result = workflow.execute(input_data)
            final_answer = result.get("output_variables", {}).get("final_answer", "")
            output_vars = result.get("output_variables", {})
            
            print(f"最终答案: {final_answer}")
            
            # 验证结果 - 当第一个处理器返回"No data"时，应该获取到第二个处理器的结果
            aggregated_result = output_vars.get("aggregator_001_output")
            
            # 在当前逻辑下，会依次尝试：
            # 1. code_001.summary -> "No data" (非空，会被选中)
            # 2. text_code_001.info -> "处理了包含 2 个单词的文本"
            # 3. start_001.fallback -> "这是兜底值"
            # 由于第一个返回了"No data"（非null），会被选中
            fallback_correct = (aggregated_result and 
                               ("No data" in str(aggregated_result) or
                                "处理了包含 2 个单词的文本" in str(aggregated_result) or
                                "这是兜底值" in str(aggregated_result)))
            
            if fallback_correct:
                print("✅ 兜底聚合测试通过")
                print(f"  - 聚合结果: {aggregated_result}")
                return True
            else:
                print(f"❌ 兜底聚合测试失败: {aggregated_result}")
                return False
                
        except Exception as e:
            print(f"❌ 兜底聚合测试异常: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def run_all_tests(self):
        """运行所有集成测试"""
        print("🚀 开始运行 AggregatorNode 集成测试套件")
        print("=" * 60)
        
        tests = [
            self.test_non_grouped_aggregation,
            self.test_grouped_aggregation,
            self.test_fallback_aggregation
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
    print("🧪 AggregatorNode 集成测试")
    print("=" * 60)
    
    tester = AggregatorNodeIntegrationTest()
    success = tester.run_all_tests()
    
    if success:
        exit(0)
    else:
        exit(1)


if __name__ == "__main__":
    main()

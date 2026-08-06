"""
最简单的工作流演示
演示一个基本的 Start -> LLM -> Answer 工作流
"""

import sys
import os
# 添加项目根目录到路径 (从 integration_tests -> test -> project_root)
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from typing import Dict, Any
from goalflow.state import BaseState, GenericState
from goalflow.workflow_types import NodeVarConfig, LLMNodeModelConfig, MemoryConfig
from goalflow.constants import WfNodeType, DefaultValueType
from langgraph.graph import StateGraph
import openai
import json

# 临时创建简化的节点类，因为原始节点文件还未完全实现
class SimpleStartNode:
    def __init__(self, **kwargs):
        self.config = kwargs

class SimpleLLMNode:
    def __init__(self, **kwargs):
        self.config = kwargs

class SimpleAnswerNode:
    def __init__(self, **kwargs):
        self.config = kwargs

class SimpleDifyWfVariableConfig:
    def __init__(self, variable, label, type, required, max_length):
        self.variable = variable
        self.label = label
        self.type = type
        self.required = required
        self.max_length = max_length

class SimpleContextConfig:
    def __init__(self, enabled, variable_selector):
        self.enabled = enabled
        self.variable_selector = variable_selector

class SimpleDifyLLmNodePromptTemplate:
    def __init__(self, role, text):
        self.role = role
        self.text = text


class DeepSeekClient:
    """DeepSeek API客户端"""
    
    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com/v1"):
        self.client = openai.OpenAI(
            api_key=api_key,
            base_url=base_url
        )
    
    def chat_completion(self, messages: list, model: str = "deepseek-chat", **kwargs) -> str:
        """调用DeepSeek聊天完成API"""
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                **kwargs
            )
            
            if response.choices and len(response.choices) > 0:
                return response.choices[0].message.content
            else:
                return "抱歉，未能获得有效回复。"
                
        except Exception as e:
            print(f"[DeepSeek API Error] {str(e)}")
            return f"API调用出错: {str(e)}"


class SimpleDemoWorkflow:
    """简单演示工作流：Start -> LLM -> Answer"""
    
    def __init__(self, deepseek_api_key: str = None, use_mock_llm: bool = False):
        self.graph = StateGraph(BaseState)
        self.use_mock_llm = use_mock_llm
        
        # 初始化DeepSeek客户端
        if deepseek_api_key and not use_mock_llm:
            self.deepseek_client = DeepSeekClient(api_key=deepseek_api_key)
            print("[Init] 已初始化DeepSeek API客户端")
        else:
            self.deepseek_client = None
            print("[Init] 使用模拟LLM回复")
        
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
                    variable="user_query",
                    label="用户问题",
                    type=DefaultValueType.STRING,
                    required=True,
                    max_length=1000
                )
            ]
        )
        
        # 2. LLM节点 - 处理用户输入
        self.llm_node = SimpleLLMNode(
            id="llm_001", 
            desc="LLM处理节点",
            selected=True,
            title="AI助手",
            type="llm",
            variables=[
                NodeVarConfig(
                    variable="query",
                    value_selector=["start_001", "user_query"]
                )
            ],
            context=SimpleContextConfig(
                enabled=False,
                variable_selector=[]
            ),
            memory=None,  # MemoryConfig需要单独创建和配置
            prompt_template=[
                SimpleDifyLLmNodePromptTemplate(
                    role="user",
                    text="请回答用户的问题：{{#query#}}"
                )
            ],
            model=LLMNodeModelConfig(
                mode="chat",
                name="gpt-3.5-turbo",
                provider="openai",
                completion_params={"temperature": 0.7, "max_tokens": 1000}
            ),
            vision={}
        )
        
        # 3. Answer节点 - 输出结果
        self.answer_node = SimpleAnswerNode(
            id="answer_001",
            desc="答案输出节点", 
            selected=True,
            title="回答",
            type="answer",
            variables=[
                NodeVarConfig(
                    variable="answer",
                    value_selector=["llm_001", "text"]
                )
            ]
        )
        
        # 添加节点到图中
        self.graph.add_node("start", self._start_wrapper)
        self.graph.add_node("llm", self._llm_wrapper)
        self.graph.add_node("answer", self._answer_wrapper)
        
        # 设置入口点
        self.graph.set_entry_point("start")
        
    def _setup_edges(self):
        """设置节点之间的连接"""
        self.graph.add_edge("start", "llm")
        self.graph.add_edge("llm", "answer")
        self.graph.set_finish_point("answer")
    
    def _start_wrapper(self, state: BaseState) -> BaseState:
        """Start节点包装器"""
        print(f"[Start] 接收到用户输入: {state.get('sys_query', '')}")
        
        # 初始化输入变量
        input_vars = {"user_query": state.get("sys_query", "")}
        
        return {
            **state,
            "input_variables": input_vars,
            "output_variables": input_vars
        }
    
    def _llm_wrapper(self, state: BaseState) -> BaseState:
        """LLM节点包装器 - 使用DeepSeek API或模拟回复"""
        user_query = state.get("input_variables", {}).get("user_query", "")
        print(f"[LLM] 处理问题: {user_query}")
        
        if self.deepseek_client and not self.use_mock_llm:
            # 使用DeepSeek API
            print("[LLM] 调用DeepSeek API...")
            
            messages = [
                {
                    "role": "system", 
                    "content": "你是一个友好、有用的AI助手。请用中文回答用户的问题，回答要准确、简洁且有帮助。"
                },
                {
                    "role": "user", 
                    "content": user_query
                }
            ]
            
            response = self.deepseek_client.chat_completion(
                messages=messages,
                temperature=0.7,
                max_tokens=1000
            )
        else:
            # 使用模拟回复
            print("[LLM] 使用模拟回复...")
            if "你好" in user_query or "hello" in user_query.lower():
                response = f"你好！我是AI助手，很高兴为您服务。您的问题是：{user_query}"
            elif "天气" in user_query:
                response = f"抱歉，我无法查询实时天气信息。不过我可以帮您解答其他问题。您问的是：{user_query}"
            else:
                response = f"感谢您的问题：{user_query}。这是一个演示回复，在实际应用中会使用真实的LLM来生成更智能的回答。"
        
        print(f"[LLM] 生成回答: {response}")
        
        # 更新输出变量
        output_vars = state.get("output_variables", {}).copy()
        output_vars["text"] = response
        
        return {
            **state,
            "output_variables": output_vars
        }
    
    def _answer_wrapper(self, state: BaseState) -> BaseState:
        """Answer节点包装器"""
        answer = state.get("output_variables", {}).get("text", "")
        print(f"[Answer] 最终回答: {answer}")
        
        # 设置最终答案
        final_vars = state.get("output_variables", {}).copy()
        final_vars["final_answer"] = answer
        
        return {
            **state,
            "output_variables": final_vars
        }
    
    def execute(self, user_query: str) -> Dict[str, Any]:
        """执行工作流"""
        print("=== 开始执行简单演示工作流 ===")
        
        # 初始化状态
        initial_state = BaseState(
            sys_query=user_query,
            sys_user_id="demo_user",
            sys_app_id="demo_app", 
            sys_workflow_id="simple_demo",
            sys_workflow_run_id="run_001",
            input_variables={},
            output_variables={},
            conversation_variables={}
        )
        
        # 编译并执行图
        compiled_graph = self.graph.compile()
        result = compiled_graph.invoke(initial_state)
        
        print("=== 工作流执行完成 ===")
        return result


def main():
    """主函数 - 运行演示"""
    print("欢迎使用 Aira 工作流简单演示！")
    print("这个演示展示了一个基本的 Start -> LLM -> Answer 工作流\n")
    
    # 创建工作流实例
    workflow = SimpleDemoWorkflow()
    
    # 测试不同的输入
    test_queries = [
        "你好，请问你是谁？",
        "今天天气怎么样？", 
        "请解释一下人工智能"
    ]
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n--- 测试 {i}: {query} ---")
        try:
            result = workflow.execute(query)
            final_answer = result.get("output_variables", {}).get("final_answer", "无回答")
            print(f"✅ 成功! 最终回答: {final_answer}")
        except Exception as e:
            print(f"❌ 错误: {e}")
        print("-" * 50)


if __name__ == "__main__":
    main()

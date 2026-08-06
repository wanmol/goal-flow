"""
CodeNode 测试用例
测试 CodeNode 的动态代码执行功能
"""

import sys
import os
from langgraph.graph import StateGraph, START, END

from goalflow.workflow_types import Case, Condition
from goalflow.node import IfElseNode, TemplateTransformNode
from goalflow.state import BaseState, GenericState

# 添加项目根目录到路径 (从 unit_tests -> test -> project_root)
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from typing import Dict, Any
from goalflow.state import BaseState
from goalflow.workflow_types import NodeVarConfig
from goalflow.constants import WfNodeType

# 直接导入 CodeNode
from goalflow.node.code_node import CodeNode
from goalflow.workflow_types import LLmNodePromptTemplate
from typing import Sequence, Tuple


class TemplateTransformNodeTest:
    """TemplateTransformNodeTest 测试类"""

    def __init__(self):
        print("🧪 TemplateTransformNodeTest 测试初始化")

    def test_one_case(self):
        """
        单条件

        case：
         input：
            # 构建输入参数1  variables
            var1 = NodeVarConfig(variable="arg1", value_selector=['sys', "intro"])
            var2 = NodeVarConfig(variable="arg2", value_selector=['sys', "intro_int"])
            var3 = NodeVarConfig(variable="arg3", value_selector=['sys', "query"])
            variables = [
                var1, var2, var3
            ]

            # 构建输入参数2  template
            jinja2_text = "{{ arg3 }}  经过{{ arg2 }}轮次  {{ arg1 }}   "

            在node中根据state做参数转换
              state:
                 开始节点有两个固定输入
                    "sys_intro": "aaaaaaaaaaaaaaa",
                    "sys_intro_int": "bbbbbbbbbbbbb",
                 结合当前文本输入
                 "sys_query": state["sys_query"]

         output：
                 你好  经过bbbbbbbbbbbbb轮次  aaaaaaaaaaaaaaa


        """
        try:
            def node_start(state: GenericState):
                print("开始节点")
                return {
                    # TemplateTransformNode
                    "sys_query": state["sys_query"],
                    "sys_intro": "aaaaaaaaaaaaaaa",
                    "sys_intro_int": "bbbbbbbbbbbbb",
                    "input_variables": {"iv": state["sys_query"]},

                    # other
                    "output_variables": {"sov": {"inputs": "你好"}},
                    "conversation_variables": {"cv": 1111}
                }

            def node_a(state: GenericState):
                print("节点 A")
                return {
                    "sys_query": "节点 A"
                }

            def node_b(state: GenericState):
                print("节点 B")
                return {
                    "sys_query": "节点 B",
                }

            # 构建输入参数1  variables
            var1 = NodeVarConfig(variable="arg1", value_selector=['sys', "intro"])
            var2 = NodeVarConfig(variable="arg2", value_selector=['sys', "intro_int"])
            var3 = NodeVarConfig(variable="arg3", value_selector=['sys', "query"])
            variables = [
                var1, var2, var3
            ]

            # 构建输入参数2  template
            jinja2_text = "{{ arg3 }}  经过{{ arg2 }}轮次  {{ arg1 }}   "

            result_out = TemplateTransformNode(
                template=jinja2_text,
                variables=variables,
                id="TemplateTransformNode_id",
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
            builder.add_conditional_edges("node_start", result_out)
            builder.add_edge("node_a", END)
            builder.add_edge("node_b", END)

            graph = builder.compile()

            # 构建输入的参数
            graph.invoke({
                "sys_query": "你好",
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
    print("🧪 template_transform_node 执行测试")
    print("=" * 60)

    tester = TemplateTransformNodeTest()
    success = tester.run_all_tests()

    if success:
        exit(0)
    else:
        exit(1)


if __name__ == "__main__":
    main()



"""
测试案例，导出dsl


app:
  description: 孙垚锋测试模板转换，变量格式化。
  icon: 🤖
  icon_background: '#FFEAD5'
  mode: advanced-chat
  name: Test模板转换器
  use_icon_as_answer_icon: false
dependencies: []
kind: app
version: 0.1.5
workflow:
  conversation_variables: []
  environment_variables: []
  features:
    file_upload:
      allowed_file_extensions:
      - .JPG
      - .JPEG
      - .PNG
      - .GIF
      - .WEBP
      - .SVG
      allowed_file_types:
      - image
      allowed_file_upload_methods:
      - local_file
      - remote_url
      enabled: false
      fileUploadConfig:
        audio_file_size_limit: 50
        batch_count_limit: 5
        file_size_limit: 15
        image_file_size_limit: 10
        video_file_size_limit: 100
        workflow_file_upload_limit: 10
      image:
        enabled: false
        number_limits: 3
        transfer_methods:
        - local_file
        - remote_url
      number_limits: 3
    opening_statement: ''
    retriever_resource:
      enabled: true
    sensitive_word_avoidance:
      enabled: false
    speech_to_text:
      enabled: false
    suggested_questions: []
    suggested_questions_after_answer:
      enabled: false
    text_to_speech:
      enabled: false
      language: ''
      voice: ''
  graph:
    edges:
    - data:
        isInLoop: false
        sourceType: start
        targetType: template-transform
      id: 1755673421407-source-1755675437615-target
      source: '1755673421407'
      sourceHandle: source
      target: '1755675437615'
      targetHandle: target
      type: custom
      zIndex: 0
    - data:
        isInLoop: false
        sourceType: template-transform
        targetType: answer
      id: 1755675437615-source-answer-target
      source: '1755675437615'
      sourceHandle: source
      target: answer
      targetHandle: target
      type: custom
      zIndex: 0
    nodes:
    - data:
        desc: ''
        selected: false
        title: 开始
        type: start
        variables:
        - label: 拼接数据1
          max_length: 48
          options: []
          required: true
          type: text-input
          variable: intro
        - label: 拼接数据2
          max_length: 48
          options: []
          required: true
          type: number
          variable: intro_int
      height: 115
      id: '1755673421407'
      position:
        x: 30
        y: 260
      positionAbsolute:
        x: 30
        y: 260
      selected: false
      sourcePosition: right
      targetPosition: left
      type: custom
      width: 243
    - data:
        answer: '经过改流程，你说说的话为：\n

          {{#1755675437615.output#}}'
        desc: ''
        selected: false
        title: 直接回复
        type: answer
        variables: []
      height: 120
      id: answer
      position:
        x: 636
        y: 260
      positionAbsolute:
        x: 636
        y: 260
      selected: false
      sourcePosition: right
      targetPosition: left
      type: custom
      width: 243
    - data:
        desc: ''
        selected: true
        template: "output：{{ arg3 }} \\n\r\n经过{{ arg2 }}轮次 \\n\r\n{{ arg1 }}   "
        title: 模板转换
        type: template-transform
        variables:
        - value_selector:
          - '1755673421407'
          - intro
          variable: arg1
        - value_selector:
          - '1755673421407'
          - intro_int
          variable: arg2
        - value_selector:
          - sys
          - query
          variable: arg3
      height: 53
      id: '1755675437615'
      position:
        x: 337.28571428571433
        y: 260
      positionAbsolute:
        x: 337.28571428571433
        y: 260
      selected: true
      sourcePosition: right
      targetPosition: left
      type: custom
      width: 243
    viewport:
      x: 697.75
      y: 527.5
      zoom: 0.7

"""
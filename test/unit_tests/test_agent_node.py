import json
import os
import sys

from goalflow.node.agent_node import AgentNode

# 添加项目根目录到路径 (从 unit_tests -> test -> project_root)
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from langgraph.graph import StateGraph, START, END

from goalflow.workflow_types import ToolProviderConfig, ToolProviderType, HttpNodeRetryConfig, MemoryConfig, AgentToolConfig, \
    AgentToolValueConfig, ToolParamSchema, ToolInput, LLMNodeModelConfig, AgentToolParameterConfig
from goalflow.node import ToolNode
from goalflow.state import GenericState

from goalflow.state import BaseState


class AgentNodeTest:
    """  AgentNodeTest 测试类"""

    def __init__(self):
        print("🧪 AgentNodeTest 测试初始化")

    def test_agent_node(self):
        """
        agent_node 节点测试
        """

        def get_current_weather(*, location: str):
            """根据城市名获取当前天气（模拟函数）"""
            weather_data = {
                "北京": {"temperature": 22, "unit": "celsius", "condition": "晴天", "humidity": 40},
                "上海": {"temperature": 25, "unit": "celsius", "condition": "多云", "humidity": 65},
                "深圳": {"temperature": 28, "unit": "celsius", "condition": "小雨", "humidity": 80},
            }

            # 返回模拟数据，若城市不存在则返回未知
            if location in weather_data:
                return json.dumps(weather_data[location], ensure_ascii=False)
            else:
                return json.dumps({"error": "城市不存在"}, ensure_ascii=False)

        try:
            def node_start(state: GenericState):
                print("开始节点")
                return {
                    "sys_query": "北京今天天气怎么样",
                    "sys_files": ["http://www.baidu.com"],
                    "input_variables": {"sys_query": "北京今天天气怎么样"},
                    "output_variables": {"sov": {"inputs": "你好"}},
                    "conversation_variables": {"sys_files": ["http://www.baidu.com"]}
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

            memory = MemoryConfig()
            memory.query_prompt_template = "'{{#sys.query#}}'"
            memory.window = {
                "enabled": "true",
                "size": 50
            }

            tool1 = AgentToolValueConfig()
            tool1.enabled = True
            tool1.extra = {"description": ""}
            file_name_parameter = AgentToolParameterConfig()
            file_name_parameter.auto = 1
            file_name_parameter.value = None
            raw_text_parameter = AgentToolParameterConfig()
            raw_text_parameter.auto = 1
            raw_text_parameter.value = None
            tool1.parameters = [{
                "file_name": file_name_parameter,
                "raw_text": raw_text_parameter,
            }]
            tool1.provider_name = "75220637-a272-4ecc-a637-794a72a380d2"
            tool1.tool_label = "标签体系建设-政府政策"
            tool1.tool_name = "tagServiceGovernPolicy"
            tool1.func = get_current_weather
            tool1.type = "workflow"
            tool1_schema1 = ToolParamSchema(
                auto_generate=None,
                default=None,
                form="llm",
                human_description={
                    "en_US": "",
                    "ja_JP": "",
                    "pt_BR": "",
                    "zh_Hans": "",
                },
                label={
                    "en_US": "政府政策-txt",
                    "ja_JP": "政府政策-txt",
                    "pt_BR": "政府政策-txt",
                    "zh_Hans": "政府政策-txt",
                },
                llm_description="",
                max=None,
                min=None,
                name="raw_text",
                options=[],
                placeholder={
                    "en_US": "",
                    "ja_JP": "",
                    "pt_BR": "",
                    "zh_Hans": "",
                },
                precision=None,
                required=False,
                scope=None,
                template=None,
                type="string",
            )

            #
            tool1_schema2 = ToolParamSchema(
                auto_generate=None,
                default=None,
                form="llm",
                human_description={
                    "en_US": "",
                    "ja_JP": "",
                    "pt_BR": "",
                    "zh_Hans": "",
                },
                label={
                    "en_US": "政府政策-pdf",
                    "ja_JP": "政府政策-pdf",
                    "pt_BR": "政府政策-pdf",
                    "zh_Hans": "政府政策-pdf",
                },
                llm_description="",
                max=None,
                min=None,
                name="file_name",
                options=[],
                placeholder={
                    "en_US": "",
                    "ja_JP": "",
                    "pt_BR": "",
                    "zh_Hans": "",
                },
                precision=None,
                required=False,
                scope=None,
                template=None,
                type="string",
            )

            tool1.schemas = [tool1_schema1, tool1_schema2]
            ############################################################################################################
            tool2 = AgentToolValueConfig()
            tool2.enabled = True
            tool2.extra = {"description": ""}
            file2_name_parameter = AgentToolParameterConfig()
            file2_name_parameter.auto = 1
            file2_name_parameter.value = None
            raw2_text_parameter = AgentToolParameterConfig()
            raw2_text_parameter.auto = 1
            raw2_text_parameter.value = None
            tool2.parameters = [{
                "file_name": file2_name_parameter,
                "raw_text": raw2_text_parameter,
            }]
            tool2.provider_name = "75220637-a272-4ecc-a637-794a72a380d1"
            tool2.tool_label = "获取指定城市的当前天气"
            tool2.tool_name = "get_current_weather"
            tool2.type = "workflow"

            tool2_schema1 = ToolParamSchema(
                auto_generate=None,
                default=None,
                form="llm",
                human_description={
                    "en_US": "",
                    "ja_JP": "",
                    "pt_BR": "",
                    "zh_Hans": "",
                },
                label={
                    "en_US": "城市名称，例如：北京、上海",
                    "ja_JP": "城市名称，例如：北京、上海",
                    "pt_BR": "城市名称，例如：北京、上海",
                    "zh_Hans": "城市名称，例如：北京、上海",
                },
                llm_description="",
                max=None,
                min=None,
                name="location",
                options=[],
                placeholder={
                    "en_US": "",
                    "ja_JP": "",
                    "pt_BR": "",
                    "zh_Hans": "",
                },
                precision=None,
                required=True,
                scope=None,
                template=None,
                type="string",
            )

            tool2.func = get_current_weather

            tool2.schemas = [tool2_schema1]
            ############################################################################################################
            tool3 = AgentToolValueConfig()
            tool3.enabled = True
            tool3.extra = {
                "description": "执行python代码，\n遇到error: operation not permitted时，注意不要import pandas、numpy等package。\n\n注意在代码最后使用print函数输出结果"}

            tool3.parameters = [{
                "code": None,
                "language": None,
            }]
            tool3.provider_name = "code"

            tool3.tool_label = "代码解释器"
            tool3.tool_name = "simple_code"
            tool3.type = "workflow"
            tool3_schema1 = ToolParamSchema(
                auto_generate=None,
                default=None,
                form="llm",
                human_description={
                    "en_US": "",
                    "ja_JP": "",
                    "pt_BR": "",
                    "zh_Hans": "",
                },
                label={
                    "en_US": "城市名称，例如：北京、上海",
                    "ja_JP": "城市名称，例如：北京、上海",
                    "pt_BR": "城市名称，例如：北京、上海",
                    "zh_Hans": "执行python代码，\n遇到error: operation not permitted时，注意不要import pandas、numpy等package。\n\n注意在代码最后使用print函数输出结果",
                },
                llm_description="",
                max=None,
                min=None,
                name="code",
                options=[],
                placeholder={
                    "en_US": "",
                    "ja_JP": "",
                    "pt_BR": "",
                    "zh_Hans": "",
                },
                precision=None,
                required=True,
                scope=None,
                template=None,
                type="string",
            )

            tool3.schemas = [tool3_schema1]
            ############################################################################################################
            tools = AgentToolConfig()
            tools.type = "constant"
            tools.value = [tool1, tool2, tool3]

            instruction = ToolInput(
                type="constant",
                value="你是一个专业的钢铁和有色金属市场分析师，负责帮助用户分析钢联数据API读取到的结果数据，根据用户意图给出分析结果。对于涉及数学计算的问题，请使用代码解释器进行计算，以确保数据准确性。"
            )

            query = ToolInput(
                type="constant",
                value="\"## 输入处理\\n- 当前日期：2025年7月11日\\n- 钢联API数据：## 相关指标0：\n{\"index_info\": {\"index_code\": \"ID01207168\", \"index_name\": \"玉米：港口库存：鲅鱼圈港（周度）\", \"unit_name\": \"万吨\", \"frequency_name\": \"周度\", \"metric_name\": \"港口库存\", \"breed_name\": \"玉米\", \"country_name\": null, \"province_name\": null, \"city_name\": null, \"cp_name\": null, \"description\": \"辽宁鲅鱼圈港（含港内，港外）所有仓库的玉米物理库存\", \"area_name\": null}, \"data\": [{\"data_date\": \"2025-07-11\", \"data_value\": \"96.20\"}, {\"data_date\": \"2025-07-04\", \"data_value\": \"108.00\"}, {\"data_date\": \"2025-06-27\", \"data_value\": \"113.20\"}, {\"data_date\": \"2025-06-20\", \"data_value\": \"112.60\"}, {\"data_date\": \"2025-06-13\", \"data_value\": \"118.10\"}, {\"data_date\": \"2025-06-06\", \"data_value\": \"119.30\"}, {\"data_date\": \"2025-05-30\", \"data_value\": \"137.20\"}, {\"data_date\": \"2025-05-23\", \"data_value\": \"143.70\"}, {\"data_date\": \"2025-05-16\", \"data_value\": \"144.90\"}, {\"data_date\": \"2025-05-09\", \"data_value\": \"158.20\"}, {\"data_date\": \"2025-05-02\", \"data_value\": \"161.20\"}, {\"data_date\": \"2025-04-25\", \"data_value\": \"168.70\"}, {\"data_date\": \"2025-04-18\", \"data_value\": \"172.00\"}]}\n\n## 相关指标1：\n{\"index_info\": {\"index_code\": \"ID01207171\", \"index_name\": \"玉米：港口库存：锦州港（周度）\", \"unit_name\": \"万吨\", \"frequency_name\": \"周度\", \"metric_name\": \"港口库存\", \"breed_name\": \"玉米\", \"country_name\": null, \"province_name\": null, \"city_name\": null, \"cp_name\": null, \"description\": \"辽宁锦州港（含港内，港外）所有仓库的玉米物理库存\", \"area_name\": null}, \"data\": [{\"data_date\": \"2025-07-11\", \"data_value\": \"111.10\"}, {\"data_date\": \"2025-07-04\", \"data_value\": \"119.50\"}, {\"data_date\": \"2025-06-27\", \"data_value\": \"126.90\"}, {\"data_date\": \"2025-06-20\", \"data_value\": \"135.60\"}, {\"data_date\": \"2025-06-13\", \"data_value\": \"141.70\"}, {\"data_date\": \"2025-06-06\", \"data_value\": \"154.50\"}, {\"data_date\": \"2025-05-30\", \"data_value\": \"164.10\"}, {\"data_date\": \"2025-05-23\", \"data_value\": \"177.00\"}, {\"data_date\": \"2025-05-16\", \"data_value\": \"186.50\"}, {\"data_date\": \"2025-05-09\", \"data_value\": \"197.70\"}, {\"data_date\": \"2025-05-02\", \"data_value\": \"209.90\"}, {\"data_date\": \"2025-04-25\", \"data_value\": \"217.40\"}, {\"data_date\": \"2025-04-18\", \"data_value\": \"219.50\"}]}\n\n## 相关指标2：\n{\"index_info\": {\"index_code\": \"ID01207172\", \"index_name\": \"玉米：港口库存：大窑湾港（周度）\", \"unit_name\": \"万吨\", \"frequency_name\": \"周度\", \"metric_name\": \"港口库存\", \"breed_name\": \"玉米\", \"country_name\": null, \"province_name\": null, \"city_name\": null, \"cp_name\": null, \"description\": \"辽宁大窑湾港（含港内，港外）所有仓库的玉米物理库存\", \"area_name\": null}, \"data\": [{\"data_date\": \"2025-07-11\", \"data_value\": \"17.10\"}, {\"data_date\": \"2025-07-04\", \"data_value\": \"23.00\"}, {\"data_date\": \"2025-06-27\", \"data_value\": \"25.00\"}, {\"data_date\": \"2025-06-20\", \"data_value\": \"24.80\"}, {\"data_date\": \"2025-06-13\", \"data_value\": \"23.30\"}, {\"data_date\": \"2025-06-06\", \"data_value\": \"22.30\"}, {\"data_date\": \"2025-05-30\", \"data_value\": \"24.60\"}, {\"data_date\": \"2025-05-23\", \"data_value\": \"32.10\"}, {\"data_date\": \"2025-05-16\", \"data_value\": \"32.70\"}, {\"data_date\": \"2025-05-09\", \"data_value\": \"34.30\"}, {\"data_date\": \"2025-05-02\", \"data_value\": \"30.20\"}, {\"data_date\": \"2025-04-25\", \"data_value\": \"32.00\"}, {\"data_date\": \"2025-04-18\", \"data_value\": \"32.10\"}]}\n\n## 相关指标3：\n{\"index_info\": {\"index_code\": \"ID01207169\", \"index_name\": \"玉米：港口库存：北良港（周度）\", \"unit_name\": \"万吨\", \"frequency_name\": \"周度\", \"metric_name\": \"港口库存\", \"breed_name\": \"玉米\", \"country_name\": null, \"province_name\": null, \"city_name\": null, \"cp_name\": null, \"description\": \"辽宁北良港（含港内，港外）所有仓库的玉米物理库存\", \"area_name\": null}, \"data\": [{\"data_date\": \"2025-07-11\", \"data_value\": \"6.20\"}, {\"data_date\": \"2025-07-04\", \"data_value\": \"9.10\"}, {\"data_date\": \"2025-06-27\", \"data_value\": \"7.30\"}, {\"data_date\": \"2025-06-20\", \"data_value\": \"7.40\"}, {\"data_date\": \"2025-06-13\", \"data_value\": \"6.90\"}, {\"data_date\": \"2025-06-06\", \"data_value\": \"9.80\"}, {\"data_date\": \"2025-05-30\", \"data_value\": \"5.20\"}, {\"data_date\": \"2025-05-23\", \"data_value\": \"9.40\"}, {\"data_date\": \"2025-05-16\", \"data_value\": \"18.00\"}, {\"data_date\": \"2025-05-09\", \"data_value\": \"31.40\"}, {\"data_date\": \"2025-05-02\", \"data_value\": \"24.60\"}, {\"data_date\": \"2025-04-25\", \"data_value\": \"20.40\"}, {\"data_date\": \"2025-04-18\", \"data_value\": \"22.50\"}]}\n\n## 相关指标4：\n{\"index_info\": {\"index_code\": \"ID01531983\", \"index_name\": \"玉米：价差：鲅鱼圈港—哈尔滨市（日度）\", \"unit_name\": \"元/吨\", \"frequency_name\": \"日度\", \"metric_name\": \"价差\", \"breed_name\": \"玉米\", \"country_name\": \"中华人民共和国\", \"province_name\": \"黑龙江省\", \"city_name\": \"哈尔滨市\", \"cp_name\": null, \"description\": \"鲅鱼圈港跟哈尔滨市之间的价格差\", \"area_name\": \"哈尔滨市\"}, \"data\": [{\"data_date\": \"2025-07-11\", \"data_value\": \"160.00\"}, {\"data_date\": \"2025-07-10\", \"data_value\": \"140.00\"}, {\"data_date\": \"2025-07-09\", \"data_value\": \"150.00\"}, {\"data_date\": \"2025-07-08\", \"data_value\": \"160.00\"}, {\"data_date\": \"2025-07-07\", \"data_value\": \"160.00\"}, {\"data_date\": \"2025-07-04\", \"data_value\": \"170.00\"}, {\"data_date\": \"2025-07-03\", \"data_value\": \"170.00\"}, {\"data_date\": \"2025-07-02\", \"data_value\": \"170.00\"}, {\"data_date\": \"2025-07-01\", \"data_value\": \"170.00\"}, {\"data_date\": \"2025-06-30\", \"data_value\": \"170.00\"}, {\"data_date\": \"2025-06-27\", \"data_value\": \"170.00\"}, {\"data_date\": \"2025-06-26\", \"data_value\": \"170.00\"}, {\"data_date\": \"2025-06-25\", \"data_value\": \"170.00\"}, {\"data_date\": \"2025-06-24\", \"data_value\": \"160.00\"}, {\"data_date\": \"2025-06-23\", \"data_value\": \"160.00\"}, {\"data_date\": \"2025-06-20\", \"data_value\": \"160.00\"}, {\"data_date\": \"2025-06-19\", \"data_value\": \"160.00\"}, {\"data_date\": \"2025-06-18\", \"data_value\": \"160.00\"}, {\"data_date\": \"2025-06-17\", \"data_value\": \"160.00\"}, {\"data_date\": \"2025-06-16\", \"data_value\": \"160.00\"}, {\"data_date\": \"2025-06-13\", \"data_value\": \"160.00\"}, {\"data_date\": \"2025-06-12\", \"data_value\": \"150.00\"}, {\"data_date\": \"2025-06-11\", \"data_value\": \"150.00\"}, {\"data_date\": \"2025-06-10\", \"data_value\": \"190.00\"}, {\"data_date\": \"2025-06-09\", \"data_value\": \"160.00\"}, {\"data_date\": \"2025-06-06\", \"data_value\": \"170.00\"}, {\"data_date\": \"2025-06-05\", \"data_value\": \"170.00\"}, {\"data_date\": \"2025-06-04\", \"data_value\": \"170.00\"}, {\"data_date\": \"2025-06-03\", \"data_value\": \"170.00\"}, {\"data_date\": \"2025-05-30\", \"data_value\": \"170.00\"}, {\"data_date\": \"2025-05-29\", \"data_value\": \"170.00\"}, {\"data_date\": \"2025-05-28\", \"data_value\": \"170.00\"}, {\"data_date\": \"2025-05-27\", \"data_value\": \"180.00\"}, {\"data_date\": \"2025-05-26\", \"data_value\": \"180.00\"}, {\"data_date\": \"2025-05-23\", \"data_value\": \"190.00\"}, {\"data_date\": \"2025-05-22\", \"data_value\": \"190.00\"}, {\"data_date\": \"2025-05-21\", \"data_value\": \"190.00\"}, {\"data_date\": \"2025-05-20\", \"data_value\": \"180.00\"}, {\"data_date\": \"2025-05-19\", \"data_value\": \"170.00\"}, {\"data_date\": \"2025-05-16\", \"data_value\": \"170.00\"}, {\"data_date\": \"2025-05-15\", \"data_value\": \"170.00\"}, {\"data_date\": \"2025-05-14\", \"data_value\": \"170.00\"}, {\"data_date\": \"2025-05-13\", \"data_value\": \"160.00\"}, {\"data_date\": \"2025-05-12\", \"data_value\": \"160.00\"}, {\"data_date\": \"2025-05-09\", \"data_value\": \"150.00\"}, {\"data_date\": \"2025-05-08\", \"data_value\": \"150.00\"}, {\"data_date\": \"2025-05-07\", \"data_value\": \"170.00\"}, {\"data_date\": \"2025-05-06\", \"data_value\": \"180.00\"}, {\"data_date\": \"2025-04-30\", \"data_value\": \"190.00\"}, {\"data_date\": \"2025-04-29\", \"data_value\": \"190.00\"}]}\n\n## 相关指标5：\n{\"index_info\": {\"index_code\": \"ID01531985\", \"index_name\": \"玉米：价差：鲅鱼圈港—长春市（日度）\", \"unit_name\": \"元/吨\", \"frequency_name\": \"日度\", \"metric_name\": \"价差\", \"breed_name\": \"玉米\", \"country_name\": \"中华人民共和国\", \"province_name\": \"吉林省\", \"city_name\": \"长春市\", \"cp_name\": null, \"description\": \"鲅鱼圈港跟长春市之间的价格差\", \"area_name\": \"长春市\"}, \"data\": [{\"data_date\": \"2025-07-11\", \"data_value\": \"90.00\"}, {\"data_date\": \"2025-07-10\", \"data_value\": \"90.00\"}, {\"data_date\": \"2025-07-09\", \"data_value\": \"100.00\"}, {\"data_date\": \"2025-07-08\", \"data_value\": \"110.00\"}, {\"data_date\": \"2025-07-07\", \"data_value\": \"100.00\"}, {\"data_date\": \"2025-07-04\", \"data_value\": \"90.00\"}, {\"data_date\": \"2025-07-03\", \"data_value\": \"90.00\"}, {\"data_date\": \"2025-07-02\", \"data_value\": \"90.00\"}, {\"data_date\": \"2025-07-01\", \"data_value\": \"90.00\"}, {\"data_date\": \"2025-06-30\", \"data_value\": \"100.00\"}, {\"data_date\": \"2025-06-27\", \"data_value\": \"100.00\"}, {\"data_date\": \"2025-06-26\", \"data_value\": \"100.00\"}, {\"data_date\": \"2025-06-25\", \"data_value\": \"100.00\"}, {\"data_date\": \"2025-06-24\", \"data_value\": \"90.00\"}, {\"data_date\": \"2025-06-23\", \"data_value\": \"90.00\"}, {\"data_date\": \"2025-06-20\", \"data_value\": \"100.00\"}, {\"data_date\": \"2025-06-19\", \"data_value\": \"100.00\"}, {\"data_date\": \"2025-06-18\", \"data_value\": \"100.00\"}, {\"data_date\": \"2025-06-17\", \"data_value\": \"100.00\"}, {\"data_date\": \"2025-06-16\", \"data_value\": \"100.00\"}, {\"data_date\": \"2025-06-13\", \"data_value\": \"100.00\"}, {\"data_date\": \"2025-06-12\", \"data_value\": \"100.00\"}, {\"data_date\": \"2025-06-11\", \"data_value\": \"100.00\"}, {\"data_date\": \"2025-06-10\", \"data_value\": \"100.00\"}, {\"data_date\": \"2025-06-09\", \"data_value\": \"80.00\"}, {\"data_date\": \"2025-06-06\", \"data_value\": \"80.00\"}, {\"data_date\": \"2025-06-05\", \"data_value\": \"80.00\"}, {\"data_date\": \"2025-06-04\", \"data_value\": \"80.00\"}, {\"data_date\": \"2025-06-03\", \"data_value\": \"80.00\"}, {\"data_date\": \"2025-05-30\", \"data_value\": \"80.00\"}, {\"data_date\": \"2025-05-29\", \"data_value\": \"90.00\"}, {\"data_date\": \"2025-05-28\", \"data_value\": \"90.00\"}, {\"data_date\": \"2025-05-27\", \"data_value\": \"90.00\"}, {\"data_date\": \"2025-05-26\", \"data_value\": \"90.00\"}, {\"data_date\": \"2025-05-23\", \"data_value\": \"100.00\"}, {\"data_date\": \"2025-05-22\", \"data_value\": \"100.00\"}, {\"data_date\": \"2025-05-21\", \"data_value\": \"100.00\"}, {\"data_date\": \"2025-05-20\", \"data_value\": \"90.00\"}, {\"data_date\": \"2025-05-19\", \"data_value\": \"90.00\"}, {\"data_date\": \"2025-05-16\", \"data_value\": \"90.00\"}, {\"data_date\": \"2025-05-15\", \"data_value\": \"90.00\"}, {\"data_date\": \"2025-05-14\", \"data_value\": \"90.00\"}, {\"data_date\": \"2025-05-13\", \"data_value\": \"80.00\"}, {\"data_date\": \"2025-05-12\", \"data_value\": \"80.00\"}, {\"data_date\": \"2025-05-09\", \"data_value\": \"90.00\"}, {\"data_date\": \"2025-05-08\", \"data_value\": \"90.00\"}, {\"data_date\": \"2025-05-07\", \"data_value\": \"90.00\"}, {\"data_date\": \"2025-05-06\", \"data_value\": \"90.00\"}, {\"data_date\": \"2025-04-30\", \"data_value\": \"120.00\"}, {\"data_date\": \"2025-04-29\", \"data_value\": \"120.00\"}]}\n\n## 相关指标6：\n{\"index_info\": {\"index_code\": \"ID01531988\", \"index_name\": \"玉米：价差：鲅鱼圈港—沈阳市（日度）\", \"unit_name\": \"元/吨\", \"frequency_name\": \"日度\", \"metric_name\": \"价差\", \"breed_name\": \"玉米\", \"country_name\": \"中华人民共和国\", \"province_name\": \"辽宁省\", \"city_name\": \"沈阳市\", \"cp_name\": null, \"description\": \"鲅鱼圈港跟沈阳市之间的价格差\", \"area_name\": \"沈阳市\"}, \"data\": [{\"data_date\": \"2025-07-11\", \"data_value\": \"50.00\"}, {\"data_date\": \"2025-07-10\", \"data_value\": \"40.00\"}, {\"data_date\": \"2025-07-09\", \"data_value\": \"40.00\"}, {\"data_date\": \"2025-07-08\", \"data_value\": \"50.00\"}, {\"data_date\": \"2025-07-07\", \"data_value\": \"40.00\"}, {\"data_date\": \"2025-07-04\", \"data_value\": \"40.00\"}, {\"data_date\": \"2025-07-03\", \"data_value\": \"40.00\"}, {\"data_date\": \"2025-07-02\", \"data_value\": \"40.00\"}, {\"data_date\": \"2025-07-01\", \"data_value\": \"40.00\"}, {\"data_date\": \"2025-06-30\", \"data_value\": \"40.00\"}, {\"data_date\": \"2025-06-27\", \"data_value\": \"50.00\"}, {\"data_date\": \"2025-06-26\", \"data_value\": \"50.00\"}, {\"data_date\": \"2025-06-25\", \"data_value\": \"50.00\"}, {\"data_date\": \"2025-06-24\", \"data_value\": \"40.00\"}, {\"data_date\": \"2025-06-23\", \"data_value\": \"60.00\"}, {\"data_date\": \"2025-06-20\", \"data_value\": \"50.00\"}, {\"data_date\": \"2025-06-19\", \"data_value\": \"50.00\"}, {\"data_date\": \"2025-06-18\", \"data_value\": \"50.00\"}, {\"data_date\": \"2025-06-17\", \"data_value\": \"50.00\"}, {\"data_date\": \"2025-06-16\", \"data_value\": \"50.00\"}, {\"data_date\": \"2025-06-13\", \"data_value\": \"50.00\"}, {\"data_date\": \"2025-06-12\", \"data_value\": \"40.00\"}, {\"data_date\": \"2025-06-11\", \"data_value\": \"40.00\"}, {\"data_date\": \"2025-06-10\", \"data_value\": \"60.00\"}, {\"data_date\": \"2025-06-09\", \"data_value\": \"30.00\"}, {\"data_date\": \"2025-06-06\", \"data_value\": \"50.00\"}, {\"data_date\": \"2025-06-05\", \"data_value\": \"50.00\"}, {\"data_date\": \"2025-06-04\", \"data_value\": \"50.00\"}, {\"data_date\": \"2025-06-03\", \"data_value\": \"50.00\"}, {\"data_date\": \"2025-05-30\", \"data_value\": \"50.00\"}, {\"data_date\": \"2025-05-29\", \"data_value\": \"50.00\"}, {\"data_date\": \"2025-05-28\", \"data_value\": \"60.00\"}, {\"data_date\": \"2025-05-27\", \"data_value\": \"60.00\"}, {\"data_date\": \"2025-05-26\", \"data_value\": \"60.00\"}, {\"data_date\": \"2025-05-23\", \"data_value\": \"70.00\"}, {\"data_date\": \"2025-05-22\", \"data_value\": \"70.00\"}, {\"data_date\": \"2025-05-21\", \"data_value\": \"40.00\"}, {\"data_date\": \"2025-05-20\", \"data_value\": \"30.00\"}, {\"data_date\": \"2025-05-19\", \"data_value\": \"30.00\"}, {\"data_date\": \"2025-05-16\", \"data_value\": \"30.00\"}, {\"data_date\": \"2025-05-15\", \"data_value\": \"30.00\"}, {\"data_date\": \"2025-05-14\", \"data_value\": \"30.00\"}, {\"data_date\": \"2025-05-13\", \"data_value\": \"20.00\"}, {\"data_date\": \"2025-05-12\", \"data_value\": \"20.00\"}, {\"data_date\": \"2025-05-09\", \"data_value\": \"10.00\"}, {\"data_date\": \"2025-05-08\", \"data_value\": \"10.00\"}, {\"data_date\": \"2025-05-07\", \"data_value\": \"40.00\"}, {\"data_date\": \"2025-05-06\", \"data_value\": \"40.00\"}, {\"data_date\": \"2025-04-30\", \"data_value\": \"60.00\"}, {\"data_date\": \"2025-04-29\", \"data_value\": \"60.00\"}]}\n\n## 相关指标7：\n{\"index_info\": {\"index_code\": \"ID00262725\", \"index_name\": \"玉米：外贸货物：库存：广东港口（周度）\", \"unit_name\": \"万吨\", \"frequency_name\": \"周度\", \"metric_name\": \"库存\", \"breed_name\": \"玉米\", \"country_name\": null, \"province_name\": null, \"city_name\": null, \"cp_name\": null, \"description\": \"广东六个港口（蛇口港、新沙港、南沙港、新港、麻涌港、省粮码头）\", \"area_name\": null}, \"data\": [{\"data_date\": \"2025-07-11\", \"data_value\": \"1.10\"}, {\"data_date\": \"2025-07-04\", \"data_value\": \"1.30\"}, {\"data_date\": \"2025-06-27\", \"data_value\": \"0.30\"}, {\"data_date\": \"2025-06-20\", \"data_value\": \"0.30\"}, {\"data_date\": \"2025-06-13\", \"data_value\": \"0.30\"}, {\"data_date\": \"2025-06-06\", \"data_value\": \"0.30\"}, {\"data_date\": \"2025-05-30\", \"data_value\": \"0.30\"}, {\"data_date\": \"2025-05-23\", \"data_value\": \"0.50\"}, {\"data_date\": \"2025-05-16\", \"data_value\": \"0.70\"}, {\"data_date\": \"2025-05-09\", \"data_value\": \"1.40\"}, {\"data_date\": \"2025-05-02\", \"data_value\": \"3.50\"}, {\"data_date\": \"2025-04-25\", \"data_value\": \"6.00\"}, {\"data_date\": \"2025-04-18\", \"data_value\": \"10.30\"}]}\n\n## 相关指标8：\n{\"index_info\": {\"index_code\": \"ID01374523\", \"index_name\": \"石油焦：港口库存：鲅鱼圈港（周度）\", \"unit_name\": \"万吨\", \"frequency_name\": \"周度\", \"metric_name\": \"港口库存\", \"breed_name\": \"石油焦\", \"country_name\": null, \"province_name\": null, \"city_name\": null, \"cp_name\": null, \"description\": \"1、区域：鲅鱼圈港\\n2、周期：当周四\\n3、取值方式：点数据\\n4、采样方式：固定取样\\n5、样本覆盖率：100%\\n6、港口库存量：位于港口的仓库或储罐物理库存量，其中仓库存或储罐含保税与非保税。\", \"area_name\": null}, \"data\": [{\"data_date\": \"2025-07-11\", \"data_value\": \"2.00\"}, {\"data_date\": \"2025-07-04\", \"data_value\": \"2.00\"}, {\"data_date\": \"2025-06-27\", \"data_value\": \"2.00\"}, {\"data_date\": \"2025-06-20\", \"data_value\": \"2.00\"}, {\"data_date\": \"2025-06-13\", \"data_value\": \"1.50\"}, {\"data_date\": \"2025-06-06\", \"data_value\": \"1.50\"}, {\"data_date\": \"2025-05-30\", \"data_value\": \"1.50\"}, {\"data_date\": \"2025-05-23\", \"data_value\": \"1.50\"}, {\"data_date\": \"2025-05-16\", \"data_value\": \"1.50\"}, {\"data_date\": \"2025-05-09\", \"data_value\": \"1.50\"}, {\"data_date\": \"2025-05-02\", \"data_value\": \"1.50\"}, {\"data_date\": \"2025-04-25\", \"data_value\": \"1.50\"}, {\"data_date\": \"2025-04-18\", \"data_value\": \"1.50\"}]}\n\n## 相关指标9：\n{\"index_info\": {\"index_code\": \"ID00299242\", \"index_name\": \"镍矿：库存：锦州港（周度）\", \"unit_name\": \"万湿吨\", \"frequency_name\": \"周度\", \"metric_name\": \"库存\", \"breed_name\": \"镍矿\", \"country_name\": null, \"province_name\": null, \"city_name\": null, \"cp_name\": null, \"description\": \"2022年3月3日起，统计周期为上周五至本周四，企业私库未包含在统计范围内。\", \"area_name\": null}, \"data\": [{\"data_date\": \"2025-07-11\", \"data_value\": \"17.00\"}, {\"data_date\": \"2025-07-04\", \"data_value\": \"17.00\"}, {\"data_date\": \"2025-06-27\", \"data_value\": \"18.00\"}, {\"data_date\": \"2025-06-20\", \"data_value\": \"19.00\"}, {\"data_date\": \"2025-06-13\", \"data_value\": \"20.00\"}, {\"data_date\": \"2025-06-06\", \"data_value\": \"20.00\"}, {\"data_date\": \"2025-05-30\", \"data_value\": \"21.00\"}, {\"data_date\": \"2025-05-23\", \"data_value\": \"22.00\"}, {\"data_date\": \"2025-05-16\", \"data_value\": \"12.00\"}, {\"data_date\": \"2025-05-09\", \"data_value\": \"12.00\"}, {\"data_date\": \"2025-05-02\", \"data_value\": \"13.00\"}, {\"data_date\": \"2025-04-25\", \"data_value\": \"14.00\"}, {\"data_date\": \"2025-04-18\", \"data_value\": \"8.00\"}]}\\n- 用户输入： 锦州港口和鲅鱼圈港口的玉米库存哪个更多？相差多少\\n\\n## 输出规则\\n1. 如API返回有效数据，根据用户query判断用户意图，执行相应分析并提供专业回答\\n2. 如果API返回的数据无法回答用户输入的问题，返回【无法回答】，不要输出其他信息\\n\\n## 应答质量标准\\n- **数据精度**：数值保留合适小数位数，确保准确性\\n- **时效标注**：明确标示数据时间范围和最新更新时间\\n- **专业深度**：结合原始数据提供有深度的市场分析和专业解读\\n- **趋势描述**：清晰描述数据趋势变化\\n- **术语规范**：使用行业标准术语，必要时提供简要解释\""

            )

            maximum_iterations = ToolInput(
                type="constant",
                value=13
            )

            model = LLMNodeModelConfig(
                mode="chat",
                name="gpt-4o",  # "qwen2.5-14b-instruct",
                provider="langgenius/azure_openai/azure_openai",
                completion_params={}
            )
            agent = AgentNode(
                id="agent_node",
                desc="",
                selected="true",
                title="agent",
                type="agent",
                memory=memory,
                tools=tools,
                instruction=instruction,
                query=query,
                maximum_iterations=maximum_iterations,
                model=model,
            )

            builder = StateGraph(BaseState)

            builder.add_node("node_a", node_a)
            builder.add_node("node_b", node_b)
            builder.add_node("node_start", node_start)
            builder.add_node("agent", agent)

            builder.add_edge(START, "node_start")
            builder.add_edge("node_start", "agent")
            builder.add_edge("node_a", END)
            builder.add_edge("node_b", END)

            graph = builder.compile()

            graph.invoke({
                "sys.query": "北京天气怎么样",
            })
            return True
        except Exception as e:
            # raise e
            print(f"❌ 测试执行异常: {e}")
            return False

    def run_all_tests(self):
        """运行所有测试"""
        print("🚀 开始运行 CodeNode 测试套件")
        print("=" * 60)

        tests = [
            self.test_agent_node,
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
    print("🧪 LLM Node 执行测试")
    print("=" * 60)

    tester = AgentNodeTest()
    success = tester.run_all_tests()

    if success:
        exit(0)
    else:
        exit(1)


if __name__ == "__main__":
    main()

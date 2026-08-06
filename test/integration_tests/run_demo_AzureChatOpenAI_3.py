import os
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
import json


def test_json_schema_with_langchain_my():
    """使用 LangChain 的 AzureChatOpenAI 测试 json_schema"""

    # 初始化 AzureChatOpenAI 客户端
    llm = AzureChatOpenAI(
        azure_endpoint="https://sub3-openai-japan.openai.azure.com/",
        api_version="2025-03-01-preview",
        azure_deployment="gpt-4o-mini",  # 替换为实际部署名
        api_key=os.environ.get("AZURE_OPENAI_API_KEY", ""),  # 从环境变量读取
        temperature=0.1
    )

    try:
        print("🔍 测试 LangChain AzureChatOpenAI + json_schema...")

        # 定义消息
        messages = [
            SystemMessage(content="You are a helpful assistant that returns structured data."),
            HumanMessage(content="What's the weather like in Boston today?")
        ]

        # 使用 invoke 调用，并传递 response_format
        response = llm.invoke(
            messages,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "query_rewrite_output_v4",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "needs_split": {
                                "type": "boolean",
                                "description": "是否需要拆分为多个原子Query"
                            },
                            "atomic_queries": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "intent": {
                                            "type": "string",
                                            "description": "单一意图描述"
                                        },
                                        "primary_query": {
                                            "type": "string",
                                            "description": "主Query（推荐用于Tavily检索）",
                                            "minLength": 5,
                                            "maxLength": 100
                                        },
                                        "variant_queries": {
                                            "type": "array",
                                            "items": {
                                                "type": "string"
                                            },
                                            "description": "2个变体Query（词汇差异≥30%）",
                                            "minItems": 2,
                                            "maxItems": 2
                                        },
                                        "entity_anchors": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "type": {
                                                        "type": "string",
                                                        "enum": ["唯一标识符", "政策名称", "时间", "地域", "主体对象", "政策类型"]
                                                    },
                                                    "value": {
                                                        "type": "string"
                                                    },
                                                    "weight": {
                                                        "type": "number",
                                                        "minimum": 1.0,
                                                        "maximum": 5.0
                                                    }
                                                },
                                                "required": ["type", "value", "weight"],
                                                "additionalProperties": False
                                            },
                                            "description": "强实体锚点（按权重排序）"
                                        },
                                        "token_count": {
                                            "type": "integer",
                                            "description": "估算token数量（目标5-15）",
                                            "minimum": 3,
                                            "maximum": 20
                                        },
                                        "noise_removed": {
                                            "type": "array",
                                            "items": {
                                                "type": "string"
                                            },
                                            "description": "删除的噪音词列表"
                                        },
                                        "site_strategy": {
                                            "type": "array",
                                            "items": {
                                                "type": "string",
                                                "enum": [
                                                    "添加site:gov.cn",
                                                    "添加site:edu.cn",
                                                    "添加site:org.cn",
                                                    "添加site:court.gov.cn",
                                                    "添加site:chinatax.gov.cn",
                                                    "添加site:12333.gov.cn",
                                                    "添加site:xinhuanet.com",
                                                    "添加site:bendibao.com",
                                                    "添加site:cn.bing.com",
                                                    "添加site:baidu.com",
                                                    "不添加site限定"
                                                ]
                                            },
                                            "description": "site限定符策略数组（支持多个网站同时检索）：gov.cn(政府官网)/edu.cn(教育)/org.cn(组织)/court.gov.cn(法院)/chinatax.gov.cn(税务)/12333.gov.cn(人社)/xinhuanet.com(新华网)/bendibao.com(本地宝)/cn.bing.com(必应)/baidu.com(百度)/不限定",
                                            "minItems": 1,
                                            "maxItems": 3
                                        }
                                    },
                                    "required": ["intent", "primary_query", "variant_queries", "entity_anchors", "token_count", "noise_removed", "site_strategy"],
                                    "additionalProperties": False
                                },
                                "description": "拆分后的原子Query列表",
                                "minItems": 1,
                                "maxItems": 3
                            },
                            "original_query": {
                                "type": "string",
                                "description": "用户原始Query"
                            },
                            "errors_corrected": {
                                "type": "array",
                                "items": {
                                    "type": "string"
                                },
                                "description": "纠正的错误（格式：错误→正确）"
                            },
                            "reasoning": {
                                "type": "string",
                                "description": "改写思考过程（1-2句话）"
                            },
                            "quality_score": {
                                "type": "number",
                                "description": "质量评分（0.0-1.0）",
                                "minimum": 0,
                                "maximum": 1
                            }
                        },
                        "required": ["needs_split", "atomic_queries", "original_query", "errors_corrected", "reasoning", "quality_score"],
                        "additionalProperties": False
                    }
                }
            }
        )

        print("✅ LangChain json_schema 测试成功！")
        print(f"Response: {response.content}")

        # 尝试解析 JSON 响应
        try:
            parsed_result = json.loads(response.content)
            print(f"✅ 解析结果: {parsed_result}")
        except json.JSONDecodeError:
            print("❌ 无法解析 JSON 响应")

        return True

    except Exception as e:
        print(f"❌ LangChain 测试失败: {e}")
        return False

def test_json_schema_with_langchain():
    """使用 LangChain 的 AzureChatOpenAI 测试 json_schema"""

    # 初始化 AzureChatOpenAI 客户端
    llm = AzureChatOpenAI(
        azure_endpoint="https://sub3-openai-japan.openai.azure.com/",
        api_version="2025-03-01-preview",
        azure_deployment="gpt-4o-mini",  # 替换为实际部署名
        api_key=os.environ.get("AZURE_OPENAI_API_KEY", ""),  # 从环境变量读取
        temperature=0.1
    )

    try:
        print("🔍 测试 LangChain AzureChatOpenAI + json_schema...")

        # 定义消息
        messages = [
            SystemMessage(content="You are a helpful assistant that returns structured data."),
            HumanMessage(content="What's the weather like in Boston today?")
        ]

        # 使用 invoke 调用，并传递 response_format
        response = llm.invoke(
            messages,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "get_weather",
                    "strict": True,
                    "schema": {
                        "type": "object",  # ✅ 必须有 type: "object"
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "The city and state"
                            },
                            "temperature": {
                                "type": "number",
                                "description": "Temperature in Celsius"
                            },
                            "condition": {
                                "type": "string",
                                "description": "Weather condition",
                                "enum": ["sunny", "cloudy", "rainy", "snowy", "windy"]
                            }
                        },
                        "required": ["location", "temperature", "condition"],
                        "additionalProperties": False
                    }
                }
            }
        )

        print("✅ LangChain json_schema 测试成功！")
        print(f"Response: {response.content}")

        # 尝试解析 JSON 响应
        try:
            parsed_result = json.loads(response.content)
            print(f"✅ 解析结果: {parsed_result}")
        except json.JSONDecodeError:
            print("❌ 无法解析 JSON 响应")

        return True

    except Exception as e:
        print(f"❌ LangChain 测试失败: {e}")
        return False

def test_simple_json_schema_langchain():
    """测试简单 json_schema 格式"""

    llm = AzureChatOpenAI(
        azure_endpoint="https://sub3-openai-japan.openai.azure.com/",
        api_version="2025-03-01-preview",
        azure_deployment="gpt-4o-mini",  # 替换为实际部署名
        api_key=os.environ.get("AZURE_OPENAI_API_KEY", ""),  # 从环境变量读取
        temperature=0.1
    )

    try:
        print("\n🔍 测试 LangChain 简单 json_schema 格式...")

        messages = [
            HumanMessage(content="Return a simple user profile with name and age")
        ]

        response = llm.invoke(
            messages,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "simple_user_profile",
                    "schema": {
                        "type": "object",  # ✅ 必须有 type: "object"
                        "properties": {
                            "name": {"type": "string"},
                            "age": {"type": "integer"}
                        },
                        "required": ["name", "age"]
                    }
                }
            }
        )

        print("✅ 简单 LangChain json_schema 测试成功！")
        print(f"Response: {response.content}")

        # 解析 JSON
        try:
            result = json.loads(response.content)
            print(f"✅ 解析结果: {result}")
        except:
            print("❌ 无法解析 JSON")

        return True

    except Exception as e:
        print(f"❌ 简单 LangChain 测试失败: {e}")
        return False

'''
def test_streaming_with_json_schema():
    """测试流式输出 + json_schema（如果支持）"""

    llm = AzureChatOpenAI(
        azure_endpoint="https://sub3-openai-japan.openai.azure.com/",
        api_version="2025-03-01-preview",
        azure_deployment="your-deployment-name",  # 替换为实际部署名
        api_key="your-api-key",  # 替换为实际 API Key
        temperature=0.1
    )

    try:
        print("\n🔍 测试流式输出 + json_schema...")

        messages = [
            HumanMessage(content="Return a simple greeting in JSON format")
        ]

        # 测试流式调用
        full_response = ""
        for chunk in llm.stream(
                messages,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "greeting",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "message": {"type": "string"},
                                "type": {"type": "string", "enum": ["greeting", "farewell"]}
                            },
                            "required": ["message", "type"]
                        }
                    }
                }
        ):
            full_response += chunk.content
            print(f"Chunk: {chunk.content}", end="")

        print(f"\n✅ 流式输出完成: {full_response}")

        # 尝试解析
        try:
            result = json.loads(full_response)
            print(f"✅ 解析结果: {result}")
        except:
            print("❌ 无法解析流式输出 JSON")

        return True

    except Exception as e:
        print(f"❌ 流式输出测试失败: {e}")
        return False
'''
# 主函数
if __name__ == "__main__":
    print("🧪 开始测试 LangChain AzureChatOpenAI json_schema 支持...")

    # 请先替换下面的占位符
    print("⚠️  注意：请先替换代码中的 'your-deployment-name' 和 'your-api-key'")
    print("   - deployment_name: 你的 Azure OpenAI 部署名称")
    print("   - api_key: 你的 Azure OpenAI API Key\n")

    # 执行测试
    success0 = test_json_schema_with_langchain_my()
    success1 = test_json_schema_with_langchain()
    success2 = test_simple_json_schema_langchain()
    #success4 = test_streaming_with_json_schema()  # 可选测试

    print(f"\n📋 测试总结:")
    print(f"- json_schema 格式: {'✅ 成功' if success0 else '❌ 失败'}")
    print(f"- json_schema 格式: {'✅ 成功' if success1 else '❌ 失败'}")
    print(f"- 简单 json_schema: {'✅ 成功' if success2 else '❌ 失败'}")
    #print(f"- 流式 + json_schema: {'✅ 成功' if success4 else '❌ 失败'}")
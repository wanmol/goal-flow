import os
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
import json

def test_json_schema_with_bind():
    """使用 model.bind() 方式测试 json_schema"""

    try:
        print("🔍 测试 AzureChatOpenAI + bind() + json_schema...")

        # 基础模型配置
        base_model = AzureChatOpenAI(
            api_key=os.environ.get("AZURE_OPENAI_API_KEY", ""),  # 从环境变量读取
            azure_endpoint="https://sub3-openai-japan.openai.azure.com/",
            api_version="2025-03-01-preview",
            model="gpt-4o-mini",  # 替换为实际模型名，如 "gpt-4o"
            temperature=0.1,
            max_tokens=1000,
            streaming=False,
            model_kwargs={}  # 其他参数（如果有的话）
        )

        # 定义 JSON Schema
        response_format_1123 = {
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

        # 使用 bind() 绑定 response_format
        bound_model = base_model.bind(
            response_format={
                "type": "json_schema",
                "json_schema": response_format_1123
            }
        )

        # 定义消息
        messages = [
            SystemMessage(content="You are a helpful assistant that returns structured data."),
            HumanMessage(content="What's the weather like in Boston today?")
        ]

        # 调用绑定后的模型
        response = bound_model.invoke(messages)

        print("✅ bind() + json_schema 测试成功！")
        print(f"Response: {response.content}")

        # 尝试解析 JSON 响应
        try:
            parsed_result = json.loads(response.content)
            print(f"✅ 解析结果: {parsed_result}")
        except json.JSONDecodeError:
            print("❌ 无法解析 JSON 响应")

        return True

    except Exception as e:
        print(f"❌ bind() 测试失败: {e}")
        return False

def test_simple_json_schema_with_bind():
    """测试简单 json_schema 格式 + bind()"""

    try:
        print("\n🔍 测试 bind() + 简单 json_schema 格式...")

        base_model = AzureChatOpenAI(
            api_key=os.environ.get("AZURE_OPENAI_API_KEY", ""),  # 从环境变量读取
            azure_endpoint="https://sub3-openai-japan.openai.azure.com/",
            api_version="2025-03-01-preview",
            model="gpt-4o-mini",  # 替换为实际模型名
            temperature=0.1,
            max_tokens=500,
            streaming=False,
            model_kwargs={}
        )

        # 简单的 JSON Schema
        simple_response_format = {
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

        # 绑定 response_format
        bound_model = base_model.bind(
            response_format={
                "type": "json_schema",
                "json_schema": simple_response_format
            }
        )

        messages = [
            HumanMessage(content="Return a simple user profile with name and age")
        ]

        response = bound_model.invoke(messages)

        print("✅ 简单 bind() + json_schema 测试成功！")
        print(f"Response: {response.content}")

        # 解析 JSON
        try:
            result = json.loads(response.content)
            print(f"✅ 解析结果: {result}")
        except:
            print("❌ 无法解析 JSON")

        return True

    except Exception as e:
        print(f"❌ 简单 bind() 测试失败: {e}")
        return False
'''
def test_streaming_with_bind():
    """测试流式输出 + bind() + json_schema"""

    try:
        print("\n🔍 测试流式输出 + bind() + json_schema...")

        base_model = AzureChatOpenAI(
            api_key="your-api-key",  # 替换为实际 API Key
            azure_endpoint="https://sub3-openai-japan.openai.azure.com/",
            api_version="2025-03-01-preview",
            model="your-model-name",  # 替换为实际模型名
            temperature=0.1,
            max_tokens=500,
            streaming=True,  # 启用流式
            model_kwargs={}
        )

        stream_response_format = {
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

        # 绑定 response_format 到流式模型
        bound_stream_model = base_model.bind(
            response_format={
                "type": "json_schema",
                "json_schema": stream_response_format
            }
        )

        messages = [
            HumanMessage(content="Return a simple greeting in JSON format")
        ]

        # 流式调用
        full_response = ""
        for chunk in bound_stream_model.stream(messages):
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
        print(f"❌ 流式 bind() 测试失败: {e}")
        return False
'''

'''
def test_multiple_binds():
    """测试同一个基础模型多次 bind() 不同的 response_format"""

    try:
        print("\n🔍 测试同一个模型多次 bind() 不同格式...")

        base_model = AzureChatOpenAI(
            api_key="your-api-key",  # 替换为实际 API Key
            azure_endpoint="https://sub3-openai-japan.openai.azure.com/",
            api_version="2025-03-01-preview",
            model="your-model-name",  # 替换为实际模型名
            temperature=0.1,
            max_tokens=500,
            streaming=False,
            model_kwargs={}
        )

        # Bind 1: Weather schema
        weather_schema = {
            "name": "weather_info",
            "schema": {
                "type": "object",
                "properties": {
                    "location": {"type": "string"},
                    "temp_c": {"type": "number"}
                },
                "required": ["location", "temp_c"]
            }
        }
        weather_model = base_model.bind(
            response_format={"type": "json_schema", "json_schema": weather_schema}
        )

        # Bind 2: User schema  
        user_schema = {
            "name": "user_info",
            "schema": {
                "type": "object",
                "properties": {
                    "username": {"type": "string"},
                    "email": {"type": "string"}
                },
                "required": ["username", "email"]
            }
        }
        user_model = base_model.bind(
            response_format={"type": "json_schema", "json_schema": user_schema}
        )

        # 测试 weather model
        weather_response = weather_model.invoke([
            HumanMessage(content="Current weather in Tokyo")
        ])
        print(f"✅ Weather response: {weather_response.content[:100]}...")

        # 测试 user model
        user_response = user_model.invoke([
            HumanMessage(content="Create user profile for John Doe")
        ])
        print(f"✅ User response: {user_response.content[:100]}...")

        return True

    except Exception as e:
        print(f"❌ 多次 bind() 测试失败: {e}")
        return False
'''

# 主函数
if __name__ == "__main__":
    print("🧪 开始测试 AzureChatOpenAI + model.bind() + json_schema 支持...")

    print("⚠️  注意：请先替换代码中的以下占位符:")
    print("   - 'your-api-key': 你的 Azure OpenAI API Key")
    print("   - 'your-model-name': 你的模型名称（如 'gpt-4o'）")
    print("   - 确保 deployment 名称与 model 名称匹配\n")

    # 执行测试
    success1 = test_json_schema_with_bind()
    success2 = test_simple_json_schema_with_bind()
    #success3 = test_streaming_with_bind()
    #success4 = test_multiple_binds()

    print(f"\n📋 测试总结:")
    print(f"- bind() + json_schema: {'✅ 成功' if success1 else '❌ 失败'}")
    print(f"- bind() + 简单 schema: {'✅ 成功' if success2 else '❌ 失败'}")
    #print(f"- bind() + 流式输出: {'✅ 成功' if success3 else '❌ 失败'}")
    #print(f"- 多次 bind() 测试: {'✅ 成功' if success4 else '❌ 失败'}")
import os
import openai
from langchain_openai import AzureChatOpenAI
import json
def test_json_schema_correct():
    client = openai.AzureOpenAI(
        azure_endpoint="https://sub3-openai-japan.openai.azure.com/",
        api_version="2025-03-01-preview",
        api_key=os.environ.get("AZURE_OPENAI_API_KEY", "")
    )

    try:
        print("🔍 测试正确的 json_schema 格式...")

        # ✅ 正确的 JSON Schema 定义
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # 替换为实际部署名
            messages=[
                {"role": "system", "content": "You are a helpful assistant that returns structured data."},
                {"role": "user", "content": "What's the weather like in Boston today?"}
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "get_weather",
                    "strict": True,  # 可选：启用严格模式
                    "schema": {
                        "type": "object",  # ✅ 关键：必须有 type: "object"
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
                                "description": "Weather condition (sunny, cloudy, rainy, etc.)",
                                "enum": ["sunny", "cloudy", "rainy", "snowy", "windy"]
                            }
                        },
                        "required": ["location", "temperature", "condition"],
                        "additionalProperties": False  # 可选：禁止额外属性
                    }
                }
            },
            temperature=0.1
        )

        print("✅ json_schema 格式测试成功！")
        print(f"Response: {response.choices[0].message.content}")

        # 解析 JSON 响应
        import json
        try:
            result = json.loads(response.choices[0].message.content)
            print(f"✅ 解析结果: {result}")
        except:
            print("❌ 无法解析 JSON 响应")

        return True

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def test_simple_json_schema():
    """测试更简单的 schema"""
    client = openai.AzureOpenAI(
        azure_endpoint="https://sub3-openai-japan.openai.azure.com/",
        api_version="2025-03-01-preview",
        api_key=os.environ.get("AZURE_OPENAI_API_KEY", "")
    )

    try:
        print("\n🔍 测试简单 json_schema 格式...")

        response = client.chat.completions.create(
            model="gpt-4o-mini",  # 替换为实际部署名
            messages=[
                {"role": "user", "content": "Return a simple user profile with name and age"}
            ],
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

        print("✅ 简单 json_schema 测试成功！")
        print(f"Response: {response.choices[0].message.content}")
        return True

    except Exception as e:
        print(f"❌ 简单测试失败: {e}")
        return False

# 执行测试
if __name__ == "__main__":
    print("🧪 开始测试 Azure OpenAI json_schema 支持...")
    print(f"OpenAI SDK 版本: {openai.__version__}\n")

    # 测试正确的格式
    test_json_schema_correct()

    # 测试简单格式
    test_simple_json_schema()
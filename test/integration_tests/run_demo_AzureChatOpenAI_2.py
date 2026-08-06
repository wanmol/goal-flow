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
            #model="gpt-4o",  # 替换为实际部署名
            model="gpt-4o-mini",  # 替换为实际部署名
            messages=[
                {"role": "system", "content": "You are a helpful assistant that returns structured data."},
                {"role": "user", "content": "What's the weather like in Boston today?"}
            ],
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
            model="gpt-4o",  # 替换为实际部署名
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
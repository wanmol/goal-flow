import os
from langchain_openai import AzureChatOpenAI
from typing import List

# 1. 直接定义JSON Schema字典
json_schema_dict = {
    "title": "StructuredAnswer", # 必需：定义输出对象的名称
    "description": "对用户问题的格式化回答，包含核心内容、置信度、要点和审核标记。", # 必需：描述这个结构的用途
    "type": "object",
    "properties": {
        "answer": {
            "type": "string",
            "description": "对问题的核心回答内容"
        },
        "confidence": {
            "type": "number",
            "description": "对回答准确性的置信度，范围从0到1",
            "minimum": 0,
            "maximum": 1
        },
        "key_points": {
            "type": "array",
            "items": {
                "type": "string"
            },
            "description": "支撑回答的关键要点列表"
        },
        "needs_human_review": {
            "type": "boolean",
            "description": "标记此回答是否需要额外的人工审核"
        }
    },
    "required": ["answer", "confidence", "key_points", "needs_human_review"],
    "additionalProperties": False  # 禁止返回未定义的字段，确保输出纯净
}

# 2. 初始化LLM
llm = AzureChatOpenAI(
    api_key=os.environ.get("AZURE_OPENAI_API_KEY", ""),
    azure_endpoint="https://sub3-openai-japan.openai.azure.com/",
    api_version="2025-03-01-preview",
    model="gpt-4o-mini",
    temperature=0.1,
    max_tokens=1000,
    streaming=True
)

# 3. 绑定JSON Schema字典
structured_llm = llm.with_structured_output(
    schema=json_schema_dict,  # 直接传入字典
    method="json_schema",
    include_raw=False
)

# 4. 测试调用
test_messages = [("human", "2025年北京公积金的提取流程是什么？")]
try:
    # 此时result是一个字典
    result = structured_llm.invoke(test_messages)

    print("🎯 JSON Schema字典模式测试成功！")
    print(f"结果类型: {type(result)}")
    print(f"完整结果: {result}")

    # 验证结构
    assert isinstance(result.get("answer"), str), "answer字段应为字符串"
    assert 0 <= result.get("confidence", -1) <= 1, "confidence应在0-1之间"
    print("✅ 返回结构验证通过")

except Exception as e:
    print(f"❌ 调用失败: {e}")
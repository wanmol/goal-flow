"""
DifyDataAdapter 与 AbstractDataAdapter 契约测试
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest

from goalflow.api.base_types import ChatCompletionBlockingResponse
from goalflow.workflow.services.data_adapter.abstract_data_adapter import AbstractDataAdapter
from goalflow.workflow.services.data_adapter.dify_data_adapter import DifyDataAdapter
from goalflow.workflow.services.data_adapter.openai_data_adapter import OpenAIDataAdapter


class TestAbstractContract:
    """抽象基类现在要求 generate + execute 两个方法。"""

    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            AbstractDataAdapter()

    def test_missing_execute_is_rejected(self):
        """只实现 generate 的子类不能实例化(契约收紧的核心验证)。"""
        class OnlyGenerate(AbstractDataAdapter):
            def generate(self, generator):
                yield from generator

        with pytest.raises(TypeError):
            OnlyGenerate()

    def test_both_methods_satisfies_contract(self):
        class Both(AbstractDataAdapter):
            def generate(self, generator):
                yield from generator
            def execute(self, data):
                return {}

        Both()  # 不应抛错

    def test_concrete_adapters_instantiate(self):
        """内置的两个具体适配器都满足契约。"""
        OpenAIDataAdapter()
        DifyDataAdapter()


class TestDifyDataAdapter:
    """Dify 适配器是 identity/透传实现。"""

    def setup_method(self):
        self.adapter = DifyDataAdapter()

    def test_generate_passthrough(self):
        lines = ["data: a\n\n", "data: b\n\n", ": comment\n\n"]
        assert list(self.adapter.generate(iter(lines))) == lines

    def test_generate_empty(self):
        assert list(self.adapter.generate(iter([]))) == []

    def test_execute_returns_dict(self):
        data = ChatCompletionBlockingResponse(
            task_id="t1", id="id1", message_id="m1",
            conversation_id="c1", answer="最终回答",
        )
        result = self.adapter.execute(data)

        assert isinstance(result, dict)
        assert result["answer"] == "最终回答"
        assert result["task_id"] == "t1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

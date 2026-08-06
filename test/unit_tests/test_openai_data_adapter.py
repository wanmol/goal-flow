"""
OpenAIDataAdapter 测试用例
测试流式消息转换、OpenAI 格式转换以及非流式响应转换
"""

import sys
import os
# 添加项目根目录到路径 (从 unit_tests -> test -> project_root)
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest

from goalflow.api.base_types import ChatStreamChunk, ChatCompletionBlockingResponse
from goalflow.workflow.services.data_adapter.openai_data_adapter import OpenAIDataAdapter


def _make_chunk(event="message", answer=None, message=None, metadata=None,
                message_id="msg-1", chunk_id="0"):
    """构造一个 ChatStreamChunk 实例"""
    return ChatStreamChunk(
        chunk_id=chunk_id,
        event=event,
        data={},
        timestamp="2026-08-01T00:00:00",
        answer=answer,
        task_id="task-1",
        message_id=message_id,
        conversation_id="conv-1",
        metadata=metadata,
        message=message,
    )


def _sse_line(chunk: ChatStreamChunk) -> str:
    """将 chunk 序列化为 SSE 行"""
    return f"data: {chunk.model_dump_json()}\n\n"


class TestConvertChunkToOpenAIFormat:
    """_convert_chunk_to_openai_format 转换逻辑测试"""

    def setup_method(self):
        self.adapter = OpenAIDataAdapter()

    def test_message_with_content(self):
        """有内容的 message: finish_reason 为空串, delta 为 answer"""
        chunk = _make_chunk(event="message", answer="你好")
        result = self.adapter._convert_chunk_to_openai_format(chunk)

        assert result["status"] == "success"
        assert result["reason"] == "success"
        assert result["finish_reason"] == ""
        assert result["choices"][0]["delta"] == "你好"
        assert result["choices"][0]["finish_reason"] == ""

    def test_message_empty_answer_is_last(self):
        """answer 为空视为结束: finish_reason 为 stop"""
        chunk = _make_chunk(event="message", answer="")
        result = self.adapter._convert_chunk_to_openai_format(chunk)

        assert result["finish_reason"] == "stop"
        assert result["choices"][0]["finish_reason"] == "stop"

    def test_message_none_answer_is_last(self):
        """answer 为 None 也视为结束"""
        chunk = _make_chunk(event="message", answer=None)
        result = self.adapter._convert_chunk_to_openai_format(chunk)

        assert result["finish_reason"] == "stop"

    def test_message_meta_flag_ignored_bug(self):
        """
        当前实现读取 chunk.meta, 但模型字段名为 metadata, 因此元数据里的
        is_last/finish/end_of_stream 结束标志【永远不会】被识别。
        只要 answer 非空, finish_reason 仍为空串。
        这是源码的一个 BUG (openai_data_adapter.py:46 应为 chunk.metadata)。
        """
        for flag in ("is_last", "finish", "end_of_stream"):
            chunk = _make_chunk(event="message", answer="继续",
                                metadata={flag: True})
            result = self.adapter._convert_chunk_to_openai_format(chunk)

            assert result["finish_reason"] == "", f"metadata 标志 {flag} 意外生效"

    def test_error_event(self):
        """error 事件: status failed, reason 为错误消息"""
        chunk = _make_chunk(event="error", message="出错了")
        result = self.adapter._convert_chunk_to_openai_format(chunk)

        assert result["status"] == "failed"
        assert result["reason"] == "出错了"
        assert result["finish_reason"] == "stop"
        assert result["choices"] == []

    def test_other_event_raises_bug(self):
        """
        其他事件类型走 else 分支, 调用了不存在的 self._get_current_timestamp(),
        直接触发 AttributeError。这是源码 BUG (openai_data_adapter.py:84)。
        注意: generate() 会先过滤掉 message/error 以外的事件, 因此该分支
        仅在直接调用私有方法时可达。
        """
        chunk = _make_chunk(event="done", answer="x", message_id="abc")

        with pytest.raises(AttributeError):
            self.adapter._convert_chunk_to_openai_format(chunk)


class TestGenerate:
    """generate 流式转换测试"""

    def setup_method(self):
        self.adapter = OpenAIDataAdapter()

    def test_yields_message_chunks(self):
        """message 事件被转换并 yield"""
        chunk = _make_chunk(event="message", answer="hi")
        outputs = list(self.adapter.generate(iter([_sse_line(chunk)])))

        assert len(outputs) == 1
        assert outputs[0].startswith("data:  ")
        assert outputs[0].endswith("\n\n")

    def test_yields_error_chunks(self):
        """error 事件被转换并 yield"""
        chunk = _make_chunk(event="error", message="boom")
        outputs = list(self.adapter.generate(iter([_sse_line(chunk)])))

        assert len(outputs) == 1

    def test_skips_non_data_lines(self):
        """非 data: 前缀的行被跳过"""
        outputs = list(self.adapter.generate(iter([": ping\n\n", "\n"])))

        assert outputs == []

    def test_skips_non_message_error_events(self):
        """非 message/error 事件被跳过"""
        chunk = _make_chunk(event="done", answer="x")
        outputs = list(self.adapter.generate(iter([_sse_line(chunk)])))

        assert outputs == []

    def test_mixed_stream(self):
        """混合流: 只保留 message 和 error 事件"""
        lines = [
            _sse_line(_make_chunk(event="message", answer="a")),
            ": comment\n\n",
            _sse_line(_make_chunk(event="done", answer="b")),
            _sse_line(_make_chunk(event="error", message="err")),
        ]
        outputs = list(self.adapter.generate(iter(lines)))

        assert len(outputs) == 2


class TestExecute:
    """execute 非流式响应转换测试"""

    def setup_method(self):
        self.adapter = OpenAIDataAdapter()

    def test_execute_returns_answer(self):
        """execute 将 answer 映射到 content 并标记成功"""
        data = ChatCompletionBlockingResponse(
            task_id="t1",
            id="id1",
            message_id="m1",
            conversation_id="c1",
            answer="最终回答",
        )
        result = self.adapter.execute(data)

        assert result["content"] == "最终回答"
        assert result["choices"] == []
        assert result["finish_reason"] == "stop"
        assert result["status"] == "success"
        assert result["reason"] == "success"


import ast

from goalflow.api.base_types import format_stream_chunk


def _parse_openai_line(line: str) -> dict:
    """
    解析 generate() 输出的一行。
    注意: generate() 用 f-string 拼接的是 dict 的 repr(单引号/None),
    因此这里用 ast.literal_eval 而非 json.loads。
    """
    assert line.startswith("data:  "), f"意外的前缀: {line!r}"
    assert line.endswith("\n\n")
    payload = line[len("data:  "):].strip()
    return ast.literal_eval(payload)


class TestEndToEndStream:
    """
    端到端流式测试。
    模拟上游用 format_stream_chunk 产出的真实 SSE 字节流,
    经 OpenAIDataAdapter.generate 消费, 断言最终 OpenAI 格式输出。
    """

    def setup_method(self):
        self.adapter = OpenAIDataAdapter()

    def _upstream_stream(self):
        """上游按 SSE 协议逐条 yield 的生成器"""
        yield format_stream_chunk(
            chunk_id=0, event_type="message", data={},
            task_id="t-1", message_id="m-1", conversation_id="c-1",
            answer="你",
        )
        yield format_stream_chunk(
            chunk_id=1, event_type="message", data={},
            task_id="t-1", message_id="m-1", conversation_id="c-1",
            answer="好",
        )
        # 非 message/error 事件, 应被适配器过滤
        yield format_stream_chunk(
            chunk_id=2, event_type="update", data={"progress": 0.5},
            task_id="t-1", message_id="m-1", conversation_id="c-1",
        )
        # 空 answer, 视为结束
        yield format_stream_chunk(
            chunk_id=3, event_type="message", data={},
            task_id="t-1", message_id="m-1", conversation_id="c-1",
            answer="",
        )

    def test_full_stream_roundtrip(self):
        """完整流: 两条内容 + 一条结束, update 事件被过滤"""
        outputs = list(self.adapter.generate(self._upstream_stream()))

        # update 事件被过滤, 剩 3 条 message
        assert len(outputs) == 3

        first = _parse_openai_line(outputs[0])
        assert first["choices"][0]["delta"] == "你"
        assert first["finish_reason"] == ""
        assert first["status"] == "success"

        second = _parse_openai_line(outputs[1])
        assert second["choices"][0]["delta"] == "好"

        last = _parse_openai_line(outputs[2])
        assert last["finish_reason"] == "stop"

    def test_full_stream_with_error(self):
        """上游中途报错: error 事件转换为 failed 状态并输出"""
        def stream():
            yield format_stream_chunk(
                chunk_id=0, event_type="message", data={},
                task_id="t-1", message_id="m-1", conversation_id="c-1",
                answer="部分",
            )
            yield format_stream_chunk(
                chunk_id=1, event_type="error", data={},
                task_id="t-1", message_id="m-1", conversation_id="c-1",
                message="上游异常",
            )

        outputs = list(self.adapter.generate(stream()))

        assert len(outputs) == 2
        err = _parse_openai_line(outputs[1])
        assert err["status"] == "failed"
        assert err["reason"] == "上游异常"
        assert err["finish_reason"] == "stop"
        assert err["choices"] == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

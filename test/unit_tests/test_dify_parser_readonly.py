"""
DifyDslParser 只读解析测试
验证 parse() 不再修改用户的 DSL 文件，且内存内替换/可配置替换表行为正确。
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest

from goalflow.dify_parser.dify_dsl_parser import DifyDslParser


def _write(tmp_path, text):
    p = tmp_path / "flow.yml"
    p.write_text(text, encoding="utf-8")
    return str(p)


def _capture_parser(path, **kwargs):
    """构造 parser 并桩掉 parse_data，只捕获传给它的 dict(即文件读取+替换后的结果)。

    这样测试聚焦于 parse() 的文件处理/替换行为，不牵扯下游图校验。
    """
    parser = DifyDslParser(path, **kwargs)
    captured = {}
    parser.parse_data = lambda data: captured.setdefault("data", data)
    parser.parse()
    return captured["data"]


def test_parse_does_not_mutate_file(tmp_path):
    """parse() 必须保持输入文件字节不变(只读)。默认替换表命中也不写回磁盘。"""
    # 用 code-node 引号形式的默认替换键，确保替换确实发生但文件不被改写
    dsl = "app:\n  name: \"'http://39.97.230.203:8001/v1/rerank'\"\n"
    path = _write(tmp_path, dsl)
    before = open(path, encoding="utf-8").read()

    data = _capture_parser(path)  # 使用默认替换表

    after = open(path, encoding="utf-8").read()
    assert after == before, "parse() 不应写回/修改用户的 DSL 文件"
    # 内存内确实应用了默认替换
    assert data["app"]["name"] == "os.environ['AIRA_RERANK_URL']"


def test_substitution_applied_in_memory(tmp_path):
    """替换表命中时，交给 parse_data 的内容应被替换，但磁盘文件不变。"""
    dsl = 'app:\n  name: "http://old-host/api"\n'
    path = _write(tmp_path, dsl)

    data = _capture_parser(path, host_substitutions={"http://old-host/api": "REPLACED"})

    # 磁盘仍是原值
    assert "http://old-host/api" in open(path, encoding="utf-8").read()
    # 解析用的是替换后的值
    assert data["app"]["name"] == "REPLACED"


def test_empty_substitution_table_disables_rewrite(tmp_path):
    """传入空替换表 → 不做任何替换。"""
    dsl = 'app:\n  name: "http://39.97.230.203:8001/v1/rerank"\n'
    path = _write(tmp_path, dsl)

    data = _capture_parser(path, host_substitutions={})

    assert data["app"]["name"] == "http://39.97.230.203:8001/v1/rerank"


def test_default_substitution_table_present():
    """默认替换表非空,且覆盖 code/http 两种形式。"""
    table = DifyDslParser.DEFAULT_HOST_SUBSTITUTIONS
    assert table, "默认替换表不应为空"
    # code node 形式(引号内)与 http node 形式(裸串)都应存在
    assert any(k.startswith("'http") for k in table), "缺少 code-node 引号形式"
    assert any(k.startswith("http") and not k.startswith("'") for k in table), "缺少 http-node 裸串形式"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

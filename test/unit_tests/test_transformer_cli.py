"""
转译器 CLI 与输出路径解析测试
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest

from goalflow.tool.dify_transformer.wf_code_generator import WorkflowCodeGenerator
from goalflow.tool.dify_transformer import wf_transformer_tool


def _gen(**kwargs):
    # dsl_path 不会被真正解析(只测路径解析),给个占位路径即可
    return WorkflowCodeGenerator("dummy.yml", **kwargs)


class TestOutputPathResolution:
    def test_default_goes_to_generated_dir(self):
        g = _gen(file_name="foo.py")
        out = g._resolve_output_path()
        assert out.endswith(os.path.join("workflow", "generated", "foo.py"))

    def test_explicit_file_path(self, tmp_path):
        target = str(tmp_path / "my_flow.py")
        g = _gen(file_name="ignored.py", out_path=target)
        assert g._resolve_output_path() == os.path.abspath(target)

    def test_directory_path_uses_file_name(self, tmp_path):
        d = str(tmp_path)  # 已存在的目录
        g = _gen(file_name="named.py", out_path=d)
        assert g._resolve_output_path() == os.path.join(os.path.abspath(d), "named.py")

    def test_trailing_sep_treated_as_dir(self):
        g = _gen(file_name="named.py", out_path="some/dir/")
        assert g._resolve_output_path() == os.path.join(os.path.abspath("some/dir"), "named.py")


class TestCliParsing:
    def test_required_dsl(self):
        with pytest.raises(SystemExit):
            wf_transformer_tool.build_parser().parse_args([])

    def test_full_args(self):
        ns = wf_transformer_tool.build_parser().parse_args(
            ["--dsl", "flow.yml", "--out", "out.py", "--class", "MyWf"]
        )
        assert ns.dsl == "flow.yml"
        assert ns.out == "out.py"
        assert ns.class_name == "MyWf"

    def test_defaults(self):
        ns = wf_transformer_tool.build_parser().parse_args(["--dsl", "flow.yml"])
        assert ns.out is None
        assert ns.class_name is None


class TestCliMain:
    def test_missing_dsl_returns_2(self, capsys):
        rc = wf_transformer_tool.main(["--dsl", "does_not_exist.yml"])
        assert rc == 2
        assert "not found" in capsys.readouterr().err

    def test_main_invokes_generator(self, tmp_path, monkeypatch):
        """--dsl 存在时，main 应构造 generator 并调用 generate(),返回 0。"""
        dsl = tmp_path / "flow.yml"
        dsl.write_text("app: {}\n", encoding="utf-8")

        calls = {}

        class FakeGen:
            def __init__(self, dsl_path, **kwargs):
                calls["dsl_path"] = dsl_path
                calls["kwargs"] = kwargs
            def generate(self):
                return "/written/path.py"

        monkeypatch.setattr(wf_transformer_tool, "WorkflowCodeGenerator", FakeGen)

        rc = wf_transformer_tool.main(["--dsl", str(dsl), "--out", "x.py", "--class", "X"])

        assert rc == 0
        assert calls["dsl_path"] == str(dsl)
        assert calls["kwargs"]["file_name"] == "x.py"
        assert calls["kwargs"]["class_name"] == "X"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

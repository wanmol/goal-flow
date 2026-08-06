"""n8n JSON → 可运行 goalflow workflow 转译 CLI。

用法::

    python -m goalflow.tool.n8n_transformer.n8n_transformer_tool \\
        --json path/to/workflow.json \\
        --out my_flow_workflow.py \\
        --class MyFlowWorkflow
"""
import argparse
import os
import sys

from goalflow.tool.n8n_transformer.n8n_code_generator import N8nCodeGenerator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m goalflow.tool.n8n_transformer.n8n_transformer_tool",
        description="Transpile an n8n workflow JSON into a runnable goalflow workflow (.py).",
    )
    parser.add_argument("--json", required=True, help="Path to the n8n workflow JSON.")
    parser.add_argument(
        "--out",
        default=None,
        help=(
            "Output path: a filename, or a full path/directory. "
            "If omitted, writes to src/goalflow/workflow/generated/<file_name>."
        ),
    )
    parser.add_argument(
        "--class",
        dest="class_name",
        default=None,
        help="Class name for the generated workflow (optional).",
    )
    return parser


def main(argv=None) -> int:
    # Windows 控制台默认 GBK,重配置为 UTF-8 以便打印 emoji / 中文警告
    for stream in (sys.stdout, sys.stderr):
        reconfig = getattr(stream, "reconfigure", None)
        if reconfig:
            try:
                reconfig(encoding="utf-8")
            except Exception:
                pass

    args = build_parser().parse_args(argv)

    if not os.path.isfile(args.json):
        print(f"❌ n8n JSON file not found: {args.json}", file=sys.stderr)
        return 2

    file_name = "n8n_workflow.py"
    out_path = None
    if args.out:
        if args.out.endswith(("/", os.sep)) or os.path.isdir(args.out):
            out_path = args.out
        else:
            base = os.path.basename(args.out)
            if base:
                file_name = base
            out_path = args.out

    try:
        generator = N8nCodeGenerator(
            args.json,
            file_name=file_name,
            class_name=args.class_name,
            out_path=out_path,
        )
        written = generator.generate()
        print(f"✅ Generated workflow: {written}")
        if generator.warnings:
            print(
                f"⚠️  {len(generator.warnings)} 个 n8n 节点无 goalflow 对应,"
                f"已生成占位节点(需人工补齐):",
                file=sys.stderr,
            )
            for w in generator.warnings:
                print(f"    - {w}", file=sys.stderr)
        return 0
    except Exception as e:
        print(f"❌ Transpile failed: {e}", file=sys.stderr)
        raise


if __name__ == "__main__":
    sys.exit(main())

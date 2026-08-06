"""Dify DSL → runnable goalflow workflow transpiler CLI.

Usage:
    python -m goalflow.tool.dify_transformer.wf_transformer_tool \\
        --dsl path/to/flow.yml \\
        --out my_flow_workflow.py \\
        --class MyFlowWorkflow
"""
import argparse
import os
import sys

from goalflow.tool.dify_transformer.wf_code_generator import WorkflowCodeGenerator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m goalflow.tool.dify_transformer.wf_transformer_tool",
        description="Transpile a Dify DSL export into a runnable goalflow workflow (.py).",
    )
    parser.add_argument(
        "--dsl",
        required=True,
        help="Path to the Dify DSL export (.yml).",
    )
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
    # Windows 控制台默认 GBK,重配置为 UTF-8 以便打印 emoji / 中文
    for stream in (sys.stdout, sys.stderr):
        reconfig = getattr(stream, "reconfigure", None)
        if reconfig:
            try:
                reconfig(encoding="utf-8")
            except Exception:
                pass

    args = build_parser().parse_args(argv)

    if not os.path.isfile(args.dsl):
        print(f"❌ DSL file not found: {args.dsl}", file=sys.stderr)
        return 2

    # --out may be a bare filename, a directory, or a full path.
    # Split it so WorkflowCodeGenerator gets file_name + optional out_path.
    file_name = "workflow.py"
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
        generator = WorkflowCodeGenerator(
            args.dsl,
            file_name=file_name,
            class_name=args.class_name,
            out_path=out_path,
        )
        written = generator.generate()
        print(f"✅ Generated workflow: {written}")
        return 0
    except Exception as e:
        print(f"❌ Transpile failed: {e}", file=sys.stderr)
        raise


if __name__ == "__main__":
    sys.exit(main())

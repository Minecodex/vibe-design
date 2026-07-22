from __future__ import annotations

import argparse

from app.services.agent_harness.runtime.eventing.trace_export import export_trace_log


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export a harness conversation trace log from the database.")
    parser.add_argument("--user-id", type=int, required=True, help="Harness user id")
    parser.add_argument("--conversation-id", required=True, help="Harness conversation id")
    parser.add_argument("--run-id", default=None, help="Optional run id filter")
    parser.add_argument(
        "--profile",
        choices=("diagnostic", "full"),
        default="diagnostic",
        help="Trace export profile",
    )
    parser.add_argument("--seq-from", type=int, default=None, help="Inclusive sequence start")
    parser.add_argument("--seq-to", type=int, default=None, help="Inclusive sequence end")
    parser.add_argument(
        "--output-file",
        default=None,
        help="Optional file path under the conversation directory. Defaults to trace.log",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    path = export_trace_log(
        args.user_id,
        args.conversation_id,
        run_id=args.run_id,
        profile=args.profile,
        seq_from=args.seq_from,
        seq_to=args.seq_to,
        output_path=args.output_file,
    )
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

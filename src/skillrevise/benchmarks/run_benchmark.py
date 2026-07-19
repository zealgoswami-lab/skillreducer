"""Benchmark-only entry point for SkillRevise evaluation harnesses.

This module is for running paper/eval benchmarks (SkillsBench, SkillLearnBench,
ALFWorld). It is not required for revising your own skills with a generic
tasks.json via ``skillrevise`` / ``skillreducer revise``.
"""

from __future__ import annotations

import sys

BENCHMARK_KINDS = ("skillsbench", "skilllearnbench", "alfworld")

BANNER = """\
SkillRevise BENCHMARK runner (eval only)
  Package: src/skillrevise/benchmarks/
  Paper:   https://arxiv.org/abs/2606.01139
  Docs:    src/skillrevise/benchmarks/README.md

Use this only for SkillsBench / SkillLearnBench / ALFWorld-style evals.
For your own tasks, use:  skillrevise <tasks.json> ...
"""


def main(argv: list[str] | None = None) -> None:
    """Run SkillRevise CLI with benchmark-oriented defaults and help."""
    args = list(sys.argv[1:] if argv is None else argv)

    if not args or args[0] in {"-h", "--help"}:
        print(BANNER)
        print(
            "Usage:\n"
            "  skillrevise-benchmark <tasks.json> --manifest-kind skillsbench [options...]\n"
            "  skillrevise-benchmark <tasks.json> --manifest-kind skilllearnbench [options...]\n"
            "  skillrevise-benchmark <tasks.json> --manifest-kind alfworld [options...]\n"
            "\n"
            "Convert SkillsBench task dirs → manifest:\n"
            "  skillrevise-convert-skillsbench --help\n"
            "\n"
            "All remaining flags are forwarded to ``skillrevise`` "
            "(see skillrevise --help).\n"
        )
        if args and args[0] in {"-h", "--help"}:
            # Also show full upstream CLI help for discoverability.
            from skillrevise.cli import main as skillrevise_main

            previous = sys.argv
            sys.argv = ["skillrevise", "--help"]
            try:
                skillrevise_main()
            except SystemExit:
                pass
            finally:
                sys.argv = previous
        return

    if "--manifest-kind" not in args:
        print(
            "error: skillrevise-benchmark requires --manifest-kind "
            f"({'|'.join(BENCHMARK_KINDS)})\n"
            "For generic tasks.json revision, use: skillrevise <tasks.json> ...",
            file=sys.stderr,
        )
        raise SystemExit(2)

    # Reject generic — this entry point is benchmark-only.
    try:
        kind_idx = args.index("--manifest-kind")
        kind = args[kind_idx + 1] if kind_idx + 1 < len(args) else ""
    except ValueError:
        kind = ""
    if kind == "generic":
        print(
            "error: --manifest-kind generic is not allowed on skillrevise-benchmark.\n"
            "Use skillrevise for generic tasks; this command is benchmark-only.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    if kind and kind not in BENCHMARK_KINDS:
        print(
            f"error: unknown --manifest-kind {kind!r}; "
            f"expected one of {', '.join(BENCHMARK_KINDS)}",
            file=sys.stderr,
        )
        raise SystemExit(2)

    print(BANNER.splitlines()[0])
    from skillrevise.cli import main as skillrevise_main

    previous = sys.argv
    sys.argv = ["skillrevise", *args]
    try:
        skillrevise_main()
    finally:
        sys.argv = previous


if __name__ == "__main__":
    main()

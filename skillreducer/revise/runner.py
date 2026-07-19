"""Run the vendored ``skillrevise`` package (src/skillrevise) without touching SkillReducer stages."""

from __future__ import annotations

import sys
from typing import Sequence

INSTALL_HINT = """\
SkillRevise could not be imported.

Expected vendored package at src/skillrevise (import name: skillrevise).
Reinstall editable:

  pip install -e .

Upstream source: https://github.com/xuansenpa1/skillrevise
Paper:          https://arxiv.org/abs/2606.01139

``skillreducer revise`` forwards args to the SkillRevise CLI.
It does not change ``audit``, ``reduce``, or ``agent``.
"""


class SkillReviseNotInstalled(RuntimeError):
    """Raised when the vendored ``skillrevise`` package cannot be imported."""


def skillrevise_installed() -> bool:
    """Return True if the vendored ``skillrevise`` package can be imported."""
    try:
        import skillrevise  # noqa: F401
    except ImportError:
        return False
    return True


def run_skillrevise(argv: Sequence[str]) -> int:
    """Run vendored ``skillrevise.cli.main`` with ``argv`` (no program name).

    Args:
        argv: Arguments as they would follow ``skillrevise`` on the CLI.

    Returns:
        Process-style exit code (0 on success).

    Raises:
        SkillReviseNotInstalled: If the vendored package is missing from the install.
    """
    if not skillrevise_installed():
        raise SkillReviseNotInstalled(INSTALL_HINT.strip())

    from skillrevise.cli import main as skillrevise_main

    previous = sys.argv
    sys.argv = ["skillrevise", *list(argv)]
    try:
        skillrevise_main()
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        return 1
    finally:
        sys.argv = previous
    return 0

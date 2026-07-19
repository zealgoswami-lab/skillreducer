#!/usr/bin/env python3
"""Run skillreducer from source without building a binary.

Loads .env (api_key / api_base_url / model ids), then dispatches to the CLI.

Usage:
    python run.py audit data --recursive
    python run.py reduce data/pdf-processing --stage 1
    python run.py agent data/marketing-strategy --stage 1
    python run.py revise --skillrevise-help   # SkillRevise; vendored in src/skillrevise
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path when run as a script.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skillreducer.config import ensure_dotenv_loaded  # noqa: E402
from skillreducer.cli import main  # noqa: E402


def run() -> None:
    ensure_dotenv_loaded()
    main()


if __name__ == "__main__":
    run()

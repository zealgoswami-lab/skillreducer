from pathlib import Path

from skillreducer.audit import audit_skill
from skillreducer.config import Config
from skillreducer.pipeline import reduce_skill


def test_audit_detects_monolithic_examples() -> None:
    report = audit_skill(Path("tests/fixtures/sample-pdf-skill"))
    codes = {issue.code for issue in report.issues}
    assert "F2_MONOLITHIC" in codes
    assert report.stats.total > 0


def test_reduce_dry_run_improves_or_maintains_tokens() -> None:
    config = Config(use_llm=False)
    report = reduce_skill(
        Path("tests/fixtures/sample-pdf-skill"),
        output_dir=Path("optimized"),
        config=config,
        dry_run=True,
    )
    assert report.original_stats.total > 0
    assert report.optimized_stats.total <= report.original_stats.total
    assert report.llm_usage.calls == 0


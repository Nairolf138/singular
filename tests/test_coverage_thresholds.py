from pathlib import Path

from scripts.check_coverage_thresholds import (
    extract_file_coverages,
    resolve_coverage,
)


def test_coverage_guard_resolves_source_root_in_xml(tmp_path: Path) -> None:
    report = tmp_path / "coverage.xml"
    report.write_text(
        '<coverage><sources><source>/checkout/src/singular</source></sources>'
        '<packages><package><classes><class filename="cli.py" line-rate="0.9" />'
        '</classes></package></packages></coverage>',
        encoding="utf-8",
    )

    coverages = extract_file_coverages(report)
    filename, percent = resolve_coverage("src/singular/cli.py", coverages)

    assert filename == "checkout/src/singular/cli.py"
    assert percent == 90.0
    assert resolve_coverage("src/singular/other.py", coverages) == (None, None)

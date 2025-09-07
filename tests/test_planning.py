from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))
from planning import plan_library

FIXTURES = Path(__file__).parent / "fixtures" / "library"


def test_disc_gap_quarantine(tmp_path):
    plan = plan_library(FIXTURES, tmp_path)
    item = next(p for p in plan if "disc_gap" in Path(p["source"]).parts)
    assert item["action"] == "quarantine"


def test_ambiguous_skip(tmp_path):
    plan = plan_library(FIXTURES, tmp_path)
    item = next(p for p in plan if "ambiguous" in Path(p["source"]).parts)
    assert item["action"] == "skip"


def test_duplicates_redirect(tmp_path):
    plan = plan_library(FIXTURES, tmp_path)
    dup_entries = [p for p in plan if "dup" in Path(p["source"]).name]
    assert any("_duplicates" in p["dest"] for p in dup_entries)

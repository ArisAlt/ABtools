import json, sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))
from abclient import AbClient


def test_reads_config_file(tmp_path):
    cfg = tmp_path / "ab.json"
    cfg.write_text(json.dumps({"use_goodreads": True}))
    client = AbClient(path=cfg)
    assert client.is_on("use_goodreads") is True

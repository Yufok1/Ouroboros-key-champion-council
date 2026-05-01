import json
import subprocess
import sys
from pathlib import Path


def test_cli_sample_writes_geojson(tmp_path: Path):
    output = tmp_path / "sample.geojson"
    result = subprocess.run(
        [sys.executable, "-m", "middle_passage", "sample", "--output", str(output)],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=True,
    )

    assert "wrote synthetic-safe sample" in result.stdout
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["type"] == "FeatureCollection"
    assert payload["features"]


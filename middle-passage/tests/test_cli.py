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


def test_cli_sample_can_write_and_replay_input_data(tmp_path: Path):
    output = tmp_path / "sample.geojson"
    replay = tmp_path / "sample.replay.json"
    replayed = tmp_path / "sample.replayed.geojson"

    sample_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "middle_passage",
            "sample",
            "--output",
            str(output),
            "--replay-output",
            str(replay),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=True,
    )

    replay_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "middle_passage",
            "replay",
            "--input",
            str(replay),
            "--output",
            str(replayed),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=True,
    )

    replay_payload = json.loads(replay.read_text(encoding="utf-8"))
    assert "wrote synthetic-safe sample" in sample_result.stdout
    assert "replayed 1 survey-priority zone" in replay_result.stdout
    assert replay_payload["schema"] == "middle_passage_replay_packet.v1"
    assert replay_payload["status"] == "replayable_input"
    assert replay_payload["receipts"]["input_hash"]
    assert replay_payload["receipts"]["output_hash"]
    assert json.loads(output.read_text(encoding="utf-8")) == json.loads(
        replayed.read_text(encoding="utf-8")
    )

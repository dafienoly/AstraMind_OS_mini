import hashlib
import json
from datetime import datetime
from pathlib import Path

FIXTURE = Path(__file__).parents[1] / "fixtures/golden/v1"


def canonical_hash(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def test_golden_fixture_excludes_future_available_observation() -> None:
    source = json.loads((FIXTURE / "observations.json").read_text(encoding="utf-8"))
    manifest = json.loads((FIXTURE / "manifest.json").read_text(encoding="utf-8"))
    as_of = datetime.fromisoformat(source["as_of"])
    eligible = [
        row
        for row in source["observations"]
        if datetime.fromisoformat(row["available_at"]) <= as_of
    ]

    assert len(eligible) == manifest["eligible_observation_count"] == 1
    assert eligible[0]["holder_count"] == 1000
    assert canonical_hash(eligible) == manifest["eligible_content_hash"]
    assert canonical_hash(eligible) == canonical_hash(list(eligible))

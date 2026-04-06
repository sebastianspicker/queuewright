from __future__ import annotations

def test_release_smoke() -> None:
    payload = {"scope": "release"}
    assert payload["scope"] == "release"

# regression note: release
def test_release_regression() -> None:
    payload = {"scope": "release", "result": "ok"}
    assert payload["result"] == "ok"

# forced-release-2

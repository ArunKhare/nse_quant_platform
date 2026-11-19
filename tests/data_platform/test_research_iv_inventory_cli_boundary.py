"""Actual CLI/profile boundary over disposable bytes; no native/source computations."""

import hashlib
import json

from nse_quant.data_platform.research_iv_inventory_cli import main


def test_actual_cli_executes_profile_gated_readonly_inventory(tmp_path, capsys):
    raw = b"synthetic content, not a research model result"
    pin = hashlib.sha256(raw).hexdigest()
    path = tmp_path / (pin + ".research-iv.json")
    path.write_bytes(raw)
    assert main(["--artifact-root", str(tmp_path), "--execute"]) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["unchanged_observed"] is True
    assert value["stage_ownership_checked"] is False
    assert value["canonical_bundle_schema_checked"] is False
    assert value["destructive_actions_authorized"] is False
    assert path.read_bytes() == raw


def test_actual_cli_missing_root_sanitized_without_creation(tmp_path, capsys):
    path = tmp_path / "missing-root"
    assert main(["--artifact-root", str(path), "--execute"]) == 1
    assert not path.exists()
    assert json.loads(capsys.readouterr().out) == {
        "status": "FAILED",
        "reason_code": "IV_ARTIFACT_INVENTORY_FAILED",
    }


def test_actual_cli_does_not_clear_pending_remnants(tmp_path, capsys):
    pending = tmp_path / ".pending-iv-SYNTHETIC_SECRET"
    pending.write_bytes(b"retained")
    assert main(["--artifact-root", str(tmp_path), "--execute"]) == 0
    raw = capsys.readouterr().out
    assert "SYNTHETIC_SECRET" not in raw
    assert json.loads(raw)["first_pass"][0]["kind"] == "PENDING_REMNANT_REVIEW"
    assert pending.read_bytes() == b"retained"

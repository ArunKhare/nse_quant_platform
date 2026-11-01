"""Plan boundary and real CLI/store SQL checks; source computation substituted."""

import builtins
import hashlib
import json
from dataclasses import asdict, replace

import duckdb
import pytest

from nse_quant.data_platform import gold_quote_build_cli as cli
from nse_quant.data_platform import gold_quote_store as store
from nse_quant.data_platform.gold_quote_features import (
    DEFINITION_FINGERPRINT,
    FEATURE_VERSION,
    GoldQuoteCandidate,
)

PIN = "a" * 64


def blocked():
    candidate = GoldQuoteCandidate(
        "",
        FEATURE_VERSION,
        DEFINITION_FINGERPRINT,
        PIN,
        "blocked",
        "SOURCE_ASSESSMENT_NOT_CURRENT",
    )
    raw = json.dumps(asdict(candidate), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return replace(candidate, build_id=hashlib.sha256(raw.encode()).hexdigest())


def arguments(tmp_path):
    return [
        "--bronze-db",
        str(tmp_path / "bronze.duckdb"),
        "--frame-silver-db",
        str(tmp_path / "frames.duckdb"),
        "--reference-silver-db",
        str(tmp_path / "references.duckdb"),
        "--assessment-db",
        str(tmp_path / "assessments.duckdb"),
        "--gold-db",
        str(tmp_path / "gold.duckdb"),
        "--assessment-revision-id",
        PIN,
    ]


def inputs(tmp_path):
    paths = [
        tmp_path / name
        for name in ("bronze.duckdb", "frames.duckdb", "references.duckdb", "assessments.duckdb")
    ]
    for path in paths:
        connection = duckdb.connect(str(path))
        connection.execute("CREATE TABLE marker (id INTEGER)")
        connection.close()
    return paths


def test_plan_no_execution_imports_or_files(tmp_path, monkeypatch, capsys):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name in {"duckdb", "nse_quant.data_platform.gold_quote_store"}:
            raise AssertionError("Plan imported execution dependency")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    assert cli.main(arguments(tmp_path) + ["--initialize"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "PLANNED"
    assert result["plan"]["inputs_verified"] is False
    assert result["plan"]["publication_requested"] is False
    assert list(tmp_path.iterdir()) == []


def test_execute_real_store_read_only_sources_and_blocked_evidence(tmp_path, monkeypatch, capsys):
    paths = inputs(tmp_path)
    before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]

    def compute(*connections, assessment_revision_id):
        assert assessment_revision_id == PIN
        for connection in connections:
            assert connection.execute("SELECT count(*) FROM marker").fetchone() == (0,)
            with pytest.raises(duckdb.InvalidInputException):
                connection.execute("INSERT INTO marker VALUES (1)")
        return blocked()

    monkeypatch.setattr(store, "build_quote_price_candidate", compute)
    options = arguments(tmp_path) + ["--execute", "--initialize", "--code-revision", "head"]
    assert cli.main(options) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["execution_status"] == "COMMITTED"
    assert output["status"] == "blocked"
    assert output["published"] is False
    assert output["decision_eligibility_asserted"] is False
    assert [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths] == before
    with duckdb.connect(str(tmp_path / "gold.duckdb"), read_only=True) as gold:
        table = store._name(gold, "quote_price_builds")
        assert gold.execute(f"SELECT count(*) FROM {table}").fetchone() == (1,)
        assert gold.execute(
            "SELECT state FROM medallion_audit.job_events ORDER BY event_index DESC LIMIT 1"
        ).fetchone() == ("SUCCEEDED",)


def test_alias_frame_reference_connection_reused(tmp_path, monkeypatch):
    inputs(tmp_path)
    args = arguments(tmp_path)
    args[5] = args[3]

    def compute(bronze, frames, references, assessments, **kwargs):
        assert frames is references
        return blocked()

    monkeypatch.setattr(store, "build_quote_price_candidate", compute)
    assert cli.main(args + ["--execute", "--initialize", "--code-revision", "head"]) == 0


def test_execution_error_redacted_and_handles_closed(tmp_path, monkeypatch, capsys):
    paths = inputs(tmp_path)

    def fail(*args, **kwargs):
        raise RuntimeError("SECRET_SOURCE_DETAILS")

    monkeypatch.setattr(store, "build_quote_price_candidate", fail)
    options = arguments(tmp_path) + ["--execute", "--initialize", "--code-revision", "head"]
    assert cli.main(options) == 1
    output = capsys.readouterr().out
    assert "SECRET" not in output
    assert json.loads(output)["reason_code"] == "GOLD_QUOTE_BUILD_FAILED"
    for path in paths:
        connection = duckdb.connect(str(path))
        connection.close()


@pytest.mark.parametrize("pin", ["", "A" * 64, "a" * 63])
def test_bad_pin(tmp_path, pin):
    args = arguments(tmp_path)
    args[-1] = pin
    with pytest.raises(SystemExit):
        cli.main(args)


def test_missing_inputs_no_output_created(tmp_path):
    with pytest.raises(SystemExit):
        cli.main(arguments(tmp_path) + ["--execute", "--initialize", "--code-revision", "head"])
    assert list(tmp_path.iterdir()) == []


def test_input_cannot_be_gold_target_in_plan(tmp_path):
    args = arguments(tmp_path)
    args[9] = args[1]
    with pytest.raises(SystemExit):
        cli.main(args)


def test_explicit_initialization_required(tmp_path):
    inputs(tmp_path)
    with pytest.raises(SystemExit):
        cli.main(arguments(tmp_path) + ["--execute", "--code-revision", "head"])
    assert not (tmp_path / "gold.duckdb").exists()

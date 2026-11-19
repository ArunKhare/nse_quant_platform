"""Explicit publication intent/role/connection boundaries; publisher seam substituted."""

import builtins
import hashlib
import json

import duckdb
import pytest

from nse_quant.data_platform import quote_bundle_publication as publisher
from nse_quant.data_platform import quote_publication_cli as cli


def arguments(tmp_path):
    result = []
    for option, filename in (
        ("bronze-db", "bronze.duckdb"),
        ("frame-silver-db", "frames.duckdb"),
        ("reference-silver-db", "refs.duckdb"),
        ("assessment-db", "assessments.duckdb"),
        ("gold-db", "gold.duckdb"),
        ("staging-db", "staging.duckdb"),
        ("publication-db", "publications.duckdb"),
        ("artifact-root", "artifacts"),
    ):
        result += ["--" + option, str(tmp_path / filename)]
    return result + [
        "--bundle-id",
        "a" * 64,
        "--expected-stage-fingerprint",
        "c" * 64,
        "--purpose",
        "RESEARCH_ONLY",
    ]


def inputs(tmp_path):
    paths = [
        tmp_path / name
        for name in (
            "bronze.duckdb",
            "frames.duckdb",
            "refs.duckdb",
            "assessments.duckdb",
            "gold.duckdb",
            "staging.duckdb",
        )
    ]
    for path in paths:
        connection = duckdb.connect(str(path))
        connection.execute("CREATE TABLE marker (id INTEGER)")
        connection.close()
    return paths


def test_plan_no_execution_imports_or_creation(tmp_path, monkeypatch, capsys):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name in {"duckdb", "nse_quant.data_platform.quote_bundle_publication"}:
            raise AssertionError("Plan imported execution service")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    assert cli.main(arguments(tmp_path)) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["status"] == "PLANNED"
    assert not plan["plan"]["inputs_verified"]
    assert not plan["plan"]["decision_eligibility_asserted"]
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("flag", ["--execute", "--allow-publication"])
def test_both_intent_gates_required_before_io(tmp_path, flag):
    with pytest.raises(SystemExit):
        cli.main(arguments(tmp_path) + [flag])
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("purpose", ["DECISION_READY", "TRADING", ""])
def test_other_purposes_not_supported(tmp_path, purpose):
    args = arguments(tmp_path)
    args[-1] = purpose
    with pytest.raises(SystemExit):
        cli.main(args)


def test_execution_forwards_exact_pins_purpose_and_readonly_inputs(tmp_path, monkeypatch, capsys):
    paths = inputs(tmp_path)
    before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]

    def publish(*connections, **kwargs):
        assert len(connections) == 7
        for connection in connections[:6]:
            assert connection.execute("SELECT count(*) FROM marker").fetchone() == (0,)
            with pytest.raises(duckdb.InvalidInputException):
                connection.execute("INSERT INTO marker VALUES (1)")
        assert kwargs["bundle_id"] == "a" * 64
        assert kwargs["expected_stage_evidence_fingerprint"] == "c" * 64
        assert kwargs["purpose"] == "RESEARCH_ONLY"
        assert kwargs["allow_publication"] is True
        assert kwargs["artifact_root"] == (tmp_path / "artifacts").resolve()
        return {"status": "PUBLISHED_RESEARCH_ONLY", "decision_eligibility_asserted": False}

    monkeypatch.setattr(publisher, "publish_research_quote_bundle", publish)
    args = arguments(tmp_path) + [
        "--execute",
        "--allow-publication",
        "--initialize",
        "--code-revision",
        "head",
    ]
    assert cli.main(args) == 0
    assert not json.loads(capsys.readouterr().out)["decision_eligibility_asserted"]
    assert [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths] == before


def test_exception_redacted_and_input_handles_closed(tmp_path, monkeypatch, capsys):
    paths = inputs(tmp_path)

    def fail(*args, **kwargs):
        raise RuntimeError("SECRET_DETAILS")

    monkeypatch.setattr(publisher, "publish_research_quote_bundle", fail)
    args = arguments(tmp_path) + [
        "--execute",
        "--allow-publication",
        "--initialize",
        "--code-revision",
        "head",
    ]
    assert cli.main(args) == 1
    output = capsys.readouterr().out
    assert "SECRET" not in output
    assert json.loads(output)["reason_code"] == "RESEARCH_PUBLICATION_FAILED"
    for path in paths:
        connection = duckdb.connect(str(path))
        connection.close()


def test_review_stamp_is_mandatory_and_not_guessed(tmp_path):
    args = arguments(tmp_path)
    args[19] = "bad"
    with pytest.raises(SystemExit):
        cli.main(args)

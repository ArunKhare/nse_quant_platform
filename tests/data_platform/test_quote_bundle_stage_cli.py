"""Real CLI/stager SQL/FS execution; only source assembly is substituted."""

import builtins
import hashlib
import json
from dataclasses import asdict, replace

import duckdb
import pytest

from nse_quant.data_platform import feature_bundle as codec
from nse_quant.data_platform import quote_bundle_stage_cli as cli
from nse_quant.data_platform import quote_bundle_staging as service
from nse_quant.data_platform.gold_quote_features import ExactPriceFeature, GoldQuoteCandidate


def bundle():
    candidate = GoldQuoteCandidate(
        "",
        codec.FEATURE_VERSION,
        "a" * 64,
        "b" * 64,
        "candidate",
        "EXACT_PROVIDER_PRICE_FIELDS",
        source_evidence_fingerprint="c" * 64,
        source_association_fingerprint="d" * 64,
        source_frame_revision_id="e" * 64,
        source_packet_ordinal=0,
        reference_assessment_revision_id="f" * 64,
        reference_row_ordinal=0,
        reference_source_fields_hash="a" * 64,
        provider_token=257,
        price_divisor=100,
        features=(ExactPriceFeature("last_price", 12345, 100, "123.45"),),
        quality_flags=("EXCHANGE_EVENT_TIME_UNKNOWN",),
    )
    candidate = replace(
        candidate, build_id=codec.digest(codec.canonical(asdict(candidate)).encode())
    )
    encoded = codec.canonical(asdict(candidate))
    return codec.make_quote_bundle(
        (
            codec.QuoteBundleMember(
                candidate.build_id,
                codec.GOLD_READER_VERSION,
                "b" * 64,
                ("job-1",),
                codec.digest(encoded.encode()),
                encoded,
            ),
        )
    )


def arguments(tmp_path):
    result = []
    for option, filename in (
        ("bronze-db", "bronze.duckdb"),
        ("frame-silver-db", "frames.duckdb"),
        ("reference-silver-db", "references.duckdb"),
        ("assessment-db", "assessments.duckdb"),
        ("gold-db", "gold.duckdb"),
        ("staging-db", "staging.duckdb"),
        ("artifact-root", "artifacts"),
    ):
        result.extend(["--" + option, str(tmp_path / filename)])
    return result + ["--build-id", bundle().members[0].build_id]


def inputs(tmp_path):
    paths = [
        tmp_path / name
        for name in (
            "bronze.duckdb",
            "frames.duckdb",
            "references.duckdb",
            "assessments.duckdb",
            "gold.duckdb",
        )
    ]
    for path in paths:
        connection = duckdb.connect(str(path))
        connection.execute("CREATE TABLE marker (id INTEGER)")
        connection.close()
    return paths


def test_plan_no_execution_imports_or_side_effects(tmp_path, monkeypatch, capsys):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name in {"duckdb", "nse_quant.data_platform.quote_bundle_staging"}:
            raise AssertionError("Plan imported execution dependencies")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    assert cli.main(arguments(tmp_path) + ["--initialize"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "PLANNED"
    assert result["plan"]["publication_requested"] is False
    assert result["plan"]["inputs_verified"] is False
    assert list(tmp_path.iterdir()) == []


def test_execution_real_stager_readonly_sources_and_complete_artifact(
    tmp_path,
    monkeypatch,
    capsys,
):
    paths = inputs(tmp_path)
    hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
    value = bundle()

    def assemble(*connections, build_ids):
        assert build_ids == (value.members[0].build_id,)
        for connection in connections:
            assert connection.execute("SELECT count(*) FROM marker").fetchone() == (0,)
            with pytest.raises(duckdb.InvalidInputException):
                connection.execute("INSERT INTO marker VALUES (1)")
        return value

    monkeypatch.setattr(service, "assemble_quote_bundle", assemble)
    options = arguments(tmp_path) + ["--execute", "--initialize", "--code-revision", "head"]
    assert cli.main(options) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["execution_status"] == "COMMITTED"
    assert result["status"] == "SEALED_NOT_PUBLISHED"
    assert result["published"] is False
    assert (tmp_path / "artifacts" / (value.bundle_id + ".json")).read_bytes() == (
        codec.encode_quote_bundle(value)
    )
    assert [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths] == hashes


def test_execution_failure_redacted_and_handles_closed(tmp_path, monkeypatch, capsys):
    paths = inputs(tmp_path)

    def fail(*args, **kwargs):
        raise RuntimeError("SECRET_DETAILS")

    monkeypatch.setattr(service, "assemble_quote_bundle", fail)
    options = arguments(tmp_path) + ["--execute", "--initialize", "--code-revision", "head"]
    assert cli.main(options) == 1
    output = capsys.readouterr().out
    assert "SECRET" not in output
    assert json.loads(output)["reason_code"] == "BUNDLE_STAGE_FAILED"
    assert not (tmp_path / "artifacts").exists()
    for path in paths:
        connection = duckdb.connect(str(path))
        connection.close()


@pytest.mark.parametrize("pin", ["", "A" * 64, "a" * 63])
def test_invalid_pin(tmp_path, pin):
    args = arguments(tmp_path)
    args[-1] = pin
    with pytest.raises(SystemExit):
        cli.main(args)


def test_duplicate_pins_rejected(tmp_path):
    args = arguments(tmp_path)
    with pytest.raises(SystemExit):
        cli.main(args + ["--build-id", args[-1]])


def test_missing_inputs_never_created(tmp_path):
    with pytest.raises(SystemExit):
        cli.main(arguments(tmp_path) + ["--execute", "--initialize", "--code-revision", "head"])
    assert list(tmp_path.iterdir()) == []


def test_database_inside_artifact_root_rejected_even_in_plan(tmp_path):
    args = arguments(tmp_path)
    args[13] = str(tmp_path)
    with pytest.raises(SystemExit):
        cli.main(args)


def test_explicit_initialization_required(tmp_path):
    inputs(tmp_path)
    with pytest.raises(SystemExit):
        cli.main(arguments(tmp_path) + ["--execute", "--code-revision", "head"])
    assert not (tmp_path / "staging.duckdb").exists()

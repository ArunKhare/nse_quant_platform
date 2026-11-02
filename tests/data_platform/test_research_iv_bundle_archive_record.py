"""Synthetic negative documents and SQL histories; no native numerical success fixture."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, cast

import duckdb
import pytest

from nse_quant.data_platform import research_iv_bundle_archive_record as record
from nse_quant.data_platform import research_iv_bundle_store as store


def negative_case():
    requests = [{"build_id": "a" * 64, "expected_archive_fingerprint": "b" * 64}]
    observed: dict[str, Any] = dict.fromkeys(record.REVALIDATION_FIELDS)
    observed.update({key: False for key in record.FLAGS & record.REVALIDATION_FIELDS})
    observed.update(
        version="research-iv-current-source-revalidation@1",
        **requests[0],
        status="review_required",
        reason_codes=["SYNTHETIC_NEGATIVE_OBSERVATION"],
        archived_recording_verified=False,
        current_source_checked=False,
        exact_recording_reproduced=False,
        archive_unchanged_observed=False,
    )
    value: dict[str, Any] = dict.fromkeys(record.ASSEMBLY_FIELDS)
    value.update({key: False for key in record.FLAGS})
    value.update(
        version=record.ASSEMBLY_VERSION,
        status="review_required",
        requests=requests,
        first_pass=[deepcopy(observed)],
        second_pass=[deepcopy(observed)],
        reason_codes=["IV_BUNDLE_MEMBER_NOT_COMPLETE_IN_BOTH_PASSES"],
        all_members_revalidated=False,
    )
    return record.canonical(requests), value


def test_roundtrip_and_full_negative_bytes_retained():
    requests, value = negative_case()
    raw = record.canonical(value)
    assert record.result_value(raw, requests) == value
    group = record.scope_id(requests, "d" * 64)
    assert record.record_id(group, raw, requests) == record.record_id(group, raw, requests)
    changed = deepcopy(value)
    changed["second_pass"][0]["reason_codes"] = ["LATER_NEGATIVE"]
    assert record.record_id(group, record.canonical(changed), requests) != record.record_id(
        group,
        raw,
        requests,
    )


@pytest.mark.parametrize("field", sorted(record.FLAGS), ids=sorted(record.FLAGS))
def test_authority_escalation_rejected(field):
    requests, value = negative_case()
    value[field] = True
    with pytest.raises(ValueError, match="RESEARCH_CONTRACT"):
        record.result_value(record.canonical(value), requests)


@pytest.mark.parametrize(
    "mutation",
    [
        "version",
        "unknown",
        "missing-pass",
        "reordered-pin",
        "eligible-member",
        "positive-flag",
        "fingerprint",
        "bundle",
        "reason",
        "observation-extra",
    ],
    ids=["version", "extra", "pass", "pin", "authority", "flag", "hash", "bundle", "code", "obs"],
)
def test_malformed_or_partial_negative_not_salvaged(mutation):
    requests, value = negative_case()
    if mutation == "version":
        value["version"] = "unknown@2"
    elif mutation == "unknown":
        value["extra"] = False
    elif mutation == "missing-pass":
        value["second_pass"] = []
    elif mutation == "reordered-pin":
        value["second_pass"][0]["build_id"] = "c" * 64
    elif mutation == "eligible-member":
        value["first_pass"][0]["decision_eligibility_asserted"] = True
    elif mutation == "positive-flag":
        value["all_members_revalidated"] = True
    elif mutation == "fingerprint":
        value["evidence_fingerprint"] = "c" * 64
    elif mutation == "bundle":
        value["bundle"] = {}
    elif mutation == "reason":
        value["reason_codes"] = ["unsafe free text"]
    else:
        value["first_pass"][0]["extra"] = 1
    with pytest.raises(ValueError):
        record.result_value(record.canonical(value), requests)


def test_strict_json_and_bounds(monkeypatch):
    for raw in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}', " {}", "{}\n", "[]x"):
        with pytest.raises(ValueError):
            record.checked(raw, 100)
    for raw in ("", "x" * 101, cast(str, b"{}")):
        with pytest.raises(ValueError):
            record.checked(raw, 100)
    requests, value = negative_case()
    monkeypatch.setattr(record, "MAX_RESULT_BYTES", 1)
    with pytest.raises(ValueError, match="BYTE_LIMIT"):
        record.result_value(record.canonical(value), requests)


def test_requests_are_exact_sorted_unique_and_review_pins_define_scope():
    requests, value = negative_case()
    one = value["requests"][0]
    for items in ([], [one, one], [one] * 65, [dict(one, extra=True)], [dict(one, build_id="bad")]):
        with pytest.raises(ValueError):
            record.requests_value(record.canonical(items))
    changed = record.canonical([dict(one, expected_archive_fingerprint="c" * 64)])
    assert record.scope_id(requests, "d" * 64) != record.scope_id(changed, "d" * 64)


def test_exact_all_prior_links_required():
    record.prior_links('["' + "a" * 64 + '"]', ("a" * 64,))
    for raw in ("[]", record.canonical(["b" * 64]), record.canonical(["a" * 64] * 2)):
        with pytest.raises(ValueError):
            record.prior_links(raw, ("a" * 64,))


@pytest.fixture
def sql_history(tmp_path):
    conn = duckdb.connect(str(tmp_path / "safe-history.duckdb"))
    conn.execute('CREATE SCHEMA "gold"')
    conn.execute('CREATE SCHEMA "medallion_audit"')
    names = {name: store._name(conn, "gold", name) for name in store.DOMAIN_TABLES}
    jobs = store._name(conn, "medallion_audit", "jobs")
    events = store._name(conn, "medallion_audit", "job_events")
    conn.execute(
        f"CREATE TABLE {names[store.DOMAIN_TABLES[2]]} ("
        "build_id VARCHAR,input_id VARCHAR,ordinal INTEGER,feature_version VARCHAR,"
        "definition_hash VARCHAR,requests_json VARCHAR,result_json VARCHAR,"
        "prior_ids_json VARCHAR,first_job_id VARCHAR,recorded_at TIMESTAMPTZ,"
        "event_ts TIMESTAMPTZ,published_at TIMESTAMPTZ)"
    )
    conn.execute(
        f"CREATE TABLE {names[store.DOMAIN_TABLES[3]]} "
        "(job_id VARCHAR,input_id VARCHAR,build_id VARCHAR)"
    )
    conn.execute(
        f"CREATE TABLE {jobs} (job_id VARCHAR,parent_job_id VARCHAR,command_name VARCHAR,"
        "config_hash VARCHAR,created_at TIMESTAMPTZ,actor_id VARCHAR,"
        "code_revision VARCHAR,"
        "scope_ref VARCHAR)"
    )
    conn.execute(
        f"CREATE TABLE {events} "
        "(job_id VARCHAR,event_index INTEGER,state VARCHAR,recorded_at TIMESTAMPTZ,"
        "reason_code VARCHAR)"
    )
    requests, value = negative_case()
    definition = record.sha(store._definition().encode())
    group = record.scope_id(requests, definition)
    clock = datetime(2026, 1, 1, tzinfo=UTC)

    def add(job="origin", changed=False, states=("PLANNED", "RUNNING", "SUCCEEDED"), link=True):
        candidate = deepcopy(value)
        if changed:
            candidate["reason_codes"] = ["SYNTHETIC_LATER_NEGATIVE"]
        raw = record.canonical(candidate)
        key = record.record_id(group, raw, requests)
        table = names[store.DOMAIN_TABLES[2]]
        prior = conn.execute(f"SELECT build_id FROM {table} ORDER BY ordinal").fetchall()
        if key not in [item[0] for item in prior]:
            conn.execute(
                f"INSERT INTO {table} VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                [
                    key,
                    group,
                    len(prior) + 1,
                    store.FEATURE_VERSION,
                    definition,
                    requests,
                    raw,
                    record.canonical([item[0] for item in prior]),
                    job,
                    clock,
                    None,
                    None,
                ],
            )
        conn.execute(
            f"INSERT INTO {jobs} VALUES (?,NULL,?,?,?,?,?,?)",
            [
                job,
                store.COMMAND,
                definition,
                clock,
                "synthetic-actor",
                "synthetic-revision",
                group,
            ],
        )
        for index, state in enumerate(states, 1):
            conn.execute(f"INSERT INTO {events} VALUES (?,?,?,?,NULL)", [job, index, state, clock])
        if link:
            conn.execute(
                f"INSERT INTO {names[store.DOMAIN_TABLES[3]]} VALUES (?,?,?)",
                [job, group, key],
            )
        return key

    key = add()
    yield conn, group, definition, key, add, names, jobs, events
    conn.close()


def test_sql_history_retry_preserves_origin_and_changes_fingerprint(sql_history):
    conn, group, definition, key, add, _, _, _ = sql_history
    rows, fingerprint = store._scope(conn, group, definition)
    assert rows[0][8] == "origin"
    assert add("retry") == key
    retried, changed = store._scope(conn, group, definition)
    assert retried == rows
    assert changed != fingerprint
    new = add("later", changed=True)
    add("old-retry")
    history, _ = store._scope(conn, group, definition)
    assert history[-1][0] == new
    assert history[0] == rows[0]


@pytest.mark.parametrize(
    "states,link",
    [
        (("PLANNED",), False),
        (("PLANNED", "RUNNING"), False),
        (("PLANNED", "RUNNING", "FAILED"), False),
        (("PLANNED", "RUNNING", "SUCCEEDED"), False),
    ],
    ids=["planned", "incomplete", "failed", "unlinked-success"],
)
def test_sql_unlinked_obligations_block_entire_scope(sql_history, states, link):
    conn, group, definition, _, add, _, _, _ = sql_history
    add("unlinked", states=states, link=link)
    with pytest.raises(store.IvBundleArchiveReviewRequired):
        store._scope(conn, group, definition)


@pytest.mark.parametrize(
    "mutation",
    [
        "links",
        "clock",
        "origin",
        "ordinal",
        "event",
        "command",
        "audit-code",
        "orphan-attempt",
    ],
    ids=["links", "time", "origin", "order", "event", "command", "reason", "orphan"],
)
def test_sql_history_tampering_cannot_repair_origin(sql_history, mutation):
    conn, group, definition, _, _, names, jobs, events = sql_history
    table = names[store.DOMAIN_TABLES[2]]
    if mutation == "links":
        conn.execute(f"UPDATE {table} SET prior_ids_json='[1]'")
    elif mutation == "clock":
        conn.execute(f"UPDATE {table} SET published_at=recorded_at")
    elif mutation == "origin":
        conn.execute(f"UPDATE {table} SET first_job_id='missing'")
    elif mutation == "ordinal":
        conn.execute(f"UPDATE {table} SET ordinal=2")
    elif mutation == "event":
        conn.execute(f"UPDATE {events} SET state='FAILED' WHERE event_index=3")
    elif mutation == "command":
        conn.execute(f"UPDATE {jobs} SET command_name='other'")
    elif mutation == "audit-code":
        conn.execute(f"UPDATE {events} SET reason_code='UNEXPECTED' WHERE event_index=3")
    else:
        conn.execute(
            f"INSERT INTO {names[store.DOMAIN_TABLES[3]]} VALUES ('missing',?,?)",
            [
                group,
                "c" * 64,
            ],
        )
    with pytest.raises(ValueError):
        store._scope(conn, group, definition)


def test_sql_budget_checked_before_payload_fetch(sql_history, monkeypatch):
    conn, group, definition, _, _, _, _, _ = sql_history
    monkeypatch.setattr(store, "MAX_SCOPE_BYTES", 1)
    with pytest.raises(store.IvBundleArchiveReviewRequired, match="SCOPE_BYTE_LIMIT"):
        store._scope(conn, group, definition)


def test_aware_instants_convert_not_relabel():
    local = datetime(2026, 1, 1, 5, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    assert store._instant(local) == "2026-01-01T00:00:00+00:00"
    with pytest.raises(ValueError):
        store._instant(datetime(2026, 1, 1))


def test_reader_does_not_initialize(tmp_path):
    conn = duckdb.connect(str(tmp_path / "empty.duckdb"))
    try:
        with pytest.raises(duckdb.Error):
            store.read_research_iv_bundle_archive(conn, build_id_pin="a" * 64)
        assert conn.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_catalog=current_database()"
        ).fetchone() == (0,)
    finally:
        conn.close()


def test_fully_quoted_catalog_alias_uses_safe_physical_filename(tmp_path):
    conn = duckdb.connect()
    safe = str(tmp_path / "safe-alias.duckdb").replace("'", "''")
    alias = 'research"catalog'
    quoted = '"' + alias.replace('"', '""') + '"'
    try:
        conn.execute(f"ATTACH '{safe}' AS {quoted}")
        conn.execute(f"USE {quoted}")
        conn.execute(f'CREATE SCHEMA {quoted}."gold"')
        name = store._name(conn, "gold", "research_iv_bundle_schema_versions")
        conn.execute(f"CREATE TABLE {name} (version INTEGER)")
        conn.execute(f"INSERT INTO {name} VALUES (1)")
        assert conn.execute(f"SELECT version FROM {name}").fetchone() == (1,)
        store._owned(conn)
    finally:
        conn.close()


def test_dedicated_file_target_is_required(tmp_path):
    memory = duckdb.connect()
    try:
        with pytest.raises(ValueError, match="FILE_BACKED"):
            store._owned(memory)
    finally:
        memory.close()
    conn = duckdb.connect(str(tmp_path / "foreign.duckdb"))
    try:
        row = conn.execute("SELECT current_database()").fetchone()
        assert row is not None
        catalog = '"' + str(row[0]).replace('"', '""') + '"'
        conn.execute(f'CREATE TABLE {catalog}."main"."foreign_table" (value INTEGER)')
        with pytest.raises(ValueError, match="DEDICATED"):
            store._owned(conn)
    finally:
        conn.close()

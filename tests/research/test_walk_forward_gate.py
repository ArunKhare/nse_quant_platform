# import sys
# from pathlib import Path
from types import SimpleNamespace

# SCRIPTS = Path(__file__).resolve().parents[2]/"scripts"
# if str(SCRIPTS) not in sys.path:
#     sys.path.insert(0,SCRIPTS)
from scripts.run_walk_forward_backtest import (
    resolve_experiment_permission,
)


def make_settings(*, experiments_enabled: bool):
    return SimpleNamespace(
        research=SimpleNamespace(
            enable_parameter_experiments=experiments_enabled,
        )
    )


def test_unready_run_blocked_without_override():
    settings = make_settings(experiments_enabled=True)
    readiness = {"ready": False}

    allowed, reason = resolve_experiment_permission(
        settings=settings,
        readiness=readiness,
        allow_unready_diagnostic=False,
    )

    assert not allowed
    assert reason == "blocked"


def test_unready_run_allowed_with_diagnostic_override():
    settings = make_settings(experiments_enabled=True)
    readiness = {"ready": False}

    allowed, reason = resolve_experiment_permission(
        settings=settings,
        readiness=readiness,
        allow_unready_diagnostic=True,
    )

    assert allowed
    assert reason == "diagnostic_override"


def test_ready_run_allowed_when_flag_enabled():
    settings = make_settings(experiments_enabled=True)
    readiness = {"ready": True}

    allowed, reason = resolve_experiment_permission(
        settings=settings,
        readiness=readiness,
        allow_unready_diagnostic=False,
    )

    assert allowed
    assert reason == "research_ready"


def test_ready_run_blocked_when_flag_disabled():
    settings = make_settings(experiments_enabled=False)
    readiness = {"ready": True}

    allowed, reason = resolve_experiment_permission(
        settings=settings,
        readiness=readiness,
        allow_unready_diagnostic=False,
    )

    assert not allowed
    assert reason == "blocked"

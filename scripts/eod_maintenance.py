"""Audited eod workflow; defaults to a nonmutating plan."""

from __future__ import annotations

from nse_quant.data_platform.workflow_cli import main as workflow_main
from nse_quant.data_platform.workspace_workflows import (
    build_export_path as build_export_path,
)
from nse_quant.data_platform.workspace_workflows import (
    get_option_stream_count_for_date as get_option_stream_count_for_date,
)


def main(argv: list[str] | None = None) -> int:
    return workflow_main("eod", argv)


if __name__ == "__main__":
    raise SystemExit(main())

"""Audited daily workflow; defaults to a nonmutating plan."""

from __future__ import annotations

from nse_quant.data_platform.workflow_cli import main as workflow_main


def main(argv: list[str] | None = None) -> int:
    return workflow_main("daily", argv)


if __name__ == "__main__":
    raise SystemExit(main())

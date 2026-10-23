from datetime import date

from nse_quant.ops.notifier import Notifier
from nse_quant.persistence.duckdb_store import DuckDBStore


def main() -> int:
    store = DuckDBStore(read_only=True)
    today = date.today().isoformat()

    rows = store.conn.execute(
        """
        SELECT COUNT(DISTINCT CAST(ts AS DATE))
        FROM option_stream
        WHERE underlying = 'NIFTY'
          AND iv IS NOT NULL
          AND CAST(ts AS DATE) = ?
        """,
        [today],
    ).fetchone()
    store.close()

    captured_days = int(rows[0])

    if captured_days == 0:
        Notifier().send(f"NSE Quant: NIFTY IV capture failed for {today}.")
        return 1

    print(f"NIFTY IV capture OK for {today}: {captured_days} day(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

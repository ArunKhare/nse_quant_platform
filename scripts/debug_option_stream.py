from nse_quant.persistence.duckdb_store import DuckDBStore

store = DuckDBStore(read_only=True)

print("Distinct underlying values:")
print(
    store.conn.execute(
        """
        SELECT underlying, COUNT(*) AS rows, MIN(ts) AS first_ts, MAX(ts) AS last_ts
        FROM option_stream
        GROUP BY underlying
        ORDER BY rows DESC
        """
    ).fetchall()
)

print("\nOverall range:")
print(store.conn.execute("SELECT MIN(ts), MAX(ts), COUNT(*) FROM option_stream").fetchone())

store.close()

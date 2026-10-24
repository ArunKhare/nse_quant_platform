from nse_quant.persistence.repositories import PositionRepository


def test_active_kill_switch_blocks_new_paper_orders(decision_loop, test_store):
    store = test_store
    repository = PositionRepository(store.conn)

    before_positions = repository.get_open_strategy_positions()
    before_orders = store.conn.execute("SELECT count(*) FROM orders").fetchone()[0]

    decision_loop.kill_switch.activate("test_kill_switch")

    result = decision_loop.run_once()

    assert result["status"] == "kill_switch_active"

    after_positions = repository.get_open_strategy_positions()
    after_orders = store.conn.execute("SELECT count(*) FROM orders").fetchone()[0]

    assert len(after_positions) == len(before_positions)
    assert after_orders == before_orders


def test_reset_kill_switch_allows_loop_to_resume(decision_loop, test_store):
    decision_loop.kill_switch.activate("test_kill_switch")

    blocked = decision_loop.run_once()
    assert blocked["status"] == "kill_switch_active"

    decision_loop.kill_switch.reset("test_kill_switch")

    result = decision_loop.run_once()

    assert result["status"] != "kill_switch_active"

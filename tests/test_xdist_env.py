"""run pytest -n 4 -s tests/test_xdist_env.py to see the exact environment variables
injected by pytest-xdist.
"""

import os
import time


def test_worker_env_one(worker_id):
    env_worker = os.environ.get("PYTEST_XDIST_WORKER", "master")
    total_workers = os.environ.get("PYTEST_XDIST_WORKER_COUNT", "1")
    print(f"\n[Test 1] Fixture: {worker_id} | Env: {env_worker} | Total Workers: {total_workers}")
    time.sleep(0.5)


def test_worker_env_two(worker_id):
    env_worker = os.environ.get("PYTEST_XDIST_WORKER", "master")
    total_workers = os.environ.get("PYTEST_XDIST_WORKER_COUNT", "1")
    print(f"\n[Test 2] Fixture: {worker_id} | Env: {env_worker} | Total Workers: {total_workers}")
    time.sleep(0.5)

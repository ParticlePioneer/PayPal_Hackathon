"""Real DB/process A5 checks; pending operations simulate unknown outcomes."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
import subprocess
import sys
from threading import Barrier
import time

from backend.domain.tests.test_quotes_postgres import domain, issue, counts, outcome_of


def test_pending_claim_survives_an_actual_new_process_and_expiry(domain):
    quote = issue(domain, ttl=1)
    domain.claim_for_authorization("buyer_1", quote.id, "op_unknown")
    time.sleep(1.1)
    code = """
import json, os
from backend.domain.database import DomainDatabase
from backend.domain.quotes import QuoteAdapter
adapter = QuoteAdapter(DomainDatabase(os.environ['TEST_DATABASE_URL'], schema=os.environ['A5_TEST_SCHEMA']))
recovered = adapter.recover_expired()
quote = adapter.claim_for_authorization('buyer_1', os.environ['A5_TEST_QUOTE'], 'op_unknown')
with adapter.database.transaction() as connection:
    row = connection.execute('SELECT sum(reserved_qty) AS reserved, sum(allocated_qty) AS allocated FROM domain_stock_batches').fetchone()
print(json.dumps({'recovered': recovered, 'state': quote.state, 'reserved': int(row['reserved']), 'allocated': int(row['allocated'])}))
"""
    env = {**os.environ, "A5_TEST_SCHEMA": domain.database.schema, "A5_TEST_QUOTE": quote.id}
    result = subprocess.run([sys.executable, "-B", "-c", code], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, "Separate process could not inspect durable claim"
    assert json.loads(result.stdout) == {"recovered": 0, "state": "claimed", "reserved": 30, "allocated": 0}
    assert counts(domain) == (30, 30, 0)
    domain.commit_allocation("op_unknown")
    assert counts(domain) == (30, 0, 30)


def test_claim_and_expiry_recovery_race_after_deadline_restores_once(domain):
    quote = issue(domain, ttl=1)
    time.sleep(1.1)
    barrier = Barrier(2)
    def recover():
        barrier.wait(timeout=5)
        return domain.recover_expired()
    def claim():
        barrier.wait(timeout=5)
        return outcome_of(lambda: domain.claim_for_authorization("buyer_1", quote.id, "racing_op"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        recovery = pool.submit(recover)
        claimed = pool.submit(claim)
        assert claimed.result(timeout=10) == "expired"
        assert recovery.result(timeout=10) in (0, 1)
    assert counts(domain) == (30, 0, 0)
    assert domain.recover_expired() == 0

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

def test_ignition_runs():
    from lumen_core.ignition import run_ignition
    run_ignition(trials=3)
    # Check chronicle exists and has entries
    import sqlite3
    from lumen_core.config.constants import CHRONICLE_DB_PATH
    assert os.path.exists(CHRONICLE_DB_PATH)
    conn = sqlite3.connect(CHRONICLE_DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    conn.close()
    assert count > 0

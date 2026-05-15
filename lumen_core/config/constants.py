import os
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ACTIVATION_COSINE_SIM_ACCEPT = 0.65
ACTIVATION_COSINE_SIM_REVIEW = 0.30
RISK_SCORE_HARD_REJECT = 0.85
RISK_SCORE_SOFT_REJECT = 0.50
GATE_ENTRY_THRESHOLD = 2
GATE_RECOVERY_THRESHOLD = 9
CHRONICLE_DB_PATH = os.path.join(BASE_DIR, "data", "chronicle", "chronicle.db")
GUARD_LOG_DB = os.environ.get("GUARD_LOG_DB", os.path.join(BASE_DIR, "data", "guardian_audit.db"))
MAX_SANCTUARY_ITEMS = 1000

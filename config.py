"""Paper-only deployment configuration. No wallet credentials are read."""
import os

# This deployment is intentionally paper-only. DOG_MODE and private-key env vars
# are ignored; the live executor is not included in the deployed directory.
MODE = "paper"
LIVE_CONFIRM = False

# ---- user strategy (fractions of original position) ----
R1_MULT = float(os.getenv("R1_MULT", "2.0"))
R1_PCT = float(os.getenv("R1_PCT", "0.50"))
R4_MULT = float(os.getenv("R4_MULT", "3.0"))
R4_PCT = float(os.getenv("R4_PCT", "0.30"))
STOP_MULT = float(os.getenv("STOP_MULT", "0.5"))
TRAIL_START_MULT = float(os.getenv("TRAIL_START", "3.0"))
TRAIL_RETRACE = float(os.getenv("TRAIL_RETRACE", "0.35"))

POLL_SEC = int(os.getenv("POLL_SEC", "20"))
SLIPPAGE_BPS = int(os.getenv("SLIPPAGE_BPS", "100"))

STATE_FILE = os.getenv("STATE_FILE", "state.json")
DASHBOARD_PORT = int(os.getenv("PORT", os.getenv("DASHBOARD_PORT", "5001")))
DASHBOARD_AUTH_FILE = os.getenv(
    "DASHBOARD_AUTH_FILE", os.path.join(os.path.dirname(__file__), ".dashboard_auth")
)
KILL_SWITCH_FILE = os.getenv("KILL_SWITCH_FILE", "/tmp/dog_kill")

# ---- automatic discovery (paper-only) ----
AUTO_BUY = os.getenv("AUTO_BUY", "0") == "1"
VIRTUAL_BANKROLL_USD = float(os.getenv("VIRTUAL_BANKROLL_USD", "100"))
AUTO_TRADE_USD = float(os.getenv("AUTO_TRADE_USD", "10"))
MAX_AUTO_POSITIONS = int(os.getenv("MAX_AUTO_POSITIONS", "5"))
SCAN_INTERVAL_SEC = int(os.getenv("SCAN_INTERVAL_SEC", "900"))
MIN_LIQ_USD = float(os.getenv("MIN_LIQ_USD", "5000"))
MIN_BUYS_24H = int(os.getenv("MIN_BUYS_24H", "20"))
MIN_SELLS_24H = int(os.getenv("MIN_SELLS_24H", "5"))
MAX_PAIR_AGE_H = float(os.getenv("MAX_PAIR_AGE_H", "168"))
TOP10_MAX_PCT = float(os.getenv("TOP10_MAX_PCT", "30"))

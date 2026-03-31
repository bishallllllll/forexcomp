"""
Aggressive Day-1 Competition Bot Configuration
- LLM-integrated decision making
- 2-3% risk per trade (vs 0.5% scout phase)
- 5 concurrent trades (vs 3)
- 0.50 min confidence (vs 0.70 scout)
- Dynamic phase: Aggressive → Rocket (8% return) → Lock-In (15% return, day 5+)
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ============================================================================
# LLM BACKEND (Azure OpenAI or AWS Bedrock)
# ============================================================================

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "azure")  # "azure" | "bedrock"
LLM_TIMEOUT_SECONDS = 5  # Max wait for LLM response
LLM_FALLBACK_ON_TIMEOUT = True  # True: execute TA alone; False: skip trade

# Azure OpenAI Configuration
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", 
                                   "https://your-resource.openai.azure.com/")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY", "")
AZURE_DEPLOYMENT_NAME = "gpt-4o"
AZURE_API_VERSION = "2024-10-21"

# AWS Bedrock Configuration
BEDROCK_REGION = os.getenv("BEDROCK_REGION", "us-east-1")
BEDROCK_MODEL_ID = "anthropic.claude-3-5-sonnet-20241022-v2:0"

# ============================================================================
# PHASE MODEL & RISK
# ============================================================================

PHASE_RISK = {
    "aggressive": 0.020,  # 2.0% risk per trade (Day 1-4)
    "rocket": 0.030,      # 3.0% risk (triggered at 8% return)
    "lock_in": {
        "winning": 0.008,   # 0.8% (protect lead if return >= 15%)
        "behind": 0.025,    # 2.5% (catch up if behind)
    }
}

# Phase transitions
ROCKET_TRIGGER_PCT = 8.0  # Auto-switch to Rocket if return >= 8%
LOCK_IN_TRIGGER_PCT = 15.0  # Switch to Lock-In if return >= 15%
LOCK_IN_MIN_DAY = 5  # Only Lock-In from day 5 onwards

# ============================================================================
# SIGNAL & EXECUTION LIMITS
# ============================================================================

CONFIDENCE_THRESHOLDS = {
    "aggressive": 0.50,
    "rocket": 0.55,
    "lock_in": 0.65,
}

MAX_CONCURRENT_TRADES = 5  # Up from 3
MAX_SAME_PAIR_POSITIONS = 3  # Allow pyramiding
MAX_TOTAL_LOSS_PCT = 0.15  # 15% total DD → emergency halt

# ============================================================================
# RISK SIZING
# ============================================================================

SL_MULTIPLIER = 1.2  # ATR × 1.2 for stop loss (was 1.5, tighter SL → bigger R)
TP_MULTIPLIER = 3.5  # ATR × 3.5 for take profit (was 2.5, let winners run)

CONFIDENCE_MULT_RANGE = (0.75, 1.25)  # Confidence impact on lot size

# ============================================================================
# PARTIAL CLOSE & TRAILING
# ============================================================================

PARTIAL_CLOSE_AT_R = 2.0  # Close 40% at +2.0R (was 1.5R, let it run)
PARTIAL_CLOSE_PERCENT = 0.40  # 40% (was 50%)

TRAIL_AT_R = 3.0  # Start trailing at +3.0R (was 2.0R)
TRAIL_MULTIPLIER = 0.3  # 0.3× ATR trail (was 0.5×, tighter)

BREAK_EVEN_AT_R = 1.2  # Move SL to break-even at +1.2R (was 1.0R)

# ============================================================================
# RE-ENTRY & PYRAMIDING
# ============================================================================

REENTRY_LOT_FACTOR = 0.75  # 75% of original lot (was 0.5×)
MAX_REENTRIES = 2  # Allow 2 re-entries per setup

PYRAMID_LOT_FACTOR = 0.50  # Add 50% of original lot on pyramid
MAX_PYRAMID_ADDS = 2  # Max 2 pyramid additions per position
PYRAMID_TRIGGER_R = 1.5  # Add to winning positions at +1.5R

# ============================================================================
# MARKET ANALYSIS
# ============================================================================

MIN_ATR_VOLATILITY = 2.0  # Pass volatile moves (was 1.5× avg ATR)

# Asian session RSI thresholds (more mean-reversion)
ASIAN_RSI_OVERSOLD = 35  # (was 30)
ASIAN_RSI_OVERBOUGHT = 65  # (was 70)

# London session ADX threshold (more breakouts)
LONDON_ADX_MIN = 20  # (was 25)

# NY Fibonacci bounce confidence
FIB_CONFIDENCE = {
    "38.2": 0.58,
    "50.0": 0.62,
    "61.8": 0.68,
}

# H1 trend bonus
H1_TREND_BONUS = 0.05  # +0.05 confidence if aligns with H1 EMA

# ============================================================================
# NEWS & TIMING
# ============================================================================

NEWS_BLACKOUT_BEFORE_MIN = 10  # (was 15)
NEWS_BLACKOUT_AFTER_MIN = 5  # (was 10)

# ============================================================================
# POLLING & LOG
# ============================================================================

POLL_INTERVAL_SEC = 15  # Faster signal capture (was 30)
LOG_DIR = "data"
LLM_DECISIONS_LOG = f"{LOG_DIR}/llm_decisions.log"

# ============================================================================
# COMPETITION PARAMETERS
# ============================================================================

DEFAULT_TARGET_RETURN_PCT = 30  # Win threshold
DEFAULT_DAYS = 7
DEFAULT_INITIAL_BALANCE = None  # Read from MT5 at runtime

# ============================================================================
# MT5 CONNECTION
# ============================================================================

MT5_TIMEOUT_SEC = 10
MT5_RETRY_COUNT = 3
MT5_RETRY_DELAY_SEC = 2

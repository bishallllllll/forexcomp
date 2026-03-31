# Aggressive Day-1 Competition Bot — Implementation Plan

## Goal

The competition rewards **highest equity at end of week**. This plan **eliminates the Scout phase** and makes the bot **aggressive from Trade 1**, with an **LLM as the final decision-maker** on every signal.

> [!IMPORTANT]
> **Account balance is unknown at design-time.** The bot reads `account_info().balance` from MT5 on startup — no hardcoded value. All risk is sized as % of live equity.

The market analyst trades **every available pair** — majors, minors, exotic crosses, correlated AND non-correlated — for maximum signal volume. Every qualifying TA signal is **sent to the LLM** for a final GO / NO-GO / ADJUST decision before execution.

---

## LLM Architecture

The LLM sits between the **Signal Agent** (TA rules) and the **Execution Agent** (order sender) as the final reasoning layer:

```
MarketAnalyst → SignalAgent → ★ LLMDecisionAgent ★ → ExecutionAgent
      (TA)        (filters)      (GO / NO-GO)           (MT5 orders)
```

**LLM Backend (configurable, one key in `aggressive_config.py`):**

| Provider | Model | When to use |
|---|---|---|
| **Azure OpenAI** | `gpt-4o` | Primary — lowest latency from Azure region |
| **AWS Bedrock** | `anthropic.claude-3-5-sonnet` | Fallback if Azure is unavailable |

The LLM receives a structured JSON prompt every 15 seconds (per-signal) containing:
- Signal: pair, direction, session, confidence, ATR, indicators that fired
- Account state: equity, phase, return %, open positions, daily P&L
- Competition context: days remaining, target return, projected final return
- Recent trade history: last 5 closed trades (W/L, pair, R-multiple)

The LLM responds in structured JSON:
```json
{
  "decision": "EXECUTE" | "SKIP" | "WAIT",
  "confidence_adjustment": -0.15,
  "risk_modifier": 0.8,
  "reasoning": "RSI divergence on H4 contradicts London breakout signal — skip."
}
```

- **EXECUTE**: Signal proceeds to ExecutionAgent with optional adjustments
- **SKIP**: Signal is discarded, no trade placed
- **WAIT**: Signal held for one more cycle (re-evaluated in 15s)
- `risk_modifier` (0.5–1.5): multiplies the RiskGuardian lot size — LLM can size up high-conviction trades

---

## User Review Required

> [!IMPORTANT]
> **Risk per trade is 2.0% of LIVE equity on Day 1, up to 3.0% in Rocket Mode.** Balance is auto-read from MT5 — no manual input needed. The disqualification guard (15% total DD) is still enforced regardless of account size.

> [!WARNING]
> **Max concurrent trades raised from 3 → 5.** More positions = more exposure simultaneously. The emergency close still fires at 15% total drawdown.

> [!CAUTION]
> **Confidence threshold lowered to 0.50 (from 0.70 Scout).** This accepts more marginal setups for volume. It is controlled by the Risk Guardian's lot-sizing formula — lower confidence = smaller lot.

---

## Proposed Changes

All new files are written to `/home/monarch/forexagenticcomp/`. The existing `/home/monarch/forex agentic/` codebase is **not modified** — this is a standalone aggressive fork.

---

### Config Layer

#### [NEW] [aggressive_config.py](file:///home/monarch/forexagenticcomp/config/aggressive_config.py)

LLM backend config added:
```python
LLM_PROVIDER = "azure"          # "azure" | "bedrock"
LLM_TIMEOUT_SECONDS = 5         # Max wait for LLM — skip if exceeded, TA alone decides
LLM_FALLBACK_ON_TIMEOUT = True  # If True: execute TA signal; if False: skip trade

# Azure OpenAI
AZURE_OPENAI_ENDPOINT = "https://<your-resource>.openai.azure.com/"
AZURE_OPENAI_KEY      = "<from env: AZURE_OPENAI_KEY>"
AZURE_DEPLOYMENT_NAME = "gpt-4o"

# AWS Bedrock
BEDROCK_REGION        = "us-east-1"
BEDROCK_MODEL_ID      = "anthropic.claude-3-5-sonnet-20241022-v2:0"
```

Key changes vs existing `competition_config.py`:

| Parameter | Old (Conservative) | New (Aggressive) |
|---|---|---|
| Phase model | Scout/Accumulate/Secure | **Aggressive/Rocket/Lock-In** |
| Day 1 risk/trade | 0.5% | **2.0%** |
| Max concurrent trades | 3 | **5** |
| Min confidence | 0.70 (Scout) | **0.50** |
| Re-entry lot factor | 0.5× | **0.75×** (more re-entries) |
| Partial close at | +1.5R | **+2.0R** (let winners run longer) |
| Trail at | +2.0R | **+3.0R** |
| SL multiplier | 1.5× ATR | **1.2× ATR** (tighter SL = bigger R multiple) |
| TP multiplier | 2.5× ATR | **3.5× ATR** (bigger reward) |

New phase model:
- **Aggressive** (Days 1–4): 2.0% risk/trade, chase every A/B-grade setup
- **Rocket** (auto-activates if return ≥ 8% by Day 3): 3.0% risk — double-down when winning
- **Lock-In** (Day 5–7 if return ≥ 15%): Drop to 0.8% to protect the lead; stays Aggressive if behind

---

### Competition Coordinator

#### [NEW] [competition_coordinator.py](file:///home/monarch/forexagenticcomp/src/competition_coordinator.py)

Changes vs existing:
- **Phase resolver uses Aggressive/Rocket/Lock-In** — no more Scout
- Adds `_check_rocket_mode_activation()`: if `current_return_pct ≥ ROCKET_TRIGGER_PCT` → switch to Rocket
- Poll interval reduced from **30s → 15s** for faster signal capture
- Agent tick order: `MarketAnalyst → SignalAgent → LLMDecisionAgent → RiskGuardian → ExecutionAgent → PerformanceTracker`
- **LLM reasoning logged** to `data/llm_decisions.log` for every trade

---

### Market Analyst Agent

#### [NEW] [market_analyst_agent.py](file:///home/monarch/forexagenticcomp/src/market_analyst_agent.py)

All available pairs are traded across every session — correlated AND non-correlated — for maximum signal volume:

```python
SESSIONS = {
    "asian": {
        "pairs": [
            # Yen pairs (highly liquid in Asia)
            "USDJPY", "EURJPY", "GBPJPY", "AUDJPY", "CADJPY", "NZDJPY", "CHFJPY",
            # Antipodean pairs
            "AUDUSD", "NZDUSD", "AUDNZD", "AUDCAD", "AUDCHF",
            # Asian-hour USD crosses
            "USDCAD", "USDCHF",
        ],
        "style": "mean_reversion",   # BB+RSI fade
    },
    "london": {
        "pairs": [
            # EUR bloc
            "EURUSD", "EURGBP", "EURJPY", "EURCHF", "EURCAD", "EURAUD", "EURNZD",
            # GBP bloc (highest pip range)
            "GBPUSD", "GBPJPY", "GBPCAD", "GBPAUD", "GBPNZD", "GBPCHF",
            # CHF/USD
            "USDCHF", "USDCAD",
        ],
        "style": "breakout_momentum",  # EMA cross + MACD + ADX
    },
    "ny": {
        "pairs": [
            # USD bloc
            "EURUSD", "GBPUSD", "USDCAD", "USDCHF", "USDJPY",
            # Commodity pairs
            "AUDUSD", "NZDUSD",
            # Metals/indices (highest range for competition)
            "XAUUSD",   # Gold — top competition pick
            "XAGUSD",   # Silver
            # Non-correlated crosses
            "AUDCAD", "NZDCAD", "CADCHF",
        ],
        "style": "trend_continuation",  # Fib retracement + RSI
    },
}
```

Other signal changes:
- **Lower ATR volatility filter**: 1.5× → **2.0×** avg ATR (pass volatile moves)
- **Asian RSI thresholds**: 35/65 (from 30/70) — more mean-reversion triggers
- **London ADX threshold**: 20 (from 25) — more breakouts qualify
- **NY Fib**: Accept 38.2% + 50% + 61.8% bounces (confidence 0.58 / 0.62 / 0.68)
- **H1 trend bonus**: +0.05 confidence if signal aligns with H1 EMA direction

---

### Aggressive Risk Guardian

#### [NEW] [aggressive_risk_guardian.py](file:///home/monarch/forexagenticcomp/src/aggressive_risk_guardian.py)

Changes vs existing `CompetitionRiskGuard`:

```python
PHASE_RISK = {
    "aggressive": 0.020,  # 2.0% per trade — on from Day 1
    "rocket":     0.030,  # 3.0% — auto-activates when return ≥ 8%
    "lock_in": {
        "winning": 0.008,  # 0.8% — protect the lead
        "behind":  0.025,  # 2.5% — catch-up mode
    }
}
```

- `compute_lot_size()`: SL distance = **1.2× ATR** (tighter than 1.5×), giving larger R multiples
- `confidence_multiplier`: Range expanded to `0.75 → 1.25` (was 0.8 → 1.16)
- Hard guardrails unchanged: total DD ≥ 15% → emergency halt

---

### Aggressive Signal Agent

#### [NEW] [aggressive_signal_agent.py](file:///home/monarch/forexagenticcomp/src/aggressive_signal_agent.py)

Changes vs existing `SignalAgent`:

```python
CONFIDENCE_THRESHOLDS = {
    "aggressive": 0.50,   # Accept B+ setups; LLM is the final quality gate
    "rocket":     0.55,
    "lock_in":    0.65,
}
```

- **Max concurrent trades: 5** (from 3)
- **Max same-pair positions: 3** — allows pyramiding
- **News blackout**: 10 min before / 5 min after (was 15/10)
- Re-entry: allowed **twice** per setup
- If `pending_signal` passes all filters → written to `state["llm_pending"]` for the LLMDecisionAgent (not `pending_signal` directly)

---

### LLM Decision Agent ⭐

#### [NEW] [llm_decision_agent.py](file:///home/monarch/forexagenticcomp/src/llm_decision_agent.py)

The **central intelligence layer**. This is the only agent that calls an external LLM.

**Flow per cycle:**
1. Read `state["llm_pending"]` — exit if empty
2. Build context prompt (signal + account + history)
3. Call Azure OpenAI or AWS Bedrock (configurable via `LLM_PROVIDER`)
4. Parse JSON response (`decision`, `confidence_adjustment`, `risk_modifier`, `reasoning`)
5. If `EXECUTE`: apply adjustments and write to `state["pending_signal"]` for coordinator dispatch
6. If `SKIP` or `WAIT`: clear `llm_pending`, log reason
7. If **timeout** (> `LLM_TIMEOUT_SECONDS`): apply `LLM_FALLBACK_ON_TIMEOUT` policy

**Prompt template:**
```
You are an expert forex trader competing in a 7-day broker competition.
Goal: maximize equity by end of week.
Current phase: {phase} | Return: {return_pct}% | Days left: {days_remaining}
Equity: {equity} | Open positions: {open_count}
Proposed signal: {direction} {pair} [{session}] confidence={confidence}
Indicators: {indicator_summary}
Last 5 trades: {recent_trades}

Respond ONLY with JSON:
{"decision":"EXECUTE|SKIP|WAIT","confidence_adjustment":0.0,"risk_modifier":1.0,"reasoning":"..."}
```

**Azure call (primary):**
```python
from openai import AzureOpenAI
client = AzureOpenAI(azure_endpoint=cfg.AZURE_OPENAI_ENDPOINT,
                     api_key=os.environ["AZURE_OPENAI_KEY"],
                     api_version="2024-10-21")
```

**AWS Bedrock call (fallback):**
```python
import boto3, json
br = boto3.client("bedrock-runtime", region_name=cfg.BEDROCK_REGION)
body = json.dumps({"anthropic_version":"bedrock-2023-05-31",
                   "max_tokens":256, "messages":[{"role":"user","content":prompt}]})
br.invoke_model(modelId=cfg.BEDROCK_MODEL_ID, body=body)
```

---

### Aggressive Execution Agent

#### [NEW] [aggressive_execution_agent.py](file:///home/monarch/forexagenticcomp/src/aggressive_execution_agent.py)

Changes vs existing `CompetitionExecutionAgent`:

- **TP multiplier: 3.5× ATR** (was 2.5×) — let winners run
- **Partial close at +2.0R** (was 1.5R) — close 40% (was 50%) to keep more running
- **Trail at +3.0R** using 0.3× ATR trail (was 0.5× — tighter trail)
- **Break-even at +1.2R** (was +1.0R)
- **Pyramid adds**: If a trade is at +1.5R and a new same-direction signal fires on the same pair, add 50% of original lot (max 2 pyramid adds per position)

---

### Performance Tracker

#### [NEW] [performance_tracker.py](file:///home/monarch/forexagenticcomp/src/performance_tracker.py)

Port from existing with one addition:
- `get_leaderboard_projection()`: models what return is needed to win, triggers Rocket mode check

---

### Support Files (Direct Ports)

#### [NEW] [mt5_connection.py](file:///home/monarch/forexagenticcomp/src/mt5_connection.py)
Port unchanged from `/home/monarch/forex agentic/src/mt5_connection.py`.

#### [NEW] [news_filter.py](file:///home/monarch/forexagenticcomp/src/news_filter.py)
Port unchanged (already optimized).

---

### Main Entry Point

#### [NEW] [competition_main.py](file:///home/monarch/forexagenticcomp/src/competition_main.py)

```bash
# Set LLM credentials before launch
export AZURE_OPENAI_KEY="your-key-here"     # for Azure
export AWS_PROFILE="your-aws-profile"       # for Bedrock

# Launch
python src/competition_main.py --target 30 --days 7 --llm azure
```

- **No `--balance` flag** — auto-read from MT5
- `--llm azure|bedrock` — selects LLM backend (default: `azure`)
- Agent tick order: `analyst → signal → llm_decision → risk → executor → tracker`
- Poll interval: **15 seconds**

**Dependencies to install:**
```bash
pip install openai boto3 MetaTrader5 pandas numpy requests
```

---

## Verification Plan

### Existing Tests (Port + Extend)

Two test files exist in `/home/monarch/forex agentic/tests/`:
- `test_competition_risk.py` — tests lot sizing, disqualification guard, phase transitions
- `test_signal_agent.py` — tests confidence filter, news blackout, concurrent limit

These will be **ported and updated** for the new aggressive parameters.

### New Automated Tests

```bash
cd /home/monarch/forexagenticcomp
python -m pytest tests/ -v
```

#### `tests/test_aggressive_risk.py`
- `test_day1_risk_is_2pct()` — Scout phase gone, first trade risks 2%
- `test_rocket_mode_activates_at_8pct_return()`
- `test_lock_in_triggers_at_15pct_return_day5()`
- `test_disqualification_guard_at_15pct_loss()`
- `test_lot_size_scales_with_confidence()`
- `test_llm_risk_modifier_scales_lot()` — modifier 1.5 → 50% bigger lot

#### `tests/test_aggressive_signal.py`
- `test_signal_goes_to_llm_pending_not_pending_signal()`
- `test_5_concurrent_trades_allowed()`
- `test_6th_trade_blocked()`
- `test_reentry_allowed_twice()`

#### `tests/test_llm_decision_agent.py`
- `test_execute_decision_writes_pending_signal()` — mock LLM returns EXECUTE
- `test_skip_decision_clears_llm_pending()` — mock LLM returns SKIP
- `test_llm_timeout_uses_fallback_policy()` — mock timeout → fallback to TA
- `test_confidence_adjustment_applied()` — LLM adj -0.1 → final conf lowered
- `test_azure_to_bedrock_failover()` — Azure raises → Bedrock called

### Manual Verification (Paper Account Dry-Run)

1. Set env vars: `export AZURE_OPENAI_KEY=...`
2. Run: `python src/competition_main.py --target 30 --days 7 --llm azure`
3. Watch `data/llm_decisions.log` — confirm LLM reasoning appears per signal
4. Verify first trade: phase=`AGGRESSIVE`, risk≈2% of balance
5. Test timeout fallback: set `LLM_TIMEOUT_SECONDS=0.001`, confirm TA signal still executes
6. Test disqualification guard: set `MAX_TOTAL_LOSS_PCT=0.001`, confirm emergency close fires

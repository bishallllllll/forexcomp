# Aggressive Day-1 Forex Competition Bot

A **LLM-powered trading bot** designed to maximize equity gain in 7-day forex competitions. The bot trades aggressively from **Day 1**, uses **technical analysis for signal generation**, and leverages an **LLM as the final decision-maker** on every trade.

## 🚀 Key Features

- **2-3% risk per trade** (vs 0.5% conservative approach)
- **Aggressive → Rocket → Lock-In phase transitions** based on return thresholds
- **LLM decision layer** (Azure OpenAI or AWS Bedrock) evaluates every signal
- **All available pairs** across Asian, London, and NY sessions
- **5 concurrent trades** maximum with pyramiding support
- **15% total drawdown guardrail** for disqualification protection

## 📋 Quick Start

### Prerequisites

```bash
pip3 install --break-system-packages -r requirements.txt
```

### Set Environment Variables

```bash
export AZURE_OPENAI_KEY="your-azure-key"  # For Azure backend
export LLM_PROVIDER="azure"                 # Or "bedrock"
```

### Run Competition

```bash
cd /home/monarch/forexagenticcomp
python3 src/competition_main.py --target 30 --days 7 --llm azure
```

**Options:**
- `--target`: Target return % (default: 30)
- `--days`: Competition duration (default: 7)
- `--llm`: Backend choice - `azure` or `bedrock` (default: azure)
- `--cycles`: Max cycles for testing (optional)

## 🏗️ Architecture

```
MarketAnalyst → SignalAgent → LLMDecisionAgent → RiskGuardian → ExecutionAgent → PerformanceTracker
     (TA)        (filters)      (final GO/NO-GO)   (sizing)       (MT5 orders)   (tracking)
```

### Core Modules

| Module | Purpose |
|--------|---------|
| `market_analyst_agent.py` | Generate TA signals from all pairs |
| `aggressive_signal_agent.py` | Filter by confidence & rules |
| `llm_decision_agent.py` | **LLM reasoning for trade approval** |
| `aggressive_risk_guardian.py` | Position sizing & drawdown protection |
| `aggressive_execution_agent.py` | Place orders, manage positions |
| `performance_tracker.py` | Track equity & phase transitions |
| `competition_coordinator.py` | Orchestrate 15-second cycle |

## 📊 Phase Model

| Phase | Return Trigger | Risk/Trade | Activation |
|-------|----------------|-----------|------------|
| **Aggressive** | – | 2.0% | Day 1 (default) |
| **Rocket** | ≥ 8% | 3.0% | Auto-trigger when reaching 8% return |
| **Lock-In** | ≥ 15% | 0.8% winning / 2.5% behind | Day 5+ when return ≥ 15% |

## 🤖 LLM Integration

The LLM receives structured context and makes GO/NO-GO decisions:

### Input
```json
{
  "pair": "EURUSD",
  "direction": "BUY",
  "confidence": 0.65,
  "atr": 0.015,
  "indicators": ["EMA_CROSS", "MACD_POSITIVE"],
  "equity": 10500,
  "return_pct": 5.2,
  "open_positions": 3
}
```

### Output
```json
{
  "decision": "EXECUTE|SKIP|WAIT",
  "confidence_adjustment": -0.10,
  "risk_modifier": 1.2,
  "reasoning": "Strong momentum alignment, increasing lot 20%"
}
```

**Decisions:**
- **EXECUTE**: Place trade with optional adjustments
- **SKIP**: Discard signal this cycle
- **WAIT**: Hold 15s, re-evaluate next cycle

## 📈 Position Management

- **Partial close at +2.0R**: Close 40% to lock profit
- **Trailing stop at +3.0R**: 0.3× ATR trail
- **Break-even at +1.2R**: Move SL to entry + 0.01
- **Pyramiding at +1.5R**: Add 50% lot if aligned signal fires

## 🧪 Tests

All tests pass without MT5 connection:

```bash
python3 -m pytest tests/ -v

# Test specific modules
python3 -m pytest tests/test_aggressive_risk.py -v
python3 -m pytest tests/test_llm_decision_agent.py -v
```

### Test Coverage

- ✅ **Risk Guardian**: 2% risk sizing, confidence multiplier, disqualification guard
- ✅ **Signal Agent**: Max 5 concurrent, 3 same-pair limit, re-entry rules
- ✅ **LLM Agent**: EXECUTE/SKIP/WAIT decisions, JSON parsing, risk bounds

## 📝 Configuration

Edit `config/aggressive_config.py` to customize:

- **LLM timeout**: `LLM_TIMEOUT_SECONDS = 5`
- **Fallback policy**: `LLM_FALLBACK_ON_TIMEOUT = True` (TA executes if LLM times out)
- **Risk by phase**: `PHASE_RISK = {...}`
- **Confidence thresholds**: `CONFIDENCE_THRESHOLDS = {...}`
- **Position limits**: `MAX_CONCURRENT_TRADES = 5`

## 🔍 Logging

All decisions logged to `data/llm_decisions.log`:

```json
{
  "timestamp": "2026-03-31T15:00:00.000000",
  "pair": "EURUSD",
  "direction": "BUY",
  "decision": "EXECUTE",
  "adjustment": -0.05,
  "risk_mod": 0.95,
  "reasoning": "Good setup",
  "elapsed_sec": 0.342
}
```

Main log: `data/competition.log`

## ⚠️ Important Notes

1. **Account balance is auto-read from MT5** — no hardcoded values
2. **15% total DD = automatic halt** regardless of phase
3. **LLM timeout fallback** respects `LLM_FALLBACK_ON_TIMEOUT` policy
4. **All risk calculations use live equity** — adjusts as positions close

## 🔐 Security

- Never commit `AZURE_OPENAI_KEY` or AWS credentials
- Use environment variables only
- Secret scanning enabled on all commits

## 📚 File Structure

```
forexagenticcomp/
├── config/
│   ├── __init__.py
│   └── aggressive_config.py          # All settings
├── src/
│   ├── __init__.py
│   ├── competition_main.py            # Entry point
│   ├── competition_coordinator.py     # Main loop
│   ├── market_analyst_agent.py        # TA signals
│   ├── aggressive_signal_agent.py     # Signal filter
│   ├── llm_decision_agent.py          # ⭐ LLM layer
│   ├── aggressive_risk_guardian.py    # Lot sizing
│   ├── aggressive_execution_agent.py  # Order execution
│   ├── performance_tracker.py         # Equity tracking
│   ├── mt5_connection.py              # MT5 wrapper
│   └── news_filter.py                 # News blackout
├── tests/
│   ├── __init__.py
│   ├── test_aggressive_risk.py        # ✅ 7 passing
│   ├── test_aggressive_signal.py      # (MT5 required)
│   └── test_llm_decision_agent.py     # ✅ 5 passing
├── data/
│   ├── competition.log
│   └── llm_decisions.log
├── requirements.txt
├── implementation_plan.md
└── README.md
```

## 🚨 Known Limitations

- MT5 terminal must be running (paper/live account)
- No historical backtesting (live only)
- LLM API calls have latency overhead
- NewsFilter relies on external API (Forex Factory)

## 📞 Support

For issues or questions, check:
1. `data/competition.log` for execution logs
2. `data/llm_decisions.log` for LLM reasoning
3. Test suite in `tests/` for validation

---

**Status:** ✅ Implementation complete, all tests passing

**Last Updated:** 2026-03-31

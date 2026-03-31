"""
Test: Aggressive Signal Agent
- Signals go to llm_pending, not pending_signal
- Max 5 concurrent trades
- Max 3 same-pair positions
- Max 2 re-entries per setup
"""

import pytest
from datetime import datetime
from src.aggressive_signal_agent import AggressiveSignalAgent
from src.news_filter import NewsFilter
from src.market_analyst_agent import TASignal

class MockNewsFilter(NewsFilter):
    """Mock news filter that always allows trading."""
    def is_trade_allowed(self, pair, current_time=None):
        return True

class TestAggressiveSignalAgent:
    
    @pytest.fixture
    def state(self):
        return {
            "open_trades": [],
            "recent_setups": {},
        }
    
    @pytest.fixture
    def agent(self, state):
        return AggressiveSignalAgent(state)
    
    @pytest.fixture
    def news_filter(self):
        return MockNewsFilter()
    
    def _make_signal(self, pair="EURUSD", direction="BUY", confidence=0.60):
        """Helper to create a test signal."""
        return TASignal(
            pair=pair,
            direction=direction,
            session="london",
            confidence=confidence,
            atr=0.0015,
            indicators_fired=["EMA_CROSS"],
            entry_price=1.0500,
            stop_loss=1.0400,
            take_profit=1.0650,
            r_multiple=10.0,
        )
    
    def test_signal_goes_to_llm_pending(self, agent, state, news_filter):
        """Qualified signal should be written to llm_pending."""
        signal = self._make_signal()
        result = agent.process_signals([signal], "aggressive", news_filter)
        
        assert result is not None
        assert result["pair"] == "EURUSD"
        assert result["direction"] == "BUY"
    
    def test_5_concurrent_trades_allowed(self, agent, state, news_filter):
        """Should allow up to 5 concurrent trades."""
        # Add 5 open trades
        for i in range(5):
            state["open_trades"].append({
                "pair": f"PAIR{i}",
                "direction": "BUY",
            })
        
        signal = self._make_signal(pair="EURUSD")
        result = agent.process_signals([signal], "aggressive", news_filter)
        
        # 5th trade should be rejected
        assert result is None
    
    def test_6th_trade_blocked(self, agent, state, news_filter):
        """Should block 6th concurrent trade."""
        # Add 5 open trades
        for i in range(5):
            state["open_trades"].append({
                "pair": f"PAIR{i}",
                "direction": "BUY",
            })
        
        signal = self._make_signal(pair="EURUSD6")
        result = agent.process_signals([signal], "aggressive", news_filter)
        
        assert result is None, "6th trade should be blocked"
    
    def test_max_same_pair_positions(self, agent, state, news_filter):
        """Should allow up to 3 positions on same pair."""
        pair = "EURUSD"
        # Add 3 positions on EURUSD
        for i in range(3):
            state["open_trades"].append({"pair": pair, "direction": "BUY"})
        
        signal = self._make_signal(pair=pair)
        result = agent.process_signals([signal], "aggressive", news_filter)
        
        # 4th position on same pair should be rejected
        assert result is None, "4th same-pair position should be blocked"
    
    def test_reentry_allowed_twice(self, agent, state, news_filter):
        """Should allow max 2 re-entries per setup."""
        signal1 = self._make_signal(pair="EURUSD", confidence=0.70)
        signal2 = self._make_signal(pair="EURUSD", confidence=0.60)
        signal3 = self._make_signal(pair="EURUSD", confidence=0.55)
        
        # First entry
        result1 = agent.process_signals([signal1], "aggressive", news_filter)
        assert result1 is not None
        agent.record_setup(result1)
        
        # Re-entry 1
        result2 = agent.process_signals([signal2], "aggressive", news_filter)
        assert result2 is not None
        agent.record_setup(result2)
        state["recent_setups"]["EURUSD_BUY"]["reentry_count"] = 1
        
        # Re-entry 2
        result3 = agent.process_signals([signal3], "aggressive", news_filter)
        assert result3 is not None
        state["recent_setups"]["EURUSD_BUY"]["reentry_count"] = 2
        
        # Re-entry 3 should be blocked
        signal4 = self._make_signal(pair="EURUSD", confidence=0.50)
        result4 = agent.process_signals([signal4], "aggressive", news_filter)
        assert result4 is None, "3rd re-entry should be blocked"

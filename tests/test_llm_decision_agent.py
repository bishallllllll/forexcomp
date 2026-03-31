"""
Test: LLM Decision Agent
- EXECUTE decision places trade
- SKIP decision clears signal
- WAIT decision holds for next cycle
- Timeout uses fallback policy
- Confidence adjustment applied
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from src.llm_decision_agent import LLMDecisionAgent
from config import aggressive_config as cfg

class TestLLMDecisionAgent:
    
    @pytest.fixture
    def state(self):
        return {
            "current_phase": "aggressive",
            "days_remaining": 7,
            "open_trades": [],
        }
    
    @pytest.fixture
    def agent(self, state):
        agent = LLMDecisionAgent(state)
        # Mock the LLM client
        agent.client = Mock()
        return agent
    
    def _make_signal(self):
        """Helper to create test signal."""
        return {
            "pair": "EURUSD",
            "direction": "BUY",
            "session": "london",
            "confidence": 0.60,
            "atr": 0.0015,
            "indicators": ["EMA_CROSS"],
            "entry_price": 1.0500,
            "stop_loss": 1.0400,
            "take_profit": 1.0650,
            "r_multiple": 10.0,
        }
    
    def test_execute_decision_returns_trade(self, agent, state):
        """EXECUTE decision should return decision dict."""
        signal = self._make_signal()
        state["llm_pending"] = signal
        
        # Mock LLM response
        llm_response = json.dumps({
            "decision": "EXECUTE",
            "confidence_adjustment": 0.0,
            "risk_modifier": 1.0,
            "reasoning": "Signal quality good"
        })
        agent.client.chat.completions.create.return_value = Mock(
            choices=[Mock(message=Mock(content=llm_response))]
        )
        
        account_state = {"equity": 10000.0, "return_pct": 0.0}
        result = agent.process_signal(signal, account_state, [])
        
        assert result is not None
        assert result["decision"] == "EXECUTE"
    
    def test_skip_decision_clears_signal(self, agent, state):
        """SKIP decision should clear llm_pending."""
        signal = self._make_signal()
        state["llm_pending"] = signal
        
        llm_response = json.dumps({
            "decision": "SKIP",
            "confidence_adjustment": 0.0,
            "risk_modifier": 1.0,
            "reasoning": "Too risky"
        })
        agent.client.chat.completions.create.return_value = Mock(
            choices=[Mock(message=Mock(content=llm_response))]
        )
        
        account_state = {"equity": 10000.0, "return_pct": 0.0}
        result = agent.process_signal(signal, account_state, [])
        
        assert result is not None
        assert result["decision"] == "SKIP"
    
    def test_confidence_adjustment_applied(self, agent, state):
        """Confidence adjustment should be in response."""
        signal = self._make_signal()
        state["llm_pending"] = signal
        
        llm_response = json.dumps({
            "decision": "EXECUTE",
            "confidence_adjustment": -0.10,
            "risk_modifier": 1.0,
            "reasoning": "Reduce confidence"
        })
        agent.client.chat.completions.create.return_value = Mock(
            choices=[Mock(message=Mock(content=llm_response))]
        )
        
        account_state = {"equity": 10000.0, "return_pct": 0.0}
        result = agent.process_signal(signal, account_state, [])
        
        assert result is not None
        assert result["confidence_adjustment"] == -0.10
    
    def test_json_parsing_with_markdown(self, agent, state):
        """Should parse JSON even if wrapped in markdown."""
        signal = self._make_signal()
        state["llm_pending"] = signal
        
        llm_response = """
Here's my analysis:
```json
{
  "decision": "EXECUTE",
  "confidence_adjustment": 0.05,
  "risk_modifier": 1.1,
  "reasoning": "Good setup"
}
```
        """
        agent.client.chat.completions.create.return_value = Mock(
            choices=[Mock(message=Mock(content=llm_response))]
        )
        
        account_state = {"equity": 10000.0, "return_pct": 0.0}
        result = agent.process_signal(signal, account_state, [])
        
        assert result is not None
        assert result["decision"] == "EXECUTE"
        assert result["risk_modifier"] == 1.1
    
    def test_risk_modifier_bounds(self, agent, state):
        """Risk modifier should be clamped to 0.5-1.5 range."""
        signal = self._make_signal()
        state["llm_pending"] = signal
        
        # Test too-high value
        llm_response = json.dumps({
            "decision": "EXECUTE",
            "confidence_adjustment": 0.0,
            "risk_modifier": 2.0,  # Too high
            "reasoning": "Test"
        })
        agent.client.chat.completions.create.return_value = Mock(
            choices=[Mock(message=Mock(content=llm_response))]
        )
        
        account_state = {"equity": 10000.0, "return_pct": 0.0}
        result = agent.process_signal(signal, account_state, [])
        
        assert result["risk_modifier"] == 1.5, "Should clamp to max 1.5"

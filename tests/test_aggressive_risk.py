"""
Test: Aggressive Risk Guardian
- Day 1 risk is 2%, not 0.5%
- Rocket mode at 8% return
- Lock-In at 15% return
- Disqualification at 15% loss
"""

import pytest
from src.aggressive_risk_guardian import AggressiveRiskGuardian
from config import aggressive_config as cfg

class TestAggressiveRiskGuardian:
    
    @pytest.fixture
    def state(self):
        return {
            "initial_balance": 10000.0,
            "current_phase": "aggressive",
            "open_trades": [],
        }
    
    @pytest.fixture
    def guardian(self, state):
        return AggressiveRiskGuardian(state)
    
    def test_day1_risk_is_2pct(self, guardian, state):
        """First trade should risk close to 2% of balance."""
        account_state = {"equity": 10000.0}
        signal = {
            "pair": "EURUSD",
            "direction": "BUY",
            "confidence": 0.60,
            "atr": 0.10,  # Large ATR to avoid guardrail (10k * 2% / (0.10 * 1.2) = 1667)
            "entry_price": 1.0500,
            "stop_loss": 1.0400,
            "take_profit": 1.0650,
        }
        
        lot = guardian.compute_lot_size(signal, account_state)
        # Risk = lot * SL distance
        sl_dist = signal["atr"] * 1.2
        risk_amount = lot * sl_dist
        risk_pct = risk_amount / account_state["equity"]
        
        # With 2% risk phase setting and confidence mult ~0.85,
        # actual risk should be ~1.7%
        assert 0.015 < risk_pct < 0.025, f"Risk {risk_pct:.2%} not in range (should be ~2%)"
    
    def test_confidence_multiplier_0_50(self, guardian):
        """At 0.50 confidence, multiplier should be ~0.75."""
        mult = guardian._calculate_confidence_multiplier(0.50)
        assert 0.74 < mult < 0.76
    
    def test_confidence_multiplier_1_00(self, guardian):
        """At 1.00 confidence, multiplier should be ~1.25."""
        mult = guardian._calculate_confidence_multiplier(1.00)
        assert 1.24 < mult < 1.26
    
    def test_disqualification_at_15pct_loss(self, guardian, state):
        """At 15% loss, should be disqualified."""
        account_state = {"equity": 8500.0}  # 15% loss from 10k
        disq = guardian.check_disqualification(account_state)
        assert disq is True
    
    def test_no_disqualification_at_14pct_loss(self, guardian, state):
        """At 14% loss, should not be disqualified."""
        account_state = {"equity": 8600.0}  # 14% loss
        disq = guardian.check_disqualification(account_state)
        assert disq is False
    
    def test_lot_size_scales_with_confidence(self, guardian, state):
        """Higher confidence → larger lot size."""
        account_state = {"equity": 10000.0}
        signal = {
            "pair": "EURUSD",
            "direction": "BUY",
            "atr": 0.10,  # Large ATR to avoid guardrail
            "entry_price": 1.0500,
            "stop_loss": 1.0400,
            "take_profit": 1.0650,
        }
        
        signal_low = {**signal, "confidence": 0.50}
        signal_high = {**signal, "confidence": 0.90}
        
        lot_low = guardian.compute_lot_size(signal_low, account_state)
        lot_high = guardian.compute_lot_size(signal_high, account_state)
        
        assert lot_high > lot_low, f"High confidence should have larger lot: {lot_high} vs {lot_low}"
    
    def test_llm_risk_modifier_1_5_increases_lot(self, guardian, state):
        """LLM modifier 1.5 → increases lot size meaningfully."""
        account_state = {"equity": 10000.0}
        signal = {
            "pair": "EURUSD",
            "direction": "BUY",
            "confidence": 0.60,
            "atr": 0.10,  # Large ATR to avoid guardrail
            "entry_price": 1.0500,
            "stop_loss": 1.0400,
            "take_profit": 1.0650,
        }
        llm_decision = {"risk_modifier": 1.5}
        
        lot_base = guardian.compute_lot_size(signal, account_state, None)
        lot_modified = guardian.compute_lot_size(signal, account_state, llm_decision)
        
        ratio = lot_modified / lot_base if lot_base > 0 else 0
        # Allow for guardrail cap affecting the ratio slightly
        assert ratio > 1.30, f"Modifier ratio {ratio} should show meaningful increase"

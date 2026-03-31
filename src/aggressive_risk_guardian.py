"""
Aggressive Risk Guardian
- Size positions based on equity percentage (2-3%)
- Apply confidence and LLM modifiers
- Emergency halt at 15% total drawdown
"""

import logging
import math
from typing import Dict, Optional
from config import aggressive_config as cfg

logger = logging.getLogger(__name__)

class AggressiveRiskGuardian:
    """Manage position sizing and risk."""
    
    def __init__(self, state: Dict):
        self.state = state
        self.phase_risk = cfg.PHASE_RISK
        self.confidence_mult_range = cfg.CONFIDENCE_MULT_RANGE
        self.sl_multiplier = cfg.SL_MULTIPLIER
        self.tp_multiplier = cfg.TP_MULTIPLIER
        self.max_dd_pct = cfg.MAX_TOTAL_LOSS_PCT
    
    def check_disqualification(self, account_state: Dict) -> bool:
        """
        Check if account is disqualified (total DD >= 15%).
        Returns: True if disqualified, False otherwise
        """
        initial_balance = self.state.get("initial_balance", 0)
        current_equity = account_state.get("equity", 0)
        
        if initial_balance <= 0:
            return False
        
        drawdown_pct = (initial_balance - current_equity) / initial_balance
        
        if drawdown_pct >= self.max_dd_pct:
            logger.critical(f"DISQUALIFICATION: Total DD {drawdown_pct:.2%} >= {self.max_dd_pct:.0%}")
            return True
        
        return False
    
    def compute_lot_size(self, signal: Dict, account_state: Dict, 
                         llm_decision: Optional[Dict] = None) -> float:
        """
        Calculate lot size based on:
        - Risk percentage (phase-dependent)
        - SL distance (ATR × 1.2)
        - Confidence multiplier
        - LLM risk modifier
        """
        current_phase = self.state.get("current_phase", "aggressive")
        equity = account_state.get("equity", 0)
        
        if equity <= 0:
            logger.error("Invalid equity for lot sizing")
            return 0.0
        
        # Phase risk percentage
        if current_phase == "lock_in":
            # Lock-In phase: 0.8% if winning, 2.5% if behind
            return_pct = account_state.get("return_pct", 0)
            if return_pct >= cfg.LOCK_IN_TRIGGER_PCT:
                risk_pct = self.phase_risk["lock_in"]["winning"]
            else:
                risk_pct = self.phase_risk["lock_in"]["behind"]
        else:
            risk_pct = self.phase_risk.get(current_phase, 0.020)
        
        risk_amount = equity * risk_pct
        
        # SL distance in pips (ATR × 1.2)
        sl_distance = signal.get("atr", 0) * self.sl_multiplier
        
        if sl_distance <= 0:
            logger.warning("Invalid SL distance")
            return 0.0
        
        # Base lot size
        # For mini/micro lots, scale appropriately
        # Assuming typical pair, 0.00001 = 1 pip in 6-decimal pairs
        base_lot = risk_amount / sl_distance
        
        # Confidence multiplier (0.75 to 1.25)
        confidence = signal.get("confidence", 0.50)
        conf_mult = self._calculate_confidence_multiplier(confidence)
        
        # LLM risk modifier (0.5 to 1.5)
        risk_mod = 1.0
        if llm_decision:
            risk_mod = max(0.5, min(1.5, llm_decision.get("risk_modifier", 1.0)))
        
        final_lot = base_lot * conf_mult * risk_mod
        
        # Apply position limit guardrails
        max_lot = equity * 0.20  # Max 20% equity in single trade (aggressive mode)
        final_lot = min(final_lot, max_lot)
        
        logger.info(
            f"Lot size: {final_lot:.2f} "
            f"(risk={risk_pct:.1%}, conf={conf_mult:.2f}, llm={risk_mod:.2f})"
        )
        
        return final_lot
    
    def _calculate_confidence_multiplier(self, confidence: float) -> float:
        """
        Calculate lot size multiplier based on confidence.
        Range: 0.75 (at 0.50 conf) to 1.25 (at 1.00 conf)
        """
        min_conf = 0.50  # Minimum threshold
        max_conf = 1.00  # Maximum confidence
        min_mult, max_mult = self.confidence_mult_range
        
        if confidence < min_conf:
            return min_mult
        if confidence >= max_conf:
            return max_mult
        
        # Linear interpolation
        return min_mult + (confidence - min_conf) / (max_conf - min_conf) * (max_mult - min_mult)
    
    def adjust_sl_tp(self, signal: Dict) -> Dict:
        """Adjust SL/TP based on ATR multiples."""
        atr = signal.get("atr", 0)
        entry = signal.get("entry_price", 0)
        direction = signal.get("direction", "BUY")
        
        if direction == "BUY":
            sl = entry - atr * self.sl_multiplier
            tp = entry + atr * self.tp_multiplier
        else:  # SELL
            sl = entry + atr * self.sl_multiplier
            tp = entry - atr * self.tp_multiplier
        
        return {
            "entry": entry,
            "stop_loss": sl,
            "take_profit": tp,
            "atr": atr,
        }
    
    def get_pyramid_lot(self, original_lot: float) -> float:
        """Calculate lot size for pyramid entry."""
        return original_lot * cfg.PYRAMID_LOT_FACTOR
    
    def get_reentry_lot(self, original_lot: float) -> float:
        """Calculate lot size for re-entry."""
        return original_lot * cfg.REENTRY_LOT_FACTOR

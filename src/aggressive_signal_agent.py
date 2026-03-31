"""
Aggressive Signal Agent
- Filter signals by confidence threshold
- Enforce position limits and re-entry rules
- Pass qualified signals to LLM for final decision
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime
from config import aggressive_config as cfg

logger = logging.getLogger(__name__)

class AggressiveSignalAgent:
    """Filter and manage trading signals."""
    
    def __init__(self, state: Dict):
        self.state = state
        self.max_concurrent = cfg.MAX_CONCURRENT_TRADES
        self.max_same_pair = cfg.MAX_SAME_PAIR_POSITIONS
        self.confidence_thresholds = cfg.CONFIDENCE_THRESHOLDS
        self.max_reentries = cfg.MAX_REENTRIES
        self.news_blackout_before = cfg.NEWS_BLACKOUT_BEFORE_MIN
        self.news_blackout_after = cfg.NEWS_BLACKOUT_AFTER_MIN
    
    def process_signals(self, signals: List, current_phase: str, news_filter) -> Optional[Dict]:
        """
        Process signals and return highest-priority candidate for LLM.
        Returns: signal dict for llm_pending, or None if all filtered
        """
        qualified = []
        
        for signal in signals:
            # Apply filters
            reason = self._filter_signal(signal, current_phase, news_filter)
            if reason:
                logger.debug(f"Signal rejected ({signal.pair}): {reason}")
                continue
            
            qualified.append(signal)
        
        if not qualified:
            return None
        
        # Sort by confidence (highest first), then by R-multiple
        qualified.sort(key=lambda s: (s.confidence, s.r_multiple), reverse=True)
        
        # Return highest-priority signal for LLM decision
        top_signal = qualified[0]
        
        return {
            "pair": top_signal.pair,
            "direction": top_signal.direction,
            "session": top_signal.session,
            "confidence": top_signal.confidence,
            "atr": top_signal.atr,
            "indicators": top_signal.indicators_fired,
            "entry_price": top_signal.entry_price,
            "stop_loss": top_signal.stop_loss,
            "take_profit": top_signal.take_profit,
            "r_multiple": top_signal.r_multiple,
        }
    
    def _filter_signal(self, signal, current_phase: str, news_filter) -> Optional[str]:
        """
        Apply all signal filters.
        Returns: rejection reason string, or None if signal passes
        """
        # Confidence threshold check
        min_conf = self.confidence_thresholds.get(current_phase, 0.50)
        if signal.confidence < min_conf:
            return f"confidence {signal.confidence:.2f} < {min_conf}"
        
        # News blackout check
        if not news_filter.is_trade_allowed(signal.pair):
            return "news blackout active"
        
        # Max concurrent trades check
        open_trades = self.state.get("open_trades", [])
        if len(open_trades) >= self.max_concurrent:
            return f"max concurrent trades ({self.max_concurrent}) reached"
        
        # Same-pair position limit check
        same_pair_count = sum(1 for t in open_trades if t.get("pair") == signal.pair)
        if same_pair_count >= self.max_same_pair:
            return f"max same-pair positions ({self.max_same_pair}) reached"
        
        # Re-entry check
        setup_id = f"{signal.pair}_{signal.direction}"
        recent_setups = self.state.get("recent_setups", {})
        if setup_id in recent_setups:
            reentry_count = recent_setups[setup_id].get("reentry_count", 0)
            if reentry_count >= self.max_reentries:
                return f"max re-entries ({self.max_reentries}) for this setup"
        
        return None
    
    def record_setup(self, signal: Dict):
        """Record a setup for re-entry tracking."""
        setup_id = f"{signal['pair']}_{signal['direction']}"
        recent_setups = self.state.setdefault("recent_setups", {})
        
        if setup_id not in recent_setups:
            recent_setups[setup_id] = {
                "first_entry": datetime.utcnow(),
                "reentry_count": 0,
                "entries": [],
            }
        else:
            recent_setups[setup_id]["reentry_count"] += 1
        
        recent_setups[setup_id]["entries"].append({
            "time": datetime.utcnow(),
            "confidence": signal.get("confidence"),
        })
    
    def mark_setup_complete(self, pair: str, direction: str):
        """Mark a setup as complete (no more re-entries)."""
        setup_id = f"{pair}_{direction}"
        recent_setups = self.state.get("recent_setups", {})
        if setup_id in recent_setups:
            del recent_setups[setup_id]

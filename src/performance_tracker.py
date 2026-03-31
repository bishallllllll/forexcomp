"""
Performance Tracker
- Track account equity, returns, P&L
- Calculate phase progression
- Monitor drawdown
"""

import logging
from typing import Dict, Optional
from datetime import datetime
from config import aggressive_config as cfg

logger = logging.getLogger(__name__)

class PerformanceTracker:
    """Track competition performance and phase progression."""
    
    def __init__(self, state: Dict):
        self.state = state
        self.rocket_trigger = cfg.ROCKET_TRIGGER_PCT
        self.lock_in_trigger = cfg.LOCK_IN_TRIGGER_PCT
        self.lock_in_min_day = cfg.LOCK_IN_MIN_DAY
    
    def update_account_state(self, mt5_conn) -> Dict:
        """
        Get current account state from MT5.
        Returns: dict with equity, balance, return %, P&L
        """
        account_info = mt5_conn.get_account_info()
        if not account_info:
            logger.error("Failed to get account info")
            return {}
        
        initial_balance = self.state.get("initial_balance", 0)
        current_equity = account_info.get("equity", 0)
        
        return_pct = 0.0
        if initial_balance > 0:
            return_pct = (current_equity - initial_balance) / initial_balance * 100
        
        state = {
            "equity": current_equity,
            "balance": account_info.get("balance", 0),
            "margin_free": account_info.get("margin_free", 0),
            "margin_level": account_info.get("margin_level", 0),
            "return_pct": return_pct,
            "timestamp": datetime.utcnow(),
        }
        
        self.state["account_state"] = state
        return state
    
    def calculate_daily_pnl(self, closed_trades: list) -> float:
        """Calculate P&L for closed trades today."""
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_pnl = sum(
            t.get("pnl", 0) for t in closed_trades
            if t.get("close_time", datetime.min) >= today_start
        )
        return today_pnl
    
    def get_phase(self) -> str:
        """Determine current phase based on return and day."""
        account_state = self.state.get("account_state", {})
        return_pct = account_state.get("return_pct", 0)
        days_elapsed = self.state.get("days_elapsed", 1)
        
        # Check Lock-In trigger (15% return on day 5+)
        if return_pct >= self.lock_in_trigger and days_elapsed >= self.lock_in_min_day:
            logger.info(f"LOCK-IN mode activated: return={return_pct:.2f}%")
            return "lock_in"
        
        # Check Rocket trigger (8% return)
        if return_pct >= self.rocket_trigger:
            logger.info(f"ROCKET MODE activated: return={return_pct:.2f}%")
            return "rocket"
        
        # Default: Aggressive
        return "aggressive"
    
    def get_leaderboard_projection(self, target_return: float, days_remaining: int) -> Dict:
        """
        Project final return if current daily rate continues.
        Used to guide phase transitions.
        """
        account_state = self.state.get("account_state", {})
        current_return = account_state.get("return_pct", 0)
        days_elapsed = self.state.get("days_elapsed", 1)
        
        # Daily rate
        daily_rate = current_return / max(days_elapsed, 1)
        projected_return = current_return + (daily_rate * days_remaining)
        
        # Win chance: how likely to hit target
        gap = target_return - current_return
        win_pct = 100 if gap <= 0 else min(100, (current_return / target_return) * 100)
        
        return {
            "current_return_pct": current_return,
            "projected_return_pct": projected_return,
            "target_return_pct": target_return,
            "gap_pct": gap,
            "win_probability_pct": win_pct,
            "daily_rate_pct": daily_rate,
            "days_remaining": days_remaining,
        }
    
    def log_performance(self):
        """Log current performance metrics."""
        account_state = self.state.get("account_state", {})
        open_trades = self.state.get("open_trades", [])
        phase = self.get_phase()
        
        logger.info(
            f"[{phase.upper()}] "
            f"Equity: ${account_state.get('equity', 0):,.2f} | "
            f"Return: {account_state.get('return_pct', 0):+.2f}% | "
            f"Open: {len(open_trades)} | "
            f"Margin: {account_state.get('margin_level', 0):.0f}%"
        )

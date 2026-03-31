"""
Competition Coordinator
- Main loop orchestrating all agents
- Phase transitions (Aggressive → Rocket → Lock-In)
- 15-second polling cycle
"""

import logging
import time
from typing import Dict, Optional
from datetime import datetime, timedelta
from config import aggressive_config as cfg
from src.mt5_connection import MT5Connection
from src.market_analyst_agent import MarketAnalystAgent
from src.aggressive_signal_agent import AggressiveSignalAgent
from src.llm_decision_agent import LLMDecisionAgent
from src.aggressive_risk_guardian import AggressiveRiskGuardian
from src.aggressive_execution_agent import AggressiveExecutionAgent
from src.performance_tracker import PerformanceTracker
from src.news_filter import NewsFilter

logger = logging.getLogger(__name__)

class CompetitionCoordinator:
    """Main orchestrator for the aggressive trading bot."""
    
    def __init__(self, target_return: float = 30, days: int = 7, llm_provider: str = "azure"):
        self.target_return = target_return
        self.total_days = days
        self.poll_interval = cfg.POLL_INTERVAL_SEC
        
        # Initialize state
        self.state = {
            "started": datetime.utcnow(),
            "target_return": target_return,
            "total_days": days,
            "initial_balance": None,
            "current_phase": "aggressive",
            "open_trades": [],
            "closed_trades": [],
            "recent_setups": {},
        }
        
        # Initialize agents
        self.mt5 = MT5Connection()
        self.analyst = MarketAnalystAgent()
        self.signal_agent = AggressiveSignalAgent(self.state)
        self.llm_agent = LLMDecisionAgent(self.state)
        self.risk_guardian = AggressiveRiskGuardian(self.state)
        self.executor = AggressiveExecutionAgent(self.mt5, self.state)
        self.tracker = PerformanceTracker(self.state)
        self.news_filter = NewsFilter(cfg.NEWS_BLACKOUT_BEFORE_MIN, cfg.NEWS_BLACKOUT_AFTER_MIN)
        
        # Connect to MT5
        if not self.mt5.connect():
            raise Exception("Failed to connect to MT5")
        
        # Read initial balance
        initial_balance = self.mt5.get_balance()
        if not initial_balance:
            raise Exception("Failed to read account balance from MT5")
        
        self.state["initial_balance"] = initial_balance
        logger.info(f"Competition started: balance=${initial_balance:,.2f}, target={target_return}%")
    
    def run(self, max_cycles: Optional[int] = None):
        """
        Main competition loop.
        Each cycle: analyst → signal → LLM → risk → executor → tracker
        """
        cycle = 0
        start_time = datetime.utcnow()
        
        try:
            while True:
                cycle += 1
                cycle_start = time.time()
                
                # Check time limit
                elapsed = datetime.utcnow() - start_time
                if elapsed > timedelta(days=self.total_days):
                    logger.info(f"Competition ended: {self.total_days} days elapsed")
                    break
                
                if max_cycles and cycle > max_cycles:
                    logger.info(f"Stopping after {max_cycles} cycles")
                    break
                
                # Update phase
                account_state = self.tracker.update_account_state(self.mt5)
                self.state["current_phase"] = self.tracker.get_phase()
                self.state["account_state"] = account_state
                days_elapsed = (elapsed.total_seconds() / 86400) + 1
                self.state["days_elapsed"] = days_elapsed
                self.state["days_remaining"] = max(0, self.total_days - days_elapsed)
                
                # Check disqualification
                if self.risk_guardian.check_disqualification(account_state):
                    logger.critical("DISQUALIFIED: Total loss exceeded 15%")
                    break
                
                # Generate signals from all pairs/sessions
                signals = self.analyst.analyze_all_sessions()
                
                # Process signals through filter
                best_signal = self.signal_agent.process_signals(
                    signals,
                    self.state["current_phase"],
                    self.news_filter
                )
                
                if best_signal:
                    self.state["llm_pending"] = best_signal
                    
                    # Send to LLM for decision
                    llm_decision = self.llm_agent.process_signal(
                        best_signal,
                        account_state,
                        self.state.get("closed_trades", [])
                    )
                    
                    if llm_decision and llm_decision["decision"] == "EXECUTE":
                        adjusted_signal = best_signal.copy()
                        adj_conf = adjusted_signal.get("confidence", 0.0) + llm_decision.get("confidence_adjustment", 0.0)
                        adjusted_signal["confidence"] = max(0.0, min(1.0, adj_conf))
                        
                        # Calculate lot size with adjustments
                        lot = self.risk_guardian.compute_lot_size(
                            adjusted_signal,
                            account_state,
                            llm_decision
                        )
                        
                        if lot > 0:
                            # Adjust SL/TP based on ATR
                            sl_tp = self.risk_guardian.adjust_sl_tp(adjusted_signal)
                            adjusted_signal.update(sl_tp)
                            
                            # Execute trade
                            trade = self.executor.execute_trade(
                                adjusted_signal,
                                lot,
                                comment=f"{self.state['current_phase']}_d{self.state['days_elapsed']:.0f}"
                            )
                            
                            if trade:
                                self.signal_agent.record_setup(adjusted_signal)
                
                # Manage open positions
                self.executor.manage_positions(account_state)
                self.executor.update_position_tracking(account_state)
                
                # Log performance
                self.tracker.log_performance()
                
                # Sleep until next cycle
                elapsed_this_cycle = time.time() - cycle_start
                sleep_time = max(0, self.poll_interval - elapsed_this_cycle)
                if sleep_time > 0:
                    time.sleep(sleep_time)
        
        except KeyboardInterrupt:
            logger.info("Competition stopped by user")
        except Exception as e:
            logger.error(f"Competition error: {e}", exc_info=True)
        finally:
            self._cleanup()
    
    def _cleanup(self):
        """Cleanup resources."""
        try:
            # Close all open positions
            open_trades = self.state.get("open_trades", [])
            for trade in open_trades:
                if trade["status"] == "open":
                    self.executor.close_position(trade["ticket"], "Competition ended")
            
            # Disconnect MT5
            self.mt5.disconnect()
            
            # Final report
            account_state = self.tracker.update_account_state(self.mt5)
            final_return = account_state.get("return_pct", 0)
            logger.info(
                f"Competition complete: final return={final_return:+.2f}%, "
                f"target={self.target_return}%"
            )
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

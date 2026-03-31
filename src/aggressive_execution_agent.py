"""
Aggressive Execution Agent
- Place orders on MT5
- Manage partial closes, trailing stops, pyramiding
- Track open positions
"""

import logging
import MetaTrader5 as mt5
from typing import Dict, List, Optional
from datetime import datetime
from config import aggressive_config as cfg
from src.mt5_connection import MT5Connection

logger = logging.getLogger(__name__)

class AggressiveExecutionAgent:
    """Execute trades and manage positions."""
    
    def __init__(self, mt5_conn: MT5Connection, state: Dict):
        self.mt5 = mt5_conn
        self.state = state
        self.partial_close_r = cfg.PARTIAL_CLOSE_AT_R
        self.partial_close_pct = cfg.PARTIAL_CLOSE_PERCENT
        self.trail_r = cfg.TRAIL_AT_R
        self.trail_mult = cfg.TRAIL_MULTIPLIER
        self.break_even_r = cfg.BREAK_EVEN_AT_R
        self.pyramid_r = cfg.PYRAMID_TRIGGER_R
        self.pyramid_max = cfg.MAX_PYRAMID_ADDS
    
    def execute_trade(self, signal: Dict, lot_size: float, comment: str = "") -> Optional[Dict]:
        """
        Place a new order on MT5.
        Returns: trade dict with ticket, entry, SL, TP, or None on failure
        """
        pair = signal.get("pair")
        direction = signal.get("direction")
        entry = signal.get("entry_price")
        sl = signal.get("stop_loss")
        tp = signal.get("take_profit")
        
        if not all([pair, direction, entry, sl, tp, lot_size > 0]):
            logger.error(f"Invalid trade params: {signal}")
            return None
        
        try:
            # Determine order type
            action = 0 if direction == "BUY" else 1  # 0=BUY, 1=SELL
            
            # Send order
            ticket = self.mt5.send_order(
                symbol=pair,
                action=action,
                volume=lot_size,
                price=entry,
                sl=sl,
                tp=tp,
                comment=comment or f"Aggressive {direction} {pair}",
            )
            
            if ticket is None:
                logger.error(f"Order failed for {pair}")
                return None
            
            # Record trade
            trade = {
                "ticket": ticket,
                "pair": pair,
                "direction": direction,
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "atr": signal.get("atr"),
                "lot": lot_size,
                "entry_time": datetime.utcnow(),
                "status": "open",
                "r_multiple": abs(tp - entry) / abs(sl - entry) if abs(sl - entry) > 0 else 0,
                "pyramid_count": 0,
                "reentry_count": 0,
            }
            
            open_trades = self.state.setdefault("open_trades", [])
            open_trades.append(trade)
            
            logger.info(f"Trade opened: {pair} {direction} {lot_size}L @ {entry}")
            return trade
        
        except Exception as e:
            logger.error(f"Execute trade error: {e}")
            return None
    
    def close_position(self, ticket: int, reason: str = "") -> bool:
        """Close a position by ticket."""
        try:
            # Find trade
            open_trades = self.state.get("open_trades", [])
            trade = next((t for t in open_trades if t["ticket"] == ticket), None)
            
            if not trade:
                logger.warning(f"Trade {ticket} not found")
                return False
            
            pair = trade["pair"]
            lot = trade["lot"]
            
            # Get current price
            info = self.mt5.get_symbol_info(pair)
            if not info:
                logger.error(f"Can't get price for {pair}")
                return False
            
            close_price = info["bid"] if trade["direction"] == "BUY" else info["ask"]
            
            # Close position
            success = self.mt5.close_position(
                ticket=ticket,
                symbol=pair,
                volume=lot,
                price=close_price,
                comment=reason,
                position_type=mt5.POSITION_TYPE_BUY if trade["direction"] == "BUY" else mt5.POSITION_TYPE_SELL,
            )
            
            if success:
                trade["status"] = "closed"
                trade["close_price"] = close_price
                trade["close_time"] = datetime.utcnow()
                
                # Calculate P&L
                if trade["direction"] == "BUY":
                    pnl = (close_price - trade["entry"]) * lot
                else:
                    pnl = (trade["entry"] - close_price) * lot
                
                trade["pnl"] = pnl
                logger.info(f"Position closed: {pair} {reason} P&L={pnl:.2f}")
                
                closed_trades = self.state.setdefault("closed_trades", [])
                closed_trades.append(trade)
                open_trades.remove(trade)
                return True
        
        except Exception as e:
            logger.error(f"Close position error: {e}")
        
        return False
    
    def manage_positions(self, account_state: Dict):
        """
        Manage open positions:
        - Partial closes at +2.0R
        - Trailing stops at +3.0R
        - Break-even at +1.2R
        - Pyramid adds at +1.5R
        """
        open_trades = self.state.get("open_trades", [])
        
        for trade in open_trades:
            if trade["status"] != "open":
                continue
            
            # Get current price
            info = self.mt5.get_symbol_info(trade["pair"])
            if not info:
                continue
            
            current_price = info["bid"] if trade["direction"] == "BUY" else info["ask"]
            
            # Calculate R (risk units won)
            entry = trade["entry"]
            sl = trade["sl"]
            r = abs(current_price - entry) / abs(sl - entry) if abs(sl - entry) > 0 else 0
            
            # Partial close at +2.0R
            if r >= self.partial_close_r and not trade.get("partial_closed"):
                close_lot = trade["lot"] * self.partial_close_pct
                if self.mt5.close_position(
                    ticket=trade["ticket"],
                    symbol=trade["pair"],
                    volume=close_lot,
                    price=current_price,
                    comment=f"Partial close at +{r:.1f}R",
                    position_type=mt5.POSITION_TYPE_BUY if trade["direction"] == "BUY" else mt5.POSITION_TYPE_SELL,
                ):
                    trade["partial_closed"] = True
                    trade["lot"] -= close_lot  # Reduce remaining lot
                    logger.info(f"Partial close: {trade['pair']} {close_lot}L @ +{r:.1f}R")
            
            # Trailing stop at +3.0R
            if r >= self.trail_r and not trade.get("trailing"):
                trail_dist = trade["atr"] * self.trail_mult if "atr" in trade else 0
                if trade["direction"] == "BUY":
                    new_sl = max(trade["sl"], current_price - trail_dist)
                else:
                    new_sl = min(trade["sl"], current_price + trail_dist)
                
                if (trade["direction"] == "BUY" and new_sl > trade["sl"]) or \
                   (trade["direction"] == "SELL" and new_sl < trade["sl"]):
                    if self.mt5.modify_position_sl_tp(
                        ticket=trade["ticket"],
                        symbol=trade["pair"],
                        sl=new_sl,
                        tp=trade["tp"],
                        comment=f"Trailing +{r:.1f}R",
                    ):
                        trade["sl"] = new_sl
                        trade["trailing"] = True
                        logger.info(f"Trailing activated: {trade['pair']} SL={new_sl}")
            
            # Break-even at +1.2R
            if r >= self.break_even_r and not trade.get("break_even_set"):
                if trade["direction"] == "BUY":
                    new_sl = trade["entry"] + 0.00001  # Tiny profit
                else:
                    new_sl = trade["entry"] - 0.00001
                
                if self.mt5.modify_position_sl_tp(
                    ticket=trade["ticket"],
                    symbol=trade["pair"],
                    sl=new_sl,
                    tp=trade["tp"],
                    comment=f"Break-even +{r:.1f}R",
                ):
                    trade["sl"] = new_sl
                    trade["break_even_set"] = True
                    logger.info(f"Break-even set: {trade['pair']} @ +{r:.1f}R")
            
            # Pyramid add at +1.5R
            if r >= self.pyramid_r and trade.get("pyramid_count", 0) < self.pyramid_max:
                logger.info(f"Pyramid candidate: {trade['pair']} @ +{r:.1f}R")
                # Pyramid logic would be triggered by signal agent with LLM approval
    
    def update_position_tracking(self, account_state: Dict):
        """Update P&L and status for all open positions."""
        open_trades = self.state.get("open_trades", [])
        positions = self.mt5.get_positions()
        
        for trade in list(open_trades):
            if trade["status"] != "open":
                continue
            
            # Find position in MT5
            position = next(
                (p for p in positions if p["ticket"] == trade["ticket"]),
                None
            )
            
            if position:
                trade["pnl"] = position["pnl"]
                trade["current_price"] = position["current_price"]
            else:
                # Position closed externally
                trade["status"] = "closed"
                logger.warning(f"Position {trade['ticket']} closed externally")
                closed_trades = self.state.setdefault("closed_trades", [])
                closed_trades.append(trade)
                open_trades.remove(trade)

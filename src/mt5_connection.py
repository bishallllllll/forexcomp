"""
MT5 Connection Manager
- Auto-read account balance from MT5 on startup
- Order management
- Position tracking
- Account info queries
"""

import MetaTrader5 as mt5
import logging
import time
from typing import Optional, Dict, List, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class MT5Connection:
    """Wrapper for MetaTrader5 operations with retry logic."""
    
    def __init__(self, timeout_sec=10, retry_count=3, retry_delay_sec=2):
        self.timeout_sec = timeout_sec
        self.retry_count = retry_count
        self.retry_delay_sec = retry_delay_sec
        self.connected = False
        
    def connect(self) -> bool:
        """Connect to MT5 terminal."""
        for attempt in range(self.retry_count):
            try:
                if not mt5.initialize():
                    logger.error(f"MT5 init failed: {mt5.last_error()}")
                    if attempt < self.retry_count - 1:
                        time.sleep(self.retry_delay_sec)
                    continue
                self.connected = True
                logger.info("MT5 connected")
                return True
            except Exception as e:
                logger.error(f"MT5 connection error (attempt {attempt + 1}): {e}")
                if attempt < self.retry_count - 1:
                    time.sleep(self.retry_delay_sec)
        
        return False
    
    def disconnect(self):
        """Disconnect from MT5."""
        if self.connected:
            mt5.shutdown()
            self.connected = False
            logger.info("MT5 disconnected")
    
    def get_account_info(self) -> Optional[Dict[str, Any]]:
        """Get account balance, equity, margin info."""
        try:
            info = mt5.account_info()
            if info is None:
                logger.error(f"Failed to get account info: {mt5.last_error()}")
                return None
            
            return {
                "balance": info.balance,
                "equity": info.equity,
                "margin": info.margin,
                "margin_free": info.margin_free,
                "margin_level": info.margin_level,
                "currency": info.currency,
            }
        except Exception as e:
            logger.error(f"Error getting account info: {e}")
            return None
    
    def get_balance(self) -> Optional[float]:
        """Get current account balance."""
        info = self.get_account_info()
        return info["balance"] if info else None
    
    def get_equity(self) -> Optional[float]:
        """Get current account equity."""
        info = self.get_account_info()
        return info["equity"] if info else None
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """Get all open positions."""
        try:
            positions = mt5.positions_get()
            if positions is None:
                logger.error(f"Failed to get positions: {mt5.last_error()}")
                return []
            
            return [
                {
                    "ticket": p.ticket,
                    "symbol": p.symbol,
                    "type": p.type,  # 0=buy, 1=sell
                    "volume": p.volume,
                    "open_price": p.price_open,
                    "current_price": p.price_current,
                    "open_time": p.time,
                    "pnl": p.profit,
                }
                for p in positions
            ]
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []
    
    def send_order(self, symbol: str, action: int, volume: float, price: float,
                   sl: float, tp: float, comment: str = "") -> Optional[int]:
        """
        Send order to MT5.
        action: 0=BUY, 1=SELL
        Returns: order ticket or None on failure
        """
        try:
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": mt5.ORDER_TYPE_BUY if action == 0 else mt5.ORDER_TYPE_SELL,
                "price": price,
                "sl": sl,
                "tp": tp,
                "deviation": 20,
                "magic": 31337,
                "comment": comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            result = mt5.order_send(request)
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                logger.error(f"Order failed: {result.comment}")
                return None
            
            logger.info(f"Order sent: {symbol} {volume}L @ {price} SL={sl} TP={tp}")
            return result.order
        except Exception as e:
            logger.error(f"Error sending order: {e}")
            return None
    
    def close_position(self, ticket: int, symbol: str, volume: float,
                       price: float, comment: str = "", position_type: Optional[int] = None) -> bool:
        """Close an open position by ticket."""
        try:
            if position_type is None:
                positions = mt5.positions_get(ticket=ticket)
                if not positions:
                    logger.error(f"Position {ticket} not found for close")
                    return False
                position_type = positions[0].type
            
            order_type = (
                mt5.ORDER_TYPE_SELL
                if position_type == mt5.POSITION_TYPE_BUY
                else mt5.ORDER_TYPE_BUY
            )
            
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": order_type,
                "position": ticket,
                "price": price,
                "deviation": 20,
                "magic": 31337,
                "comment": comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            result = mt5.order_send(request)
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                logger.error(f"Close failed: {result.comment}")
                return False
            
            logger.info(f"Position closed: ticket={ticket} {symbol} {volume}L")
            return True
        except Exception as e:
            logger.error(f"Error closing position: {e}")
            return False
    
    def get_rates(self, symbol: str, timeframe: int, count: int) -> Optional[List[Dict]]:
        """
        Get OHLC data.
        timeframe: mt5.TIMEFRAME_M1, mt5.TIMEFRAME_H1, etc.
        Returns: list of candles [time, open, high, low, close, volume]
        """
        try:
            rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
            if rates is None:
                logger.error(f"Failed to get rates for {symbol}: {mt5.last_error()}")
                return None
            
            return [
                {
                    "time": r[0],
                    "open": r[1],
                    "high": r[2],
                    "low": r[3],
                    "close": r[4],
                    "volume": r[5],
                }
                for r in rates
            ]
        except Exception as e:
            logger.error(f"Error getting rates: {e}")
            return None

    def modify_position_sl_tp(self, ticket: int, symbol: str, sl: float, tp: float,
                              comment: str = "") -> bool:
        """Modify SL/TP for an open position."""
        try:
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "position": ticket,
                "symbol": symbol,
                "sl": sl,
                "tp": tp,
                "magic": 31337,
                "comment": comment,
            }
            
            result = mt5.order_send(request)
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                logger.error(f"SL/TP modify failed: {result.comment}")
                return False
            
            logger.info(f"SL/TP modified: ticket={ticket} SL={sl} TP={tp}")
            return True
        except Exception as e:
            logger.error(f"Error modifying SL/TP: {e}")
            return False
    
    def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get symbol specification."""
        try:
            info = mt5.symbol_info(symbol)
            if info is None:
                logger.error(f"Symbol {symbol} not found")
                return None
            
            return {
                "symbol": info.name,
                "bid": info.bid,
                "ask": info.ask,
                "bid_high": info.bid_high,
                "bid_low": info.bid_low,
                "ask_high": info.ask_high,
                "ask_low": info.ask_low,
                "volume": info.volume,
                "volume_high": info.volume_high,
                "volume_low": info.volume_low,
            }
        except Exception as e:
            logger.error(f"Error getting symbol info for {symbol}: {e}")
            return None

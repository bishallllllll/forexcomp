"""
Market Analyst Agent
- Technical analysis on all available pairs
- Three trading sessions: Asian, London, NY
- Signal generation with confidence scores
"""

import logging
import MetaTrader5 as mt5
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import numpy as np
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class TASignal:
    """Technical analysis signal."""
    pair: str
    direction: str  # "BUY" or "SELL"
    session: str  # "asian", "london", "ny"
    confidence: float  # 0.0 - 1.0
    atr: float
    indicators_fired: List[str]
    entry_price: float
    stop_loss: float
    take_profit: float
    r_multiple: float  # Risk/Reward ratio

class MarketAnalystAgent:
    """Generate trading signals from technical analysis."""
    
    # All available pairs across three sessions
    SESSIONS = {
        "asian": {
            "pairs": [
                "USDJPY", "EURJPY", "GBPJPY", "AUDJPY", "CADJPY", "NZDJPY", "CHFJPY",
                "AUDUSD", "NZDUSD", "AUDNZD", "AUDCAD", "AUDCHF",
                "USDCAD", "USDCHF",
            ],
            "style": "mean_reversion",
        },
        "london": {
            "pairs": [
                "EURUSD", "EURGBP", "EURJPY", "EURCHF", "EURCAD", "EURAUD", "EURNZD",
                "GBPUSD", "GBPJPY", "GBPCAD", "GBPAUD", "GBPNZD", "GBPCHF",
                "USDCHF", "USDCAD",
            ],
            "style": "breakout_momentum",
        },
        "ny": {
            "pairs": [
                "EURUSD", "GBPUSD", "USDCAD", "USDCHF", "USDJPY",
                "AUDUSD", "NZDUSD",
                "XAUUSD", "XAGUSD",
                "AUDCAD", "NZDCAD", "CADCHF",
            ],
            "style": "trend_continuation",
        },
    }
    
    def __init__(self, min_atr_volatility=2.0, h1_trend_bonus=0.05):
        self.min_atr_volatility = min_atr_volatility
        self.h1_trend_bonus = h1_trend_bonus
        self.signals: List[TASignal] = []
        
    def analyze_all_sessions(self) -> List[TASignal]:
        """Run analysis on all pairs across all sessions."""
        self.signals = []
        
        for session_name, session_config in self.SESSIONS.items():
            for pair in session_config["pairs"]:
                signals = self._analyze_pair(pair, session_name, session_config["style"])
                self.signals.extend(signals)
        
        logger.info(f"Generated {len(self.signals)} signals across all pairs")
        return self.signals
    
    def _analyze_pair(self, pair: str, session: str, style: str) -> List[TASignal]:
        """Analyze a single pair for signals."""
        signals = []
        
        try:
            # Get H4 and H1 data
            h4_rates = self._get_rates(pair, mt5.TIMEFRAME_H4, 50)
            h1_rates = self._get_rates(pair, mt5.TIMEFRAME_H1, 50)
            
            if not h4_rates or len(h4_rates) < 20:
                return signals
            
            atr_h4 = self._calculate_atr(h4_rates, 14)
            if atr_h4 < self.min_atr_volatility:
                logger.debug(f"{pair} ATR too low: {atr_h4}")
                return signals
            
            # Route to analysis based on session style
            if style == "mean_reversion":
                signals = self._analyze_mean_reversion(pair, session, h4_rates, h1_rates, atr_h4)
            elif style == "breakout_momentum":
                signals = self._analyze_breakout(pair, session, h4_rates, h1_rates, atr_h4)
            elif style == "trend_continuation":
                signals = self._analyze_trend(pair, session, h4_rates, h1_rates, atr_h4)
            
        except Exception as e:
            logger.error(f"Error analyzing {pair}: {e}")
        
        return signals
    
    def _analyze_mean_reversion(self, pair: str, session: str, h4_rates, h1_rates, atr: float) -> List[TASignal]:
        """Asian session: Bollinger Bands + RSI fade."""
        signals = []
        
        # Bollinger Bands on H4
        sma, std = self._calculate_bb(h4_rates, 20, 2)
        rsi = self._calculate_rsi(h4_rates, 14)
        
        current_close = h4_rates[-1]["close"]
        upper_band = sma[-1] + 2 * std[-1]
        lower_band = sma[-1] - 2 * std[-1]
        
        # Oversold rebound (RSI 35 or lower touching lower band)
        if rsi[-1] <= 35 and current_close <= lower_band * 1.01:
            signal = TASignal(
                pair=pair,
                direction="BUY",
                session=session,
                confidence=0.58,
                atr=atr,
                indicators_fired=["BB_TOUCH_LOWER", "RSI_OVERSOLD"],
                entry_price=current_close,
                stop_loss=current_close - atr * 1.2,
                take_profit=current_close + atr * 3.5,
                r_multiple=3.5 / 1.2,
            )
            # H1 trend bonus
            h1_ema = self._calculate_ema(h1_rates, 21)
            if current_close > h1_ema[-1]:
                signal.confidence += self.h1_trend_bonus
            signals.append(signal)
        
        # Overbought rejection (RSI 65+ touching upper band)
        elif rsi[-1] >= 65 and current_close >= upper_band * 0.99:
            signal = TASignal(
                pair=pair,
                direction="SELL",
                session=session,
                confidence=0.58,
                atr=atr,
                indicators_fired=["BB_TOUCH_UPPER", "RSI_OVERBOUGHT"],
                entry_price=current_close,
                stop_loss=current_close + atr * 1.2,
                take_profit=current_close - atr * 3.5,
                r_multiple=3.5 / 1.2,
            )
            # H1 trend bonus
            h1_ema = self._calculate_ema(h1_rates, 21)
            if current_close < h1_ema[-1]:
                signal.confidence += self.h1_trend_bonus
            signals.append(signal)
        
        return signals
    
    def _analyze_breakout(self, pair: str, session: str, h4_rates, h1_rates, atr: float) -> List[TASignal]:
        """London session: EMA cross + MACD + ADX breakout."""
        signals = []
        
        ema12 = self._calculate_ema(h4_rates, 12)
        ema26 = self._calculate_ema(h4_rates, 26)
        macd = ema12[-1] - ema26[-1]
        macd_prev = ema12[-2] - ema26[-2]
        adx = self._calculate_adx(h4_rates, 14)
        
        current_close = h4_rates[-1]["close"]
        
        # Golden cross (EMA12 > EMA26) + MACD positive + ADX > 20
        if ema12[-1] > ema26[-1] and macd > 0 and macd > macd_prev and adx[-1] > 20:
            signal = TASignal(
                pair=pair,
                direction="BUY",
                session=session,
                confidence=0.62,
                atr=atr,
                indicators_fired=["EMA_GOLDEN_CROSS", "MACD_POSITIVE", "ADX_STRONG"],
                entry_price=current_close,
                stop_loss=current_close - atr * 1.2,
                take_profit=current_close + atr * 3.5,
                r_multiple=3.5 / 1.2,
            )
            signals.append(signal)
        
        # Death cross (EMA12 < EMA26) + MACD negative + ADX > 20
        elif ema12[-1] < ema26[-1] and macd < 0 and macd < macd_prev and adx[-1] > 20:
            signal = TASignal(
                pair=pair,
                direction="SELL",
                session=session,
                confidence=0.62,
                atr=atr,
                indicators_fired=["EMA_DEATH_CROSS", "MACD_NEGATIVE", "ADX_STRONG"],
                entry_price=current_close,
                stop_loss=current_close + atr * 1.2,
                take_profit=current_close - atr * 3.5,
                r_multiple=3.5 / 1.2,
            )
            signals.append(signal)
        
        return signals
    
    def _analyze_trend(self, pair: str, session: str, h4_rates, h1_rates, atr: float) -> List[TASignal]:
        """NY session: Fib retracement + RSI."""
        signals = []
        
        rsi = self._calculate_rsi(h4_rates, 14)
        current_close = h4_rates[-1]["close"]
        
        # Find recent high/low for Fib levels
        high = max(r["high"] for r in h4_rates[-20:])
        low = min(r["low"] for r in h4_rates[-20:])
        range_ = high - low
        
        # Uptrend: Price bounces at 38.2%, 50%, 61.8% retracement
        fib_levels = {
            0.382: 0.58,
            0.50: 0.62,
            0.618: 0.68,
        }
        
        for fib_pct, confidence in fib_levels.items():
            retracement_level = high - (range_ * fib_pct)
            if abs(current_close - retracement_level) < atr * 0.2 and rsi[-1] < 50:
                signal = TASignal(
                    pair=pair,
                    direction="BUY",
                    session=session,
                    confidence=confidence,
                    atr=atr,
                    indicators_fired=[f"FIB_{int(fib_pct*100)}_BOUNCE"],
                    entry_price=current_close,
                    stop_loss=low - atr * 0.2,
                    take_profit=high + atr * 1.5,
                    r_multiple=2.5 / 1.2,
                )
                signals.append(signal)
        
        return signals
    
    def _get_rates(self, pair: str, timeframe: int, count: int) -> Optional[List[Dict]]:
        """Fetch OHLC data from MT5."""
        try:
            rates = mt5.copy_rates_from_pos(pair, timeframe, 0, count)
            if rates is None:
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
            logger.error(f"Error fetching rates for {pair}: {e}")
            return None
    
    def _calculate_atr(self, rates: List[Dict], period: int = 14) -> float:
        """Calculate Average True Range."""
        if len(rates) < period:
            return 0.0
        
        tr_values = []
        for i in range(1, len(rates)):
            h = rates[i]["high"]
            l = rates[i]["low"]
            c_prev = rates[i-1]["close"]
            tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
            tr_values.append(tr)
        
        return np.mean(tr_values[-period:]) if tr_values else 0.0
    
    def _calculate_rsi(self, rates: List[Dict], period: int = 14) -> np.ndarray:
        """Calculate Relative Strength Index."""
        if len(rates) < period:
            return np.array([50] * len(rates))
        
        closes = np.array([r["close"] for r in rates])
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.convolve(gains, np.ones(period) / period, mode="valid")
        avg_loss = np.convolve(losses, np.ones(period) / period, mode="valid")
        
        rs = avg_gain / (avg_loss + 1e-10)
        rsi = 100 - (100 / (1 + rs))
        
        # Pad to match original length
        rsi_full = np.concatenate([np.ones(period - 1) * 50, rsi])
        return rsi_full[-len(rates):]
    
    def _calculate_ema(self, rates: List[Dict], period: int) -> np.ndarray:
        """Calculate Exponential Moving Average."""
        closes = np.array([r["close"] for r in rates], dtype=float)
        if len(closes) == 0:
            return np.array([])
        
        k = 2.0 / (period + 1)
        ema = np.empty_like(closes)
        ema[0] = closes[0]
        for i in range(1, len(closes)):
            ema[i] = closes[i] * k + ema[i - 1] * (1 - k)
        return ema
    
    def _calculate_bb(self, rates: List[Dict], period: int = 20, std_dev: float = 2) -> Tuple[np.ndarray, np.ndarray]:
        """Calculate Bollinger Bands."""
        closes = np.array([r["close"] for r in rates])
        sma = np.convolve(closes, np.ones(period) / period, mode="same")
        std = np.array([
            np.std(closes[max(0, i - period + 1):i + 1]) if i >= 1 else 0.0
            for i in range(len(closes))
        ])
        return sma, std
    
    def _calculate_adx(self, rates: List[Dict], period: int = 14) -> np.ndarray:
        """Calculate Average Directional Index (simplified)."""
        if len(rates) < period:
            return np.array([20] * len(rates))
        
        highs = np.array([r["high"] for r in rates])
        lows = np.array([r["low"] for r in rates])
        
        plus_dm = np.where(np.diff(highs) > 0, np.diff(highs), 0)
        minus_dm = np.where(np.diff(lows) < 0, -np.diff(lows), 0)
        
        tr = []
        for i in range(1, len(rates)):
            tr.append(max(highs[i] - lows[i], abs(highs[i] - rates[i-1]["close"]), abs(lows[i] - rates[i-1]["close"])))
        
        adx_values = []
        for i in range(period, len(tr)):
            plus_di = 100 * np.mean(plus_dm[i-period:i]) / (np.mean(tr[i-period:i]) + 1e-10)
            minus_di = 100 * np.mean(minus_dm[i-period:i]) / (np.mean(tr[i-period:i]) + 1e-10)
            adx = abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10) * 100
            adx_values.append(adx)
        
        adx_full = np.concatenate([np.ones(period) * 20, adx_values])
        return adx_full[-len(rates):]

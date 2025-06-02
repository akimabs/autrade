from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

@dataclass
class Position:
    entry: float
    qty: float
    side: str
    tp_price: Decimal
    sl_price: float
    timestamp: datetime
    rsi: Optional[float] = None
    atr: Optional[float] = None
    margin: float = 0.0
    leverage: float = 1.0
    mark_price: float = 0.0
    liquidation_price: float = 0.0
    spread: float = 0.0
    ema20: Optional[float] = None
    ema50: Optional[float] = None
    last_close: Optional[float] = None
    lower_band: Optional[float] = None
    upper_band: Optional[float] = None
    is_green: Optional[bool] = None
    is_red: Optional[bool] = None
    signal: Optional[str] = None
    volume_now: Optional[float] = None
    volume_avg10: Optional[float] = None
    reason: Optional[str] = None
    candle_pattern: Optional[str] = None
    entry_confidence_score: Optional[int] = None
    price_change_5m: float = 0.0

    def __init__(
        self,
        entry: float,
        qty: float,
        side: str,
        tp_price: float,
        sl_price: float,
        timestamp: datetime,
        margin: float,
        leverage: float,
        mark_price: float = 0.0,
        liquidation_price: float = 0.0,
        spread: float = 0.0,
        rsi: float = 0.0,
        atr: float = 0.0,
        ema20: float = 0.0,
        ema50: float = 0.0,
        last_close: float = 0.0,
        lower_band: float = 0.0,
        upper_band: float = 0.0,
        is_green: bool = False,
        is_red: bool = False,
        volume_now: float = 0.0,
        volume_avg10: float = 0.0,
        candle_pattern: str = "",
        entry_confidence_score: float = 0.0,
        reason: str = "",
        price_change_5m: float = 0.0,
        signal: str = ""
    ):
        self.entry = entry
        self.qty = qty
        self.side = side
        self.tp_price = tp_price
        self.sl_price = sl_price
        self.timestamp = timestamp
        self.margin = margin
        self.leverage = leverage
        self.mark_price = mark_price
        self.liquidation_price = liquidation_price
        self.spread = spread
        self.rsi = rsi
        self.atr = atr
        self.ema20 = ema20
        self.ema50 = ema50
        self.last_close = last_close
        self.lower_band = lower_band
        self.upper_band = upper_band
        self.is_green = is_green
        self.is_red = is_red
        self.volume_now = volume_now
        self.volume_avg10 = volume_avg10
        self.candle_pattern = candle_pattern
        self.entry_confidence_score = entry_confidence_score
        self.reason = reason
        self.price_change_5m = price_change_5m
        self.signal = signal

@dataclass
class Trade:
    symbol: str
    entry: float
    exit: float
    qty: float
    pnl: float
    timestamp: datetime
    duration: str

class TradeManager:
    def __init__(self):
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []
        self.consecutive_losses: int = 0
        self.daily_trade_count: int = 0
        self.last_trade_reset: datetime = datetime.now().date()

    def add_position(self, symbol: str, position: Position) -> None:
        self.positions[symbol] = position

    def remove_position(self, symbol: str) -> None:
        if symbol in self.positions:
            del self.positions[symbol]

    def add_trade(self, trade: Trade) -> None:
        self.trades.append(trade)

    def reset_daily_counters(self) -> None:
        current_date = datetime.now().date()
        if current_date > self.last_trade_reset:
            self.daily_trade_count = 0
            self.last_trade_reset = current_date

    def increment_consecutive_losses(self) -> None:
        self.consecutive_losses += 1

    def reset_consecutive_losses(self) -> None:
        self.consecutive_losses = 0

    def increment_daily_trade_count(self) -> None:
        self.daily_trade_count += 1

    def clear_trades(self) -> None:
        self.trades.clear() 
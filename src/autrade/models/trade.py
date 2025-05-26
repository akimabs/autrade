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
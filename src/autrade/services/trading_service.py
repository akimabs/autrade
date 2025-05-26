from datetime import datetime
from decimal import Decimal, ROUND_DOWN
from typing import Dict, List, Optional, Tuple
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator
from ta.volatility import BollingerBands, AverageTrueRange
import aiohttp

from ..config.settings import Config
from ..models.trade import Position, Trade, TradeManager
from .binance_service import BinanceService
from .telegram_service import TelegramService

class TradingService:
    def __init__(
        self,
        config: Config,
        binance_service: BinanceService,
        telegram_service: TelegramService,
        trade_manager: TradeManager
    ):
        self.config = config
        self.binance = binance_service
        self.telegram = telegram_service
        self.trade_manager = trade_manager

    def generate_signal(
        self,
        rsi: float,
        ema20: float,
        ema50: float,
        last_close: float,
        lower_band: float,
        upper_band: float,
        is_green: bool,
        is_red: bool
    ) -> str:
        signal_mode = self.config.trading.mode

        if signal_mode == "conservative":
            if (
                rsi < 30 and
                ema20 > ema50 * 1.01 and
                last_close < lower_band * 0.99 and
                is_green
            ):
                return "LONG"
            elif (
                rsi > 70 and
                ema20 < ema50 * 0.99 and
                last_close > upper_band * 1.01 and
                is_red
            ):
                return "SHORT"

        elif signal_mode == "moderate":
            if (
                rsi < 45 and
                ema20 > ema50 and
                last_close < lower_band and
                is_green
            ):
                return "LONG"
            elif (
                rsi > 55 and
                ema20 < ema50 and
                last_close > upper_band and
                is_red
            ):
                return "SHORT"

        elif signal_mode == "aggressive":
            if (
                rsi < 50 and
                ema20 > ema50 and
                last_close <= lower_band * 1.02 and
                is_green
            ):
                return "LONG"
            elif (
                rsi > 50 and
                ema20 < ema50 and
                last_close >= upper_band * 0.98 and
                is_red
            ):
                return "SHORT"

        return "WAIT"

    async def analyze(
        self,
        session: aiohttp.ClientSession,
        symbol: str,
        idx: int = 0
    ) -> Optional[Tuple[str, str, float, float, float]]:
        df = await self.binance.get_klines(session, symbol)
        if df.empty or len(df) < 30:
            return None

        close = df["close"]
        open_ = df["open"]
        high = df["high"]
        low = df["low"]

        last_close = close.iloc[-1]
        last_open = open_.iloc[-1]

        rsi = RSIIndicator(close).rsi().iloc[-1]
        ema20 = EMAIndicator(close, window=20).ema_indicator().iloc[-1]
        ema50 = EMAIndicator(close, window=50).ema_indicator().iloc[-1]
        bb = BollingerBands(close)
        upper_band = bb.bollinger_hband().iloc[-1]
        lower_band = bb.bollinger_lband().iloc[-1]
        atr = AverageTrueRange(high, low, close, window=14).average_true_range().iloc[-1]
        min_atr = last_close * self.config.risk.min_atr_ratio

        if atr < min_atr:
            atr = min_atr

        is_green = last_close > last_open
        is_red = last_close < last_open

        signal = self.generate_signal(
            rsi, ema20, ema50, last_close,
            lower_band, upper_band, is_green, is_red
        )

        print(f"""
        📊 ANALYZE [{idx + 1}] {symbol}
        ├── Harga Terakhir : {last_close:.4f}
        ├── RSI            : {rsi:.2f}
        ├── EMA20 / EMA50  : {ema20:.4f} / {ema50:.4f}
        ├── BollingerBand  : Lower={lower_band:.4f} | Upper={upper_band:.4f}
        ├── ATR            : {atr:.4f}
        ├── Candle Status  : {"GREEN ✅" if is_green else "RED ❌"}
        └── Sinyal Akhir   : {signal}
        """)

        return symbol, signal, last_close, rsi, atr

    async def calculate_position_size(
        self,
        price: float,
        atr: float
    ) -> Tuple[Decimal, Decimal, Decimal]:
        usdt = self.config.fixed_usdt_balance
        price_decimal = Decimal(str(price))
        qty = (
            Decimal(usdt * self.config.trading.usdt_percentage * self.config.trading.leverage) /
            price_decimal
        ).quantize(Decimal('0.001'), rounding=ROUND_DOWN)

        atr_decimal = Decimal(str(atr))
        tp_price = price_decimal + (atr_decimal * Decimal('1.2'))
        sl_price = price_decimal - (atr_decimal * Decimal('0.8'))

        return qty, tp_price, sl_price

    async def process_trade(
        self,
        session: aiohttp.ClientSession,
        symbol: str,
        signal: str,
        price: float,
        rsi: float,
        atr: float
    ) -> None:
        if signal == "WAIT":
            return

        spread_ok, spread = await self.binance.check_spread(session, symbol)
        if not spread_ok:
            print(f"⚠️ Skip {symbol} due to high spread: {spread:.2f}%")
            return

        if price > 10 or price < 0.0001:
            print(f"⚠️ Skip {symbol} karena harga tidak dalam rentang: {price}")
            return

        qty = (
            Decimal(self.config.fixed_usdt_balance * self.config.trading.usdt_percentage * self.config.trading.leverage) /
            Decimal(str(price))
        ).quantize(Decimal('0.001'), rounding=ROUND_DOWN)

        atr_decimal = Decimal(str(atr))
        price_decimal = Decimal(str(price))

        if signal == "LONG":
            tp_price = price_decimal + (atr_decimal * Decimal('1.2'))
            sl_price = price_decimal - (atr_decimal * Decimal('0.8'))
            side = "BUY"
        else:
            tp_price = price_decimal - (atr_decimal * Decimal('1.2'))
            sl_price = price_decimal + (atr_decimal * Decimal('0.8'))
            side = "SELL"

        notional = float(qty) * price

        if notional < 5:
            print(f"⚠️ Notional terlalu kecil untuk {symbol} → {notional:.2f} USDT")
            return

        side = "BUY" if signal == "LONG" else "SELL"
        res = await self.binance.place_order(session, symbol, side, float(qty))

        if "orderId" in res:
            position = Position(
                entry=price,
                qty=float(qty),
                side=side,
                tp_price=tp_price,
                sl_price=float(sl_price),
                timestamp=datetime.now()
            )
            self.trade_manager.add_position(symbol, position)
            self.trade_manager.increment_daily_trade_count()

            print(f"📈 ENTRY {symbol} | Qty: {qty} | Price: {price:.4f}")
            print(f"➡️ TP: {tp_price:.6f}, SL: {sl_price:.6f} (ATR: {atr:.4f})")

            direction = "LONG 🚀" if side == "BUY" else "SHORT 🔻"
            await self.telegram.send_message(
                session,
                f"📈 ENTRY {symbol} | {direction} | Price: {price:.4f} | RSI: {rsi:.2f} | ATR: {atr:.4f}"
            ) 
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
    ) -> Optional[Dict[str, float]]:
        df = await self.binance.get_klines(session, symbol)
        if df.empty or len(df) < 30:
            return None

        # Convert numeric columns to float
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        close = df["close"]
        open_ = df["open"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        last_close = close.iloc[-1]
        last_open = open_.iloc[-1]
        last_high = high.iloc[-1]
        last_low = low.iloc[-1]
        last_volume = float(volume.iloc[-1])

        # Calculate volume average for last 10 candles
        volume_avg10 = float(volume.iloc[-10:].mean())

        # Calculate price change in last 5 minutes
        # Get the most recent 2 candles
        recent_candles = close.iloc[-2:]
        if len(recent_candles) == 2:
            prev_close = recent_candles.iloc[0]
            current_close = recent_candles.iloc[1]
            price_change_5m = ((current_close - prev_close) / prev_close) * 100
        else:
            price_change_5m = 0.0
            print("⚠️ Not enough candles to calculate price change")

        # Detect candle pattern
        candle_pattern = ""
        body_size = abs(last_close - last_open)
        upper_wick = last_high - max(last_open, last_close)
        lower_wick = min(last_open, last_close) - last_low
        total_size = last_high - last_low
        
        if total_size > 0:  # Avoid division by zero
            body_ratio = body_size / total_size
            upper_ratio = upper_wick / total_size
            lower_ratio = lower_wick / total_size
            
            if last_close > last_open:  # Bullish candle
                if body_ratio > 0.6:
                    if upper_ratio < 0.1 and lower_ratio < 0.1:
                        candle_pattern = "Bullish Marubozu"
                    else:
                        candle_pattern = "Strong Bullish"
                elif body_ratio < 0.3:
                    if lower_ratio > 0.6:
                        candle_pattern = "Hammer"
                    elif upper_ratio > 0.6:
                        candle_pattern = "Inverted Hammer"
                    else:
                        candle_pattern = "Doji"
                elif upper_ratio < 0.1 and lower_ratio > 0.4:
                    candle_pattern = "Bullish Engulfing"
            else:  # Bearish candle
                if body_ratio > 0.6:
                    if upper_ratio < 0.1 and lower_ratio < 0.1:
                        candle_pattern = "Bearish Marubozu"
                    else:
                        candle_pattern = "Strong Bearish"
                elif body_ratio < 0.3:
                    if upper_ratio > 0.6:
                        candle_pattern = "Shooting Star"
                    elif lower_ratio > 0.6:
                        candle_pattern = "Hanging Man"
                    else:
                        candle_pattern = "Doji"
                elif lower_ratio < 0.1 and upper_ratio > 0.4:
                    candle_pattern = "Bearish Engulfing"

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

        # Calculate entry confidence score (0-100)
        entry_confidence_score = 0
        if signal != "WAIT":
            # RSI contribution (0-30 points)
            if signal == "LONG":
                rsi_score = max(0, 30 - (rsi - 30))  # Higher score for lower RSI in LONG
            else:
                rsi_score = max(0, 30 - (70 - rsi))  # Higher score for higher RSI in SHORT
            
            # Volume contribution (0-30 points)
            volume_score = min(30, (last_volume / volume_avg10) * 15)
            
            # Trend contribution (0-40 points)
            trend_score = 0
            if signal == "LONG":
                if ema20 > ema50:
                    trend_score = min(40, ((ema20 / ema50 - 1) * 100))
            else:
                if ema20 < ema50:
                    trend_score = min(40, ((1 - ema20 / ema50) * 100))
            
            entry_confidence_score = int(rsi_score + volume_score + trend_score)

        # Generate reason for the signal
        reason = ""
        if signal != "WAIT":
            reasons = []
            # Always add signal type as first reason
            reasons.append(signal)
            
            # Add RSI reason
            if rsi < 30:
                reasons.append(f"RSI {rsi:.1f}")
            elif rsi > 70:
                reasons.append(f"RSI {rsi:.1f}")
            
            # Add EMA reason
            if ema20 > ema50 * 1.01:
                reasons.append("EMA20 > EMA50")
            elif ema20 < ema50 * 0.99:
                reasons.append("EMA20 < EMA50")
            
            # Add BB reason
            if last_close < lower_band * 0.99:
                reasons.append("Price < Lower BB")
            elif last_close > upper_band * 1.01:
                reasons.append("Price > Upper BB")
            
            # Add candle pattern if present
            if candle_pattern:
                reasons.append(candle_pattern)
            
            # If no specific reasons were found, add a default reason
            if len(reasons) == 1:  # Only contains signal type
                reasons.append("Technical Analysis")
            
            reason = " + ".join(reasons)

            # Return data when there is a signal
            # Calculate TP and SL prices based on ATR from settings
            if signal == "LONG":
                tp_price = last_close + (atr * self.config.trading.tp_atr_ratio)
                sl_price = last_close - (atr * self.config.trading.sl_atr_ratio)
            else:  # SHORT
                tp_price = last_close - (atr * self.config.trading.tp_atr_ratio)
                sl_price = last_close + (atr * self.config.trading.sl_atr_ratio)

            # Calculate spread percentage
            spread = ((last_high - last_low) / last_low) * 100

            # Calculate Bollinger Bands width
            bb_width = upper_band - lower_band

            return {
                "symbol": symbol,
                "signal": signal,
                "price": last_close,
                "rsi": rsi,
                "atr": atr,
                "ema20": ema20,
                "ema50": ema50,
                "last_close": last_close,
                "lower_band": lower_band,
                "upper_band": upper_band,
                "is_green": is_green,
                "is_red": is_red,
                "volume_now": last_volume,
                "volume_avg10": volume_avg10,
                "candle_pattern": candle_pattern,
                "entry_confidence_score": entry_confidence_score,
                "reason": reason,
                "price_change_5m": price_change_5m,
                "tp_price": tp_price,
                "sl_price": sl_price,
                "spread": spread,
                "bb_width": bb_width
            }

        return None  # Return None when there is no signal

    def calculate_position_size(self, price: float, atr: float) -> float:
        """Calculate position size based on risk management rules"""
        try:
            # Get available balance
            if self.config.binance.bot_mode == "DEMO":
                balance = Decimal(str(self.config.fixed_usdt_balance))
            else:
                # For real mode, we'll get the actual balance from Binance
                balance = Decimal(str(self.config.fixed_usdt_balance))  # This will be updated with real balance

            # Convert price to Decimal
            price_decimal = Decimal(str(price))

            # Calculate position size based on USDT percentage
            position_size = (balance * Decimal(str(self.config.trading.usdt_percentage)) * Decimal(str(self.config.trading.leverage))) / price_decimal

            # Limit maximum position size to 1000 units
            max_position = Decimal('1000')
            position_size = min(position_size, max_position)

            # Round to appropriate precision
            position_size = float(position_size.quantize(Decimal('0.1')))  # Round to 1 decimal place

            print(f"💰 Balance: {float(balance):.2f} USDT")
            print(f"🎯 Position Size: {position_size:.1f} units")
            return position_size

        except Exception as e:
            print(f"Error calculating position size: {e}")
            return 0.0

    async def process_trade(self, session: aiohttp.ClientSession, trade_data: Dict) -> Optional[Position]:
        """Process a trade based on analysis results"""
        try:
            symbol = trade_data["symbol"]
            signal = trade_data["signal"]
            entry_confidence_score = trade_data["entry_confidence_score"]
            
            # Check if we already have a position for this symbol
            if symbol in self.trade_manager.positions:
                print(f"⚠️ Already have a position for {symbol}")
                return None
            
            # Check if we have enough confidence to trade
            if entry_confidence_score <= 30:
                print(f"⚠️ Confidence score too low ({entry_confidence_score}) for {symbol}, skipping trade")
                return None
            
            # Get current price and calculate position size
            current_price = await self.binance.get_mark_price(session, symbol)
            if current_price <= 0:
                print(f"❌ Invalid price for {symbol}: {current_price}")
                return None
            
            # Calculate position size based on risk management
            balance = await self.binance.get_account_balance(session)
            position_size = self.calculate_position_size(balance, current_price)
            
            if position_size <= 0:
                print(f"❌ Invalid position size for {symbol}: {position_size}")
                return None
            
            # Place the order
            order = await self.binance.place_order(
                session,
                symbol,
                signal,
                position_size
            )
            
            if not order:
                print(f"❌ Failed to place order for {symbol}")
                return None
            
            # Create position object
            position = Position(
                entry=current_price,
                qty=position_size,
                side=signal,
                tp_price=trade_data["tp_price"],
                sl_price=trade_data["sl_price"],
                timestamp=datetime.now(),
                margin=position_size * current_price / self.config.trading.leverage,
                leverage=self.config.trading.leverage,
                mark_price=current_price,
                spread=trade_data["spread"],
                rsi=trade_data["rsi"],
                atr=trade_data["atr"],
                ema20=trade_data["ema20"],
                ema50=trade_data["ema50"],
                last_close=trade_data["last_close"],
                lower_band=trade_data["lower_band"],
                upper_band=trade_data["upper_band"],
                is_green=trade_data["is_green"],
                is_red=trade_data["is_red"],
                signal=trade_data["signal"],
                volume_now=trade_data["volume_now"],
                volume_avg10=trade_data["volume_avg10"],
                reason=trade_data["reason"],
                price_change_5m=trade_data["price_change_5m"],
                candle_pattern=trade_data["candle_pattern"],
                entry_confidence_score=entry_confidence_score
            )
            
            # Add position to manager
            self.trade_manager.add_position(symbol, position)
            
            # Send Telegram notification
            mode_prefix = "🤖 DEMO" if self.config.binance.bot_mode == "DEMO" else "💰 REAL"
            direction = "Long 🚀" if signal == "BUY" else "Short 🔻"
            message = (
                f"<pre>\n"
                f"{mode_prefix} New Position : {symbol} ({direction})\n"
                f"🎯 Entry        : {current_price:.6f}\n"
                f"📦 Size         : {position_size:.1f} {symbol.replace('USDT', '')}\n"
                f"🪙 Margin       : {(position_size * current_price / self.config.trading.leverage):.2f} USDT\n"
                f"📈 Leverage     : {self.config.trading.leverage}x\n\n"
                f"📊 Analysis:\n"
                f"   • RSI        : {trade_data['rsi']:.1f}\n"
                f"   • EMA20      : {trade_data['ema20']:.6f}\n"
                f"   • EMA50      : {trade_data['ema50']:.6f}\n"
                f"   • BB Width   : {trade_data['bb_width']:.6f}\n"
                f"   • Volume     : {trade_data['volume_now']:.1f} vs {trade_data['volume_avg10']:.1f}\n"
                f"   • Pattern    : {trade_data['candle_pattern']}\n"
                f"   • Confidence : {entry_confidence_score:.1f}\n\n"
                f"🎯 TP           : {trade_data['tp_price']:.6f}\n"
                f"🛑 SL           : {trade_data['sl_price']:.6f}\n"
                f"⏰ Time         : {datetime.now().strftime('%H:%M:%S')}\n"
                f"</pre>"
            )
            
            await self.telegram.send_message(session, message)
            
            return position
            
        except Exception as e:
            print(f"❌ Error processing trade: {e}")
            return None 
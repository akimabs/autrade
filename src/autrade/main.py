import asyncio
import ssl
import aiohttp
from datetime import datetime, timedelta, timezone
import os
import csv
import pandas as pd
from typing import Dict

from .config.settings import load_config
from .models.trade import TradeManager
from .services.binance_service import BinanceService
from .services.telegram_service import TelegramService
from .services.trading_service import TradingService
from src.autrade.utils.report import create_trading_report, create_summary_report

class TradingBot:
    def __init__(self):
        self.config = load_config()
        self.trade_manager = TradeManager()
        self.binance_service = BinanceService(self.config, self.trade_manager)
        self.telegram_service = TelegramService(self.config.telegram)
        self.trading_service = TradingService(
            self.config,
            self.binance_service,
            self.telegram_service,
            self.trade_manager
        )
        self.position_messages = {}  # {symbol: message_id}
        self.csv_file = "data/trades.csv"
        self._ensure_csv_exists()

    def _ensure_csv_exists(self):
        """Ensure CSV file exists with headers"""
        os.makedirs("data", exist_ok=True)
        if not os.path.exists(self.csv_file):
            headers = [
                "timestamp", "symbol", "side", "entry_price", "exit_price", "quantity",
                "leverage", "pnl", "roi", "duration", "close_reason", "balance",
                "margin_used", "margin_call_price", "take_profit", "stop_loss",
                "atr", "spread", "signal_mode", "rsi", "ema20", "ema50",
                "last_close", "lower_band", "upper_band", "is_green", "is_red",
                "signal", "volume_now", "volume_avg10", "entry_time", "exit_time",
                "reason", "price_change_5m", "bb_width", "trend_strength",
                "candle_pattern", "entry_confidence_score", "is_win"
            ]
            with open(self.csv_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(headers)
        else:
            # Check if file is empty or has no headers
            with open(self.csv_file, 'r') as f:
                first_line = f.readline().strip()
                if not first_line:  # If file is empty
                    headers = [
                        "timestamp", "symbol", "side", "entry_price", "exit_price", "quantity",
                        "leverage", "pnl", "roi", "duration", "close_reason", "balance",
                        "margin_used", "margin_call_price", "take_profit", "stop_loss",
                        "atr", "spread", "signal_mode", "rsi", "ema20", "ema50",
                        "last_close", "lower_band", "upper_band", "is_green", "is_red",
                        "signal", "volume_now", "volume_avg10", "entry_time", "exit_time",
                        "reason", "price_change_5m", "bb_width", "trend_strength",
                        "candle_pattern", "entry_confidence_score", "is_win"
                    ]
                    with open(self.csv_file, 'w', newline='') as f:
                        writer = csv.writer(f)
                        writer.writerow(headers)

    def save_trade_to_csv(self, trade_data: Dict):
        """Save trade data to CSV file"""
        try:
            # Create DataFrame with trade data
            df = pd.DataFrame([{
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "symbol": trade_data["symbol"],
                "side": trade_data["side"],
                "entry_price": trade_data["entry_price"],
                "exit_price": trade_data["exit_price"],
                "quantity": trade_data["quantity"],
                "leverage": trade_data["leverage"],
                "pnl": trade_data["pnl"],
                "roi": trade_data["roi"],
                "duration": trade_data["duration"],
                "close_reason": trade_data["close_reason"],
                "balance": trade_data["balance"],
                "margin_used": trade_data["margin_used"],
                "margin_call_price": trade_data["margin_call_price"],
                "take_profit": trade_data["take_profit"],
                "stop_loss": trade_data["stop_loss"],
                "atr": trade_data["atr"],
                "spread": trade_data["spread"],
                "signal_mode": trade_data["signal_mode"],
                "rsi": trade_data["rsi"],
                "ema20": trade_data["ema20"],
                "ema50": trade_data["ema50"],
                "last_close": trade_data["last_close"],
                "lower_band": trade_data["lower_band"],
                "upper_band": trade_data["upper_band"],
                "is_green": trade_data["is_green"],
                "is_red": trade_data["is_red"],
                "signal": trade_data["signal"],
                "volume_now": trade_data["volume_now"],
                "volume_avg10": trade_data["volume_avg10"],
                "entry_time": trade_data["entry_time"],
                "exit_time": trade_data["exit_time"],
                "reason": trade_data["reason"],
                "price_change_5m": trade_data["price_change_5m"],
                "bb_width": trade_data["bb_width"],
                "trend_strength": trade_data["trend_strength"],
                "candle_pattern": trade_data["candle_pattern"],
                "entry_confidence_score": trade_data["entry_confidence_score"],
                "is_win": 1 if trade_data["pnl"] > 0 else 0
            }])

            # Save to CSV with proper formatting
            csv_path = "data/trades.csv"
            df.to_csv(csv_path, mode='a', header=not os.path.exists(csv_path), index=False, line_terminator='\n', quoting=csv.QUOTE_ALL)
            print(f"✅ Trade data saved to {csv_path}")

        except Exception as e:
            print(f"❌ Error saving trade data: {e}")
            print(f"Available keys in trade_data: {list(trade_data.keys())}")  # Debug info

    async def update_positions(self, session: aiohttp.ClientSession):
        """Update active positions and check for closures"""
        while True:
            for symbol, position in list(self.trade_manager.positions.items()):
                try:
                    # Get current position from Binance
                    current_position = await self.binance_service.get_position(session, symbol)
                    
                    if not current_position:
                        # Position was closed
                        print(f"\n🔍 Checking closed position for {symbol}...")
                        
                        # Get last trade to determine exit price
                        trades = await self.binance_service.get_trades(session, symbol)
                        if trades:
                            last_trade = trades[0]  # Most recent trade
                            exit_price = float(last_trade['price'])
                            
                            # Calculate PnL
                            qty = abs(float(position.qty))
                            if position.side == "BUY":
                                pnl = (exit_price - position.entry) * qty
                                pnl_pct = ((exit_price - position.entry) / position.entry) * 100
                            else:
                                pnl = (position.entry - exit_price) * qty
                                pnl_pct = ((position.entry - exit_price) / position.entry) * 100
                            
                            roi = (pnl / position.margin) * 100
                            
                            # Calculate duration
                            duration = datetime.now() - position.timestamp
                            duration_str = str(duration).split('.')[0]  # Remove microseconds
                            
                            # Determine close reason
                            close_reason = "TP" if pnl > 0 else "SL"
                            
                            # Get current balance
                            balance = await self.binance_service.get_account_balance(session)
                            
                            # Calculate price change after 5 minutes
                            entry_time = position.timestamp
                            five_min_later = entry_time + timedelta(minutes=5)
                            klines = await self.binance_service.get_klines(
                                session, 
                                symbol, 
                                interval='5m',
                                limit=2
                            )
                            if not klines.empty:
                                price_5m = float(klines.iloc[0]['close'])
                                price_change_5m = ((price_5m - position.entry) / position.entry) * 100
                            else:
                                price_change_5m = 0.0
                            
                            # Calculate BB width
                            bb_width = position.upper_band - position.lower_band
                            
                            # Calculate trend strength (using EMA ratio)
                            trend_strength = position.ema20 / position.ema50 if position.ema50 != 0 else 0
                            
                            # Save trade data
                            self.save_trade_to_csv({
                                'symbol': symbol,
                                'side': position.side,
                                'entry_price': position.entry,
                                'exit_price': exit_price,
                                'quantity': qty,
                                'leverage': position.leverage,
                                'pnl': pnl,
                                'pnl_percent': pnl_pct,
                                'roi': roi,
                                'duration': duration_str,
                                'close_reason': close_reason,
                                'balance': balance,
                                'margin_used': position.margin,
                                'margin_call_price': position.liquidation_price,
                                'take_profit': position.tp_price,
                                'stop_loss': position.sl_price,
                                'atr': position.atr,
                                'spread': position.spread,
                                'signal_mode': self.config.trading.mode,
                                'rsi': position.rsi,
                                'ema20': position.ema20,
                                'ema50': position.ema50,
                                'last_close': position.last_close,
                                'lower_band': position.lower_band,
                                'upper_band': position.upper_band,
                                'is_green': position.is_green,
                                'is_red': position.is_red,
                                'signal': position.signal,
                                'volume_now': position.volume_now,
                                'volume_avg10': position.volume_avg10,
                                'entry_time': position.timestamp,
                                'exit_time': datetime.now(),
                                'reason': position.reason,
                                'price_change_5m': price_change_5m,
                                'bb_width': bb_width,
                                'trend_strength': trend_strength,
                                'candle_pattern': position.candle_pattern,
                                'entry_confidence_score': position.entry_confidence_score
                            })
                            
                            # Send Telegram notification for closed position
                            result_emoji = "✅" if pnl > 0 else "❌"
                            await self.telegram_service.send_message(
                                session,
                                f"{result_emoji} CLOSE {symbol}\n"
                                f"Side: {position.side}\n"
                                f"Entry: {position.entry:.8f}\n"
                                f"Exit: {exit_price:.8f}\n"
                                f"TP: {position.tp_price:.8f} | SL: {position.sl_price:.8f}\n"
                                f"PnL: {pnl:.4f} USDT\n"
                                f"📊 ROI: {roi:.2f}%\n"
                                f"Durasi: {duration_str}"
                            )
                            
                            # Create and send trade result image
                            image_path = f"/tmp/trade_result_{symbol}_{int(datetime.now().timestamp())}.png"
                            create_trading_report(
                                symbol=symbol,
                                pnl=pnl_pct,
                                trade_time=duration_str,
                                output_path=image_path
                            )
                            
                            try:
                                await self.telegram_service.send_photo(
                                    session,
                                    image_path,
                                    caption=f"{symbol} closed with {close_reason.lower()}"
                                )
                            finally:
                                os.remove(image_path)
                            
                            # Remove from active positions
                            self.trade_manager.remove_position(symbol)
                            if symbol in self.position_messages:
                                del self.position_messages[symbol]
                        else:
                            print(f"❌ No trade data found for {symbol}")
                    else:
                        # Update position with current data
                        position.qty = float(current_position['positionAmt'])
                        entry_price = float(current_position['entryPrice'])
                        
                        # Get current mark price
                        current_price = await self.binance_service.get_mark_price(session, symbol)
                        if current_price > 0:
                            position.mark_price = current_price
                            
                        # Calculate liquidation price based on leverage and margin
                        qty = abs(float(position.qty))
                        margin_used = (qty * position.entry) / position.leverage
                        
                        # Check if TP or SL is hit
                        if position.mark_price > 0:  # Ensure we have valid mark price
                            # Add small tolerance (0.01%) to account for spread and price fluctuations
                            tolerance = position.mark_price * 0.0001  # 0.01%
                            close_reason = None
                            
                            if position.side == "BUY":
                                # For long positions
                                if position.mark_price >= (position.tp_price - tolerance):
                                    print(f"🎯 TP hit for {symbol} at {position.mark_price} (TP: {position.tp_price}, Tolerance: {tolerance:.8f})")
                                    close_reason = "TP"
                                    # Close position
                                    await self.binance_service.place_order(
                                        session,
                                        symbol,
                                        "SELL",
                                        abs(position.qty),
                                        reduce_only=True
                                    )
                                elif position.mark_price <= (position.sl_price + tolerance):
                                    print(f"🛑 SL hit for {symbol} at {position.mark_price} (SL: {position.sl_price}, Tolerance: {tolerance:.8f})")
                                    close_reason = "SL"
                                    # Close position
                                    await self.binance_service.place_order(
                                        session,
                                        symbol,
                                        "SELL",
                                        abs(position.qty),
                                        reduce_only=True
                                    )
                            else:
                                # For short positions
                                if position.mark_price <= (position.tp_price + tolerance):
                                    print(f"🎯 TP hit for {symbol} at {position.mark_price} (TP: {position.tp_price}, Tolerance: {tolerance:.8f})")
                                    close_reason = "TP"
                                    # Close position
                                    await self.binance_service.place_order(
                                        session,
                                        symbol,
                                        "BUY",
                                        abs(position.qty),
                                        reduce_only=True
                                    )
                                elif position.mark_price >= (position.sl_price - tolerance):
                                    print(f"🛑 SL hit for {symbol} at {position.mark_price} (SL: {position.sl_price}, Tolerance: {tolerance:.8f})")
                                    close_reason = "SL"
                                    # Close position
                                    await self.binance_service.place_order(
                                        session,
                                        symbol,
                                        "BUY",
                                        abs(position.qty),
                                        reduce_only=True
                                    )
                            
                            if close_reason:
                                # Calculate PnL
                                qty = abs(float(position.qty))
                                if position.side == "BUY":
                                    pnl = (position.mark_price - position.entry) * qty
                                    pnl_pct = ((position.mark_price - position.entry) / position.entry) * 100
                                else:
                                    pnl = (position.entry - position.mark_price) * qty
                                    pnl_pct = ((position.entry - position.mark_price) / position.entry) * 100
                                
                                roi = (pnl / margin_used * 100) if margin_used != 0 else 0
                                
                                # Calculate duration
                                duration = datetime.now() - position.timestamp
                                duration_str = str(duration).split('.')[0]  # Remove microseconds
                                
                                # Get current balance
                                balance = await self.binance_service.get_account_balance(session)
                                
                                # Save trade data
                                self.save_trade_to_csv({
                                    'symbol': symbol,
                                    'side': position.side,
                                    'entry_price': position.entry,
                                    'exit_price': position.mark_price,
                                    'quantity': qty,
                                    'leverage': position.leverage,
                                    'pnl': pnl,
                                    'roi': roi,
                                    'duration': duration_str,
                                    'close_reason': close_reason,
                                    'balance': balance,
                                    'margin_used': margin_used,
                                    'margin_call_price': position.liquidation_price,
                                    'take_profit': position.tp_price,
                                    'stop_loss': position.sl_price,
                                    'atr': position.atr,
                                    'spread': position.spread,
                                    'signal_mode': self.config.trading.mode,
                                    'rsi': position.rsi,
                                    'ema20': position.ema20,
                                    'ema50': position.ema50,
                                    'last_close': position.last_close,
                                    'lower_band': position.lower_band,
                                    'upper_band': position.upper_band,
                                    'is_green': position.is_green,
                                    'is_red': position.is_red,
                                    'signal': position.signal,
                                    'volume_now': position.volume_now,
                                    'volume_avg10': position.volume_avg10,
                                    'entry_time': position.timestamp,
                                    'exit_time': datetime.now(),
                                    'reason': position.reason,
                                    'price_change_5m': position.price_change_5m,
                                    'bb_width': position.upper_band - position.lower_band if position.upper_band and position.lower_band else 0.0,
                                    'trend_strength': position.ema20 / position.ema50 if position.ema20 and position.ema50 else 0.0,
                                    'candle_pattern': position.candle_pattern,
                                    'entry_confidence_score': position.entry_confidence_score
                                })
                                
                                # Send Telegram notification for closed position
                                result_emoji = "✅" if pnl > 0 else "❌"
                                await self.telegram_service.send_message(
                                    session,
                                    f"{result_emoji} CLOSE {symbol}\n"
                                    f"Side: {position.side}\n"
                                    f"Entry: {position.entry:.8f}\n"
                                    f"Exit: {position.mark_price:.8f}\n"
                                    f"TP: {position.tp_price:.8f} | SL: {position.sl_price:.8f}\n"
                                    f"PnL: {pnl:.4f} USDT\n"
                                    f"📊 ROI: {roi:.2f}%\n"
                                    f"Durasi: {duration_str}"
                                )
                                
                                # Create and send trade result image
                                image_path = f"/tmp/trade_result_{symbol}_{int(datetime.now().timestamp())}.png"
                                create_trading_report(
                                    symbol=symbol,
                                    pnl=pnl_pct,
                                    trade_time=duration_str,
                                    output_path=image_path
                                )
                                
                                try:
                                    await self.telegram_service.send_photo(
                                        session,
                                        image_path,
                                        caption=f"{symbol} closed with {close_reason.lower()}"
                                    )
                                finally:
                                    os.remove(image_path)
                                
                                # Remove from active positions
                                self.trade_manager.remove_position(symbol)
                                if symbol in self.position_messages:
                                    del self.position_messages[symbol]
                                
                                continue
                        
                        # Calculate liquidation price with buffer
                        buffer = 0.05  # 5% buffer
                        if position.side == "BUY":
                            # For long positions, liquidation price is lower
                            # Add buffer to make it more realistic
                            liquidation_price = position.entry * (1 - (1 / position.leverage) + buffer)
                        else:
                            # For short positions, liquidation price is higher
                            # Subtract buffer to make it more realistic
                            liquidation_price = position.entry * (1 + (1 / position.leverage) - buffer)
                            
                        # Ensure liquidation price is not zero or negative
                        if liquidation_price <= 0:
                            liquidation_price = position.entry * 0.5  # Set to 50% of entry price as fallback
                            
                        position.liquidation_price = liquidation_price
                        
                        # Validate entry price
                        if entry_price <= 0:
                            print(f"⚠️ Warning: Invalid entry price ({entry_price}) for {symbol}, skipping update")
                            continue
                            
                        position.entry = entry_price
                        
                        # Calculate PnL
                        qty = abs(position.qty)
                        if position.side == "BUY":
                            pnl = (position.mark_price - position.entry) * qty
                            pnl_pct = ((position.mark_price - position.entry) / position.entry * 100)
                        else:
                            pnl = (position.entry - position.mark_price) * qty
                            pnl_pct = ((position.entry - position.mark_price) / position.entry * 100)
                        
                        # Calculate ROI based on margin used
                        roi = (pnl / margin_used * 100) if margin_used != 0 else 0
                        
                        # Calculate duration
                        duration = datetime.now() - position.timestamp
                        duration_str = str(duration).split('.')[0]  # Remove microseconds
                        
                        # Calculate price changes for TP/SL/Margin Call
                        tp_change = ((position.tp_price - position.entry) / position.entry * 100)
                        sl_change = ((position.sl_price - position.entry) / position.entry * 100)
                        mc_change = ((position.liquidation_price - position.entry) / position.entry * 100)
                        
                        # Send Telegram notification for position update
                        mode_prefix = "🤖 DEMO" if self.config.binance.bot_mode == "DEMO" else "💰 REAL"
                        direction = "Long 🚀" if position.side == "BUY" else "Short 🔻"
                        message = (
                            f"<pre>\n"
                            f"{mode_prefix} Posisi Aktif : {symbol} ({direction})\n"
                            f"🎯 Entry        : {position.entry:.6f}\n"
                            f"📦 Size         : {qty:.1f} {symbol.replace('USDT', '')}\n"
                            f"🪙 Margin       : {margin_used:.2f} USDT\n"
                            f"📈 Leverage     : {position.leverage}x ({margin_used:.2f} USDT)\n\n"
                            f"💰 Mark Price   : {position.mark_price:.6f}\n"
                            f"📊 Spread       : {position.spread:.6f}\n\n"
                            f"📊 PNL:\n"
                            f"   • Realized   : {pnl:+.4f} USDT\n"
                            f"   • Percentage : {pnl_pct:+.2f}%\n"
                            f"   • ROI        : {roi:+.2f}%\n\n"
                            f"🎯 TP           : {position.tp_price:.6f} ({tp_change:+.2f}%)\n"
                            f"🛑 SL           : {position.sl_price:.6f} ({sl_change:+.2f}%)\n"
                            f"⚠️ Margin Call  : {position.liquidation_price:.6f} ({mc_change:+.2f}%)\n"
                            f"⏰ Last Update  : {datetime.now().strftime('%H:%M:%S')}\n"
                            f"</pre>"
                        )
                        
                        # Check if we already have a message for this position
                        if symbol in self.position_messages:
                            # Update existing message
                            await self.telegram_service.edit_message(
                                session,
                                self.position_messages[symbol],
                                message
                            )
                        else:
                            # Send new message and store its ID
                            response = await self.telegram_service.send_message(
                                session,
                                message
                            )
                            if response and 'result' in response and 'message_id' in response['result']:
                                self.position_messages[symbol] = response['result']['message_id']
                        
                        print(f"\n📊 Active Position Update:")
                        print(f"Symbol: {symbol}")
                        print(f"Side: {position.side}")
                        print(f"Entry: {position.entry:.8f}")
                        print(f"Size: {qty:.8f}")
                        print(f"Margin: {margin_used:.2f} USDT")
                        print(f"Leverage: {position.leverage}x")
                        print(f"Mark Price: {position.mark_price:.8f}")
                        print(f"Spread: {position.spread:.4f}%")
                        print(f"PnL: {pnl:.2f} USDT ({pnl_pct:.2f}%)")
                        print(f"ROI: {roi:.2f}%")
                        print(f"TP: {position.tp_price:.8f}")
                        print(f"SL: {position.sl_price:.8f}")
                        print(f"Margin Call: {position.liquidation_price:.8f}")
                        print(f"Duration: {duration_str}")
                        
                except Exception as e:
                    print(f"❌ Error updating position {symbol}: {e}")
                    continue
            
            # Wait for 5 seconds before next update
            await asyncio.sleep(5)

    async def bot_loop(self, session: aiohttp.ClientSession):
        while True:
            if self.trade_manager.positions:
                await asyncio.sleep(10)
                continue

            self.trade_manager.reset_daily_counters()

            if (
                self.config.risk.max_daily_trades is not None and 
                self.trade_manager.daily_trade_count >= self.config.risk.max_daily_trades
            ):
                print(f"⚠️ Daily trade limit reached ({self.config.risk.max_daily_trades} trades)")
                await asyncio.sleep(self.config.risk.scan_interval)
                continue
            if (
                self.config.risk.max_consecutive_losses is not None and 
                self.trade_manager.consecutive_losses >= self.config.risk.max_consecutive_losses
            ):
                print(f"⚠️ Trading paused due to {self.trade_manager.consecutive_losses} consecutive losses")
                await asyncio.sleep(self.config.risk.scan_interval)
                continue

            symbols = await self.binance_service.get_symbols(session)
            print("🔍 Scanning market for opportunities...")
            results = await asyncio.gather(*[
                self.trading_service.analyze(session, symbol)
                for symbol in symbols
            ])

            candidates = [r for r in results if r and r["signal"] != "WAIT"]
            if not candidates:
                print("💤 No trading opportunities found, waiting for next scan...")
                await asyncio.sleep(self.config.risk.scan_interval)
                continue

            def signal_strength(item):
                _, _, _, rsi, _ = item
                return abs(rsi - 50)

            # Find the candidate with the strongest signal based on RSI deviation from 50
            strongest_candidate = max(candidates, key=lambda x: abs(x["rsi"] - 50))
            
            # Extract all data from the strongest candidate
            trade_data = strongest_candidate

            # Store RSI and ATR in the position object
            position = await self.trading_service.process_trade(
                session,
                trade_data
            )

            await asyncio.sleep(self.config.risk.scan_interval)

    async def print_summary(self, session: aiohttp.ClientSession, mode: str = "hourly"):
        total = len(self.trade_manager.trades)
        if total == 0:
            print("📊 Belum ada trade untuk disummarize.")
            return

        win = sum(1 for t in self.trade_manager.trades if t['pnl'] > 0)
        loss = total - win
        net_pnl = sum(t['pnl'] for t in self.trade_manager.trades)
        net_pct = (net_pnl / float(self.config.fixed_usdt_balance)) * 100
        winrate = (win / total) * 100
        caption = "Hourly Summary" if mode == "hourly" else "Daily Summary"

        summary_text = (
            f"📊 SUMMARY PER {mode}\n"
            f"🧾 Total Trades : {total}\n"
            f"✅ Win          : {win}\n"
            f"❌ Loss         : {loss}\n"
            f"📈 Winrate      : {winrate:.2f}%\n"
            f"💰 Net PnL      : {net_pnl:.4f} USDT\n"
            f"📊 Net PnL %    : {net_pct:.2f}%\n"
        )

        print(summary_text)
        await self.telegram_service.send_message(session, summary_text)

        image_path = f"/tmp/{mode.lower()}_summary_{int(datetime.now().timestamp())}.png"
        create_summary_report(total, win, loss, winrate, net_pnl, net_pct, image_path, mode=caption)

        try:
            await self.telegram_service.send_photo(session, image_path, caption=caption)
        finally:
            os.remove(image_path)

        if mode.lower().startswith("daily"):
            self.trade_manager.clear_trades()

    async def wait_until(self, hour: int = 7, minute: int = 0):
        now = datetime.now()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        wait_seconds = (target - now).total_seconds()
        await asyncio.sleep(wait_seconds)

    async def hourly_summary_loop(self, session: aiohttp.ClientSession):
        while True:
            await asyncio.sleep(1800)  # 1 hour
            await self.print_summary(session, mode="hourly")

    async def daily_summary_loop(self, session: aiohttp.ClientSession):
        while True:
            await self.wait_until(7, 0)
            await self.print_summary(session, mode="daily")

    async def start_summary_loops(self, session: aiohttp.ClientSession):
        await asyncio.gather(
            self.hourly_summary_loop(session),
            self.daily_summary_loop(session),
        )
        
    async def is_active_hour(self, start_hour=22, end_hour=7):
        now = datetime.now(timezone(timedelta(hours=7)))

        start_time = now.replace(hour=start_hour, minute=0, second=0, microsecond=0)
        end_time = now.replace(hour=end_hour, minute=0, second=0, microsecond=0)

        if start_hour < end_hour:
            # Contoh: aktif antara 08:00 - 17:00
            return start_time <= now < end_time
        else:
            # Contoh: aktif antara 22:00 - 07:00 (melewati tengah malam)
            if now >= start_time:
                return True
            elif now < end_time:
                return True
            else:
                return False

    async def run(self):
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        while True:
            # if await self.is_active_hour(22, 7):
                print("⏰ Aktif! Menjalankan bot...")
                async with aiohttp.ClientSession(
                    connector=aiohttp.TCPConnector(ssl=ssl_context)
                ) as session:
                    # Test API connection first
                    if self.config.binance.bot_mode == "REAL":
                        if not await self.binance_service.test_connection(session):
                            print("❌ API connection test failed. Please check your API key permissions.")
                            await asyncio.sleep(300)
                            continue
                    
                    await asyncio.gather(
                        self.bot_loop(session),
                        self.update_positions(session),
                        self.start_summary_loops(session)
                    )
            # else:
            #     print("🛑 Diluar jam aktif (22:00 - 07:00). Tidur 5 menit...")
            #     await asyncio.sleep(300)  # 5 menit

def main():
    bot = TradingBot()
    asyncio.run(bot.run())

if __name__ == "__main__":
    main() 
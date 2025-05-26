import asyncio
import ssl
import aiohttp
from datetime import datetime, timedelta
import os

from .config.settings import load_config
from .models.trade import TradeManager
from .services.binance_service import BinanceService
from .services.telegram_service import TelegramService
from .services.trading_service import TradingService
from src.autrade.utils.report import create_trading_report, create_summary_report

class TradingBot:
    def __init__(self):
        self.config = load_config()
        self.binance_service = BinanceService(self.config.binance)
        self.telegram_service = TelegramService(self.config.telegram)
        self.trade_manager = TradeManager()
        self.trading_service = TradingService(
            self.config,
            self.binance_service,
            self.telegram_service,
            self.trade_manager
        )
        self.position_messages = {}  # {symbol: message_id}

    async def update_positions(self, session: aiohttp.ClientSession):
        while True:
            if not self.trade_manager.positions:
                await asyncio.sleep(3)
                continue

            for symbol, position in list(self.trade_manager.positions.items()):
                mark_price = await self.binance_service.get_mark_price(session, symbol)
                entry = position.entry
                qty = position.qty
                tp_price = float(position.tp_price)
                sl_price = position.sl_price
                side = position.side

                pnl = (mark_price - entry) * qty if side == "BUY" else (entry - mark_price) * qty
                pnl_pct = ((mark_price - entry) / entry) * 100 if side == "BUY" else ((entry - mark_price) / entry) * 100
                now = datetime.now().strftime("%H:%M:%S")
                tp_pct = ((tp_price - entry) / entry * 100) if side == "BUY" else ((entry - tp_price) / entry * 100)
                sl_pct = ((entry - sl_price) / entry * 100) if side == "BUY" else ((sl_price - entry) / entry * 100)

                msg = (
                    f"<pre>"
                    f"📌 Posisi Aktif : {symbol}\n"
                    f"📥 Side         : {side}\n"
                    f"🎯 Entry        : {entry:.6f}\n"
                    f"📦 Jumlah       : {qty}\n"
                    f"🎯 TP Target    : {tp_price:.6f} ({tp_pct:.2f}%)\n"
                    f"🛑 SL Target    : {sl_price:.6f} ({sl_pct:.2f}%)\n"
                    f"📉 Mark         : {mark_price:.6f}\n"
                    f"💰 PnL          : {pnl:.4f} USDT\n"
                    f"📊 PnL %        : {pnl_pct:.2f}%\n"
                    f"⏰ Last Update  : {now}\n"
                    f"</pre>"
                )

                if symbol in self.position_messages:
                    await self.telegram_service.edit_message(
                        session,
                        self.position_messages[symbol],
                        msg
                    )
                else:
                    res = await session.post(
                        f"{self.telegram_service.base_url}/sendMessage",
                        data={
                            'chat_id': self.telegram_service.config.chat_id,
                            'text': msg,
                            'parse_mode': 'HTML'
                        }
                    )
                    res_json = await res.json()
                    if 'result' in res_json and 'message_id' in res_json['result']:
                        self.position_messages[symbol] = res_json['result']['message_id']

                closed = False
                if side == "BUY":
                    if mark_price >= tp_price:
                        print(f"✨ TP {symbol} at {mark_price:.4f}")
                        await self.binance_service.place_order(session, symbol, "SELL", reduce_only=True)
                        closed = True
                        self.trade_manager.reset_consecutive_losses()
                    elif mark_price <= sl_price:
                        print(f"⛔ SL {symbol} at {mark_price:.4f}")
                        await self.binance_service.place_order(session, symbol, "SELL", reduce_only=True)
                        closed = True
                        self.trade_manager.increment_consecutive_losses()
                else:  # SELL
                    if mark_price <= tp_price:
                        print(f"✨ TP {symbol} at {mark_price:.4f}")
                        await self.binance_service.place_order(session, symbol, "BUY", reduce_only=True)
                        closed = True
                        self.trade_manager.reset_consecutive_losses()
                    elif mark_price >= sl_price:
                        print(f"⛔ SL {symbol} at {mark_price:.4f}")
                        await self.binance_service.place_order(session, symbol, "BUY", reduce_only=True)
                        closed = True
                        self.trade_manager.increment_consecutive_losses()

                if closed:
                    entry_time = position.timestamp
                    exit_time = datetime.now()
                    duration = exit_time - entry_time
                    minutes = int(duration.total_seconds() // 60)
                    seconds = int(duration.total_seconds() % 60)
                    trade_duration = f"{minutes}m {seconds}s"

                    trade = {
                        "symbol": symbol,
                        "entry": entry,
                        "exit": mark_price,
                        "qty": qty,
                        "pnl": pnl,
                        "timestamp": exit_time,
                        "duration": trade_duration
                    }
                    self.trade_manager.add_trade(trade)

                    print(f"✅ CLOSE {symbol} | PnL: {pnl:.4f} | Durasi: {trade_duration}")

                    image_path = f"/tmp/{symbol}_{int(datetime.now().timestamp())}.png"
                    chart_background_path = "./assets/bg.png"
                    create_trading_report(symbol, pnl_pct, trade_duration, image_path, background_path=chart_background_path)
                    await self.telegram_service.send_photo(session, image_path, caption=f"{symbol} closed with {'profit' if pnl > 0 else 'loss'}")
                    os.remove(image_path)

                    await self.telegram_service.send_message(
                        session,
                        f"<pre>"
                        f"✅ CLOSE {symbol}\n"
                        f"📥 Side: {side}\n"
                        f"🎯 Entry: {entry:.6f}\n"
                        f"📈 Exit: {mark_price:.6f}\n"
                        f"🎯 TP: {tp_price:.6f} | 🛑 SL: {sl_price:.6f}\n"
                        f"💰 PnL: {pnl:.4f} USDT\n"
                        f"⏰ Durasi: {trade_duration}"
                        f"</pre>"
                    )

                    self.trade_manager.remove_position(symbol)
                    if symbol in self.position_messages:
                        del self.position_messages[symbol]

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
            results = await asyncio.gather(*[
                self.trading_service.analyze(session, symbol, idx)
                for idx, symbol in enumerate(symbols)
            ])

            candidates = [r for r in results if r and r[1] != "WAIT"]
            if not candidates:
                await asyncio.sleep(self.config.risk.scan_interval)
                continue

            def signal_strength(item):
                _, _, _, rsi, _ = item
                return abs(rsi - 50)

            strongest = max(candidates, key=signal_strength)
            symbol, signal, price, rsi, atr = strongest

            await self.trading_service.process_trade(
                session,
                symbol,
                signal,
                price,
                rsi,
                atr
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
        now = datetime.now().time()
        if start_hour < end_hour:
            return start_hour <= now.hour < end_hour
        else:
            return now.hour >= start_hour or now.hour < end_hour

    async def run(self):
        while True:
            if await self.is_active_hour(22, 7):
                print("⏰ Aktif! Menjalankan bot...")
                async with aiohttp.ClientSession(
                    connector=aiohttp.TCPConnector(ssl=ssl._create_unverified_context())
                ) as session:
                    await asyncio.gather(
                        self.bot_loop(session),
                        self.update_positions(session),
                        self.start_summary_loops(session)
                    )
            else:
                print("🛑 Diluar jam aktif (22:00 - 07:00). Tidur 5 menit...")
                await asyncio.sleep(300)  # 5 menit

def main():
    bot = TradingBot()
    asyncio.run(bot.run())

if __name__ == "__main__":
    main() 
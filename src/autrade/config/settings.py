from dataclasses import dataclass
from typing import Optional
from decimal import Decimal
import os
from dotenv import load_dotenv

@dataclass
class TradingConfig:
    mode: str
    leverage: int
    usdt_percentage: float
    tp_atr_ratio: float  # TP distance in ATR units
    sl_atr_ratio: float  # SL distance in ATR units

@dataclass
class RiskConfig:
    max_spread_percent: float
    max_consecutive_losses: int
    max_daily_trades: int
    min_atr_ratio: float
    scan_interval: int

@dataclass
class TelegramConfig:
    token: str
    chat_id: str

@dataclass
class BinanceConfig:
    api_key: str
    api_secret: str
    base_url: str
    bot_mode: str

@dataclass
class Config:
    trading: TradingConfig
    risk: RiskConfig
    telegram: TelegramConfig
    binance: BinanceConfig
    fixed_usdt_balance: Decimal

def load_config() -> Config:
    load_dotenv()
    
    # Bot mode configuration
    bot_mode = os.getenv("BOT_MODE", "DEMO").upper()  # Default to DEMO if not set
    if bot_mode not in ["DEMO", "REAL"]:
        print(f"⚠️ Invalid BOT_MODE: {bot_mode}. Defaulting to DEMO mode.")
        bot_mode = "DEMO"
    print(f"🤖 Bot Mode: {bot_mode}")
    
    # Trading mode configuration
    trading_mode = os.getenv("TRADING_MODE", "balanced")
    if trading_mode == "safe":
        trading_config = TradingConfig(
            mode="safe",
            leverage=1,
            usdt_percentage=1,
            tp_atr_ratio=2.0,  # TP at 2 ATR
            sl_atr_ratio=1.0   # SL at 1 ATR
        )
    elif trading_mode == "balanced":
        trading_config = TradingConfig(
            mode="balanced",
            leverage=1,
            usdt_percentage=1,
            tp_atr_ratio=1.5,  # TP at 1.5 ATR
            sl_atr_ratio=0.75  # SL at 0.75 ATR
        )
    elif trading_mode == "aggressive":
        trading_config = TradingConfig(
            mode="aggressive",
            leverage=1,
            usdt_percentage=1,
            tp_atr_ratio=1.0,  # TP at 1.0 ATR
            sl_atr_ratio=0.5   # SL at 0.5 ATR
        )
    else:
        raise ValueError(f"Unknown TRADING_MODE: {trading_mode}")

    # Risk configuration
    risk_config = RiskConfig(
        max_spread_percent=0.15,
        max_consecutive_losses=3,
        max_daily_trades=None,
        min_atr_ratio=0.005,
        scan_interval=30
    )

    # Telegram configuration
    telegram_config = TelegramConfig(
        token=os.getenv("TELEGRAM_TOKEN", ""),
        chat_id=os.getenv("TELEGRAM_CHAT_ID", "")
    )

    # Binance configuration
    binance_config = BinanceConfig(
        api_key=os.getenv("BINANCE_API_KEY", ""),
        api_secret=os.getenv("BINANCE_API_SECRET", ""),
        base_url="https://fapi.binance.com",
        bot_mode=bot_mode
    )

    # Get fixed USDT balance from environment variable
    fixed_usdt_balance = os.getenv("FIXED_USDT_BALANCE", "100")
    return Config(
        trading=trading_config,
        risk=risk_config,
        telegram=telegram_config,
        binance=binance_config,
        fixed_usdt_balance=Decimal(fixed_usdt_balance)
    ) 
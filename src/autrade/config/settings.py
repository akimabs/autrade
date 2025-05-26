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
    tp_percent: float
    sl_percent: float

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

@dataclass
class Config:
    trading: TradingConfig
    risk: RiskConfig
    telegram: TelegramConfig
    binance: BinanceConfig
    fixed_usdt_balance: Decimal

def load_config() -> Config:
    load_dotenv()
    
    # Trading mode configuration
    trading_mode = os.getenv("TRADING_MODE", "balanced")
    if trading_mode == "safe":
        trading_config = TradingConfig(
            mode="safe",
            leverage=1,
            usdt_percentage=1,
            tp_percent=0.5,
            sl_percent=0.3
        )
    elif trading_mode == "balanced":
        trading_config = TradingConfig(
            mode="balanced",
            leverage=10,
            usdt_percentage=1,
            tp_percent=1.0,
            sl_percent=0.5
        )
    elif trading_mode == "aggressive":
        trading_config = TradingConfig(
            mode="aggressive",
            leverage=25,
            usdt_percentage=1,
            tp_percent=0.6,
            sl_percent=0.3
        )
    else:
        raise ValueError(f"Unknown TRADING_MODE: {trading_mode}")

    # Risk configuration
    risk_config = RiskConfig(
        max_spread_percent=0.15,
        max_consecutive_losses=None,
        max_daily_trades=None,
        min_atr_ratio=0.005,
        scan_interval=60
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
        base_url="https://fapi.binance.com"
    )

    # Get fixed USDT balance from environment variable
    fixed_usdt_balance = os.getenv("FIXED_USDT_BALANCE", "100")  # Default to 100 USDT if not set
    return Config(
        trading=trading_config,
        risk=risk_config,
        telegram=telegram_config,
        binance=binance_config,
        fixed_usdt_balance=Decimal(fixed_usdt_balance)
    ) 
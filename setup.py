from setuptools import setup, find_packages

setup(
    name="autrade",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "aiohttp",
        "pandas",
        "ta",
        "python-telegram-bot",
        "python-binance",
        "matplotlib",
        "seaborn"
    ],
    author="Your Name",
    author_email="your.email@example.com",
    description="""
    Automated Trading Bot for Cryptocurrency Markets

    Data Sources and Parameters:
    1. Market Data (from Binance API):
       - OHLCV (Open, High, Low, Close, Volume) data
       - Current price and order book data
       - Account balance and position information
       - Trade history and execution details

    2. Technical Indicators:
       - RSI (Relative Strength Index): 14-period default
       - EMA (Exponential Moving Average): 20 and 50 periods
       - Bollinger Bands: 20-period with 2 standard deviations
       - ATR (Average True Range): 14-period for volatility

    3. Trading Parameters:
       - Entry/Exit signals based on:
         * RSI levels (30/70 for conservative, 45/55 for moderate)
         * EMA crossovers (20/50 period)
         * Bollinger Band breakouts
         * Candle patterns (Engulfing, Marubozu, Hammer, Shooting Star)
       - Risk Management:
         * Position sizing based on ATR and account balance
         * Take Profit and Stop Loss levels using ATR ratios
         * Maximum daily trades limit
         * Consecutive losses limit
         * Spread monitoring

    4. Performance Metrics:
       - PnL (Profit and Loss) tracking
       - ROI (Return on Investment) calculation
       - Win rate statistics
       - Trade duration monitoring
       - Volume analysis (current vs 10-period average)

    5. Additional Features:
       - Telegram notifications for trade signals and updates
       - CSV logging of all trades with detailed metrics:
         * Timestamp and Symbol information
         * Trade Details:
           - Side (BUY/SELL)
           - Entry and Exit prices
           - Quantity and Leverage
           - PnL and ROI percentages
           - Trade duration
           - Close reason (TP/SL)
         * Account Metrics:
           - Balance
           - Margin used
           - Margin call price
           - Take profit and Stop loss levels
         * Technical Analysis:
           - ATR and Spread
           - Signal mode
           - RSI, EMA20, EMA50 values
           - Bollinger Bands (upper/lower)
           - Candle colors (is_green/is_red)
         * Volume Analysis:
           - Current volume
           - 10-period volume average
         * Trade Timing:
           - Entry and Exit timestamps
         * Signal Information:
           - Trading signal
           - Reason for entry
           - 5-minute price change
           - BB width
           - Trend strength
           - Candle pattern
           - Entry confidence score
       - Real-time position monitoring
       - Automated summary reports (hourly/daily)
    """,
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/autrade",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.7",
) 
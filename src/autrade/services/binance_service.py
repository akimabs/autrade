import hmac
import hashlib
import urllib.parse
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import aiohttp
import pandas as pd
from decimal import Decimal, ROUND_DOWN

from ..config.settings import BinanceConfig

class BinanceService:
    def __init__(self, config: BinanceConfig):
        self.config = config

    def _sign(self, query: str) -> str:
        return hmac.new(
            self.config.api_secret.encode(),
            query.encode(),
            hashlib.sha256
        ).hexdigest()

    async def request(
        self,
        session: aiohttp.ClientSession,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None
    ) -> Dict:
        if params is None:
            params = {}
        
        params['timestamp'] = int(datetime.now().timestamp() * 1000)
        query = urllib.parse.urlencode(params)
        sig = self._sign(query)
        url = f"{self.config.base_url}{endpoint}?{query}&signature={sig}"
        headers = {"X-MBX-APIKEY": self.config.api_key}
        
        async with getattr(session, method.lower())(url, headers=headers) as resp:
            return await resp.json()

    async def get_klines(
        self,
        session: aiohttp.ClientSession,
        symbol: str,
        interval: str = '5m',
        limit: int = 1500
    ) -> pd.DataFrame:
        try:
            data = await self.request(
                session,
                'GET',
                '/fapi/v1/klines',
                {'symbol': symbol, 'interval': interval, 'limit': limit}
            )
            
            df = pd.DataFrame(
                data,
                columns=[
                    "timestamp", "open", "high", "low", "close", "volume",
                    "close_time", "quote_volume", "num_trades",
                    "taker_base_vol", "taker_quote_vol", "ignore"
                ]
            )
            
            for col in ["open", "high", "low", "close"]:
                df[col] = df[col].astype(float)
                
            return df
        except Exception as e:
            print(f"Error getting klines for {symbol}: {e}")
            return pd.DataFrame()

    async def get_symbols(self, session: aiohttp.ClientSession) -> List[str]:
        try:
            info = await self.request(session, 'GET', '/fapi/v1/exchangeInfo')
            all_symbols = [
                s['symbol'] for s in info['symbols']
                if s['contractType'] == 'PERPETUAL'
                and s['status'] == 'TRADING'
                and s['quoteAsset'] == 'USDT'
            ]

            ticker_data = await self.request(session, 'GET', '/fapi/v1/ticker/24hr')
            ticker_map = {
                t['symbol']: float(t['quoteVolume'])
                for t in ticker_data
                if t['symbol'] in all_symbols
            }
            
            return sorted(ticker_map, key=ticker_map.get, reverse=True)[:50]
        except Exception as e:
            print(f"Error getting symbols: {e}")
            return []

    async def check_spread(
        self,
        session: aiohttp.ClientSession,
        symbol: str
    ) -> Tuple[bool, float]:
        try:
            ticker = await self.request(
                session,
                'GET',
                '/fapi/v1/ticker/bookTicker',
                {'symbol': symbol}
            )
            bid = float(ticker['bidPrice'])
            ask = float(ticker['askPrice'])
            spread = ((ask - bid) / bid) * 100
            return spread < 0.15, spread  # 0.15 is max spread percent
        except Exception as e:
            print(f"Error checking spread for {symbol}: {e}")
            return False, 0

    async def get_mark_price(
        self,
        session: aiohttp.ClientSession,
        symbol: str
    ) -> float:
        try:
            response = await self.request(
                session,
                'GET',
                '/fapi/v1/ticker/price',
                {'symbol': symbol}
            )
            return float(response['price'])
        except Exception as e:
            print(f"Error getting mark price for {symbol}: {e}")
            return 0.0

    async def place_order(
        self,
        session: aiohttp.ClientSession,
        symbol: str,
        side: str,
        qty: Optional[float] = None,
        reduce_only: bool = False
    ) -> Dict:
        # This is a simulated order placement
        print(f"[SIMULATED ORDER] {side} {symbol} | Qty: {qty} | ReduceOnly: {reduce_only}")
        return {"orderId": f"SIM-{datetime.now().timestamp()}"} 
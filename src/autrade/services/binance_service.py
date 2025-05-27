import hmac
import hashlib
import urllib.parse
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import aiohttp
import pandas as pd
from decimal import Decimal, ROUND_DOWN
import ssl

from ..config.settings import BinanceConfig

class BinanceService:
    def __init__(self, config: BinanceConfig):
        self.config = config
        # Create SSL context
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE

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
        
        params['timestamp'] = int(time.time() * 1000)
        query = urllib.parse.urlencode(params)
        signature = self._sign(query)
        url = f"{self.config.base_url}{endpoint}?{query}&signature={signature}"

        headers = {
            "X-MBX-APIKEY": self.config.api_key
        }

        try:
            async with session.request(method.upper(), url, headers=headers) as resp:
                text = await resp.text()

                if resp.status != 200:
                    return {"error": f"HTTP {resp.status}: {text}"}

                try:
                    return await resp.json()
                except Exception as e:
                    return {"error": f"JSON error: {str(e)}, Body: {text}"}
        except Exception as e:
            return {"error": str(e)}

    async def get_klines(self, session: aiohttp.ClientSession, symbol: str, interval: str = '5m', limit: int = 1500) -> pd.DataFrame:
        try:
            data = await self.request(session, 'GET', '/fapi/v1/klines', {
                'symbol': symbol, 'interval': interval, 'limit': limit
            })

            df = pd.DataFrame(data, columns=[
                "timestamp", "open", "high", "low", "close", "volume",
                "close_time", "quote_volume", "num_trades",
                "taker_base_vol", "taker_quote_vol", "ignore"
            ])
            for col in ["open", "high", "low", "close"]:
                df[col] = df[col].astype(float)
            return df
        except Exception as e:
            print(f"Error getting klines: {e}")
            return pd.DataFrame()

    async def get_symbols(self, session: aiohttp.ClientSession) -> List[str]:
        try:
            info = await self.request(session, 'GET', '/fapi/v1/exchangeInfo')
            all_symbols = [
                s['symbol'] for s in info['symbols']
                if s['contractType'] == 'PERPETUAL' and s['status'] == 'TRADING' and s['quoteAsset'] == 'USDT'
            ]

            ticker_data = await self.request(session, 'GET', '/fapi/v1/ticker/24hr')
            ticker_map = {
                t['symbol']: float(t['quoteVolume'])
                for t in ticker_data if t['symbol'] in all_symbols
            }
            return sorted(ticker_map, key=ticker_map.get, reverse=True)[:50]
        except Exception as e:
            print(f"Error getting symbols: {e}")
            return []

    async def check_spread(self, session: aiohttp.ClientSession, symbol: str) -> Tuple[bool, float]:
        try:
            ticker = await self.request(session, 'GET', '/fapi/v1/ticker/bookTicker', {'symbol': symbol})
            bid = float(ticker['bidPrice'])
            ask = float(ticker['askPrice'])
            spread = ((ask - bid) / bid) * 100
            return spread < 0.15, spread
        except Exception as e:
            print(f"Error checking spread: {e}")
            return False, 0

    async def get_mark_price(self, session: aiohttp.ClientSession, symbol: str) -> float:
        try:
            response = await self.request(session, 'GET', '/fapi/v1/ticker/price', {'symbol': symbol})
            return float(response['price'])
        except Exception as e:
            print(f"Error getting mark price: {e}")
            return 0.0

    async def test_connection(self, session: aiohttp.ClientSession) -> bool:
        try:
            print("\n🔍 Testing Binance API connection...")
            response = await self.request(session, 'GET', '/fapi/v2/account')  # Changed to v2
            if "error" in response:
                print(f"❌ API Error: {response['error']}")
                return False

            if response.get('canTrade'):
                print("✅ API Key valid with trading permissions")
                return True
            else:
                print("❌ No trading permission")
                return False
        except Exception as e:
            print(f"❌ Connection error: {e}")
            return False

    async def set_leverage(self, session: aiohttp.ClientSession, symbol: str, leverage: int) -> bool:
        try:
            response = await self.request(session, 'POST', '/fapi/v1/leverage', {
                'symbol': symbol, 'leverage': leverage
            })
            return 'leverage' in response
        except Exception as e:
            print(f"Error setting leverage: {e}")
            return False

    async def place_order(
        self,
        session: aiohttp.ClientSession,
        symbol: str,
        side: str,
        qty: Optional[float] = None,
        reduce_only: bool = False
    ) -> Dict:
        if self.config.bot_mode == "DEMO":
            print(f"[DEMO] {side} {symbol} qty={qty} reduceOnly={reduce_only}")
            return {
                "orderId": f"DEMO-{int(datetime.now().timestamp())}",
                "symbol": symbol,
                "side": side,
                "type": "MARKET",
                "quantity": qty,
                "reduceOnly": reduce_only,
                "status": "FILLED"
            }

        try:
            leverage_set = await self.set_leverage(session, symbol, self.config.trading.leverage)
            if not leverage_set:
                return {"error": "Failed to set leverage"}

            params = {
                'symbol': symbol,
                'side': side,
                'type': 'MARKET',
                'quantity': qty,
                'reduceOnly': reduce_only
            }

            response = await self.request(session, 'POST', '/fapi/v1/order', params)
            if 'orderId' in response:
                print(f"✅ Order success: {response}")
            else:
                print(f"❌ Order failed: {response}")
            return response
        except Exception as e:
            return {"error": str(e)}

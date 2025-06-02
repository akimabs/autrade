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
import asyncio

from ..config.settings import Config

class BinanceService:
    def __init__(self, config: Config, trade_manager=None):
        self.config = config
        self.trade_manager = trade_manager
        # Create SSL context
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE

    def _sign(self, query: str) -> str:
        return hmac.new(
            self.config.binance.api_secret.encode(),
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
        url = f"{self.config.binance.base_url}{endpoint}?{query}&signature={signature}"

        headers = {
            "X-MBX-APIKEY": self.config.binance.api_key
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

    async def get_symbol_precision(self, session: aiohttp.ClientSession, symbol: str) -> int:
        try:
            info = await self.request(session, 'GET', '/fapi/v1/exchangeInfo')
            for s in info['symbols']:
                if s['symbol'] == symbol:
                    for f in s['filters']:
                        if f['filterType'] == 'LOT_SIZE':
                            step_size = float(f['stepSize'])
                            precision = 0
                            while step_size < 1:
                                step_size *= 10
                                precision += 1
                            return precision
            return 3  # Default precision if not found
        except Exception as e:
            print(f"Error getting symbol precision: {e}")
            return 3  # Default precision on error

    async def get_account_balance(self, session: aiohttp.ClientSession) -> float:
        try:
            response = await self.request(session, 'GET', '/fapi/v2/account')
            if "error" in response:
                print(f"❌ Error getting balance: {response['error']}")
                return 0.0

            for asset in response.get('assets', []):
                if asset['asset'] == 'USDT':
                    return float(asset['walletBalance'])
            return 0.0
        except Exception as e:
            print(f"❌ Error getting balance: {e}")
            return 0.0

    async def get_price_precision(self, session: aiohttp.ClientSession, symbol: str) -> int:
        try:
            info = await self.request(session, 'GET', '/fapi/v1/exchangeInfo')
            for s in info['symbols']:
                if s['symbol'] == symbol:
                    for f in s['filters']:
                        if f['filterType'] == 'PRICE_FILTER':
                            tick_size = float(f['tickSize'])
                            precision = 0
                            while tick_size < 1:
                                tick_size *= 10
                                precision += 1
                            return precision
            return 8  # Default precision if not found
        except Exception as e:
            print(f"Error getting price precision: {e}")
            return 8  # Default precision on error

    async def cancel_all_orders(self, session: aiohttp.ClientSession, symbol: str) -> bool:
        try:
            print(f"\n🔄 Canceling all orders for {symbol}...")
            response = await self.request(session, 'DELETE', '/fapi/v1/allOpenOrders', {'symbol': symbol})
            if 'error' in response:
                print(f"❌ Error canceling orders: {response['error']}")
                return False
            
            # Check if orders were actually canceled
            open_orders = await self.request(session, 'GET', '/fapi/v1/openOrders', {'symbol': symbol})
            if isinstance(open_orders, list) and len(open_orders) == 0:
                print(f"✅ Successfully canceled all orders for {symbol}")
                return True
            else:
                print(f"⚠️ Some orders might still be open for {symbol}")
                return False
        except Exception as e:
            print(f"❌ Error canceling orders: {e}")
            return False

    async def get_position(self, session: aiohttp.ClientSession, symbol: str) -> Optional[Dict]:
        try:
            if self.config.binance.bot_mode == "DEMO":
                # For demo mode, we'll simulate an open position
                # Get the actual position data from trade manager
                position = self.trade_manager.positions.get(symbol)
                if not position:
                    return None
                    
                return {
                    'symbol': symbol,
                    'positionAmt': str(position.qty),
                    'entryPrice': str(position.entry),
                    'markPrice': str(position.mark_price),
                    'unRealizedProfit': '0.0',
                    'liquidationPrice': str(position.liquidation_price),
                    'leverage': str(position.leverage),
                    'isolated': False,
                    'isAutoAddMargin': False,
                    'positionSide': 'BOTH',
                    'notional': str(abs(float(position.qty) * float(position.entry))),
                    'isolatedWallet': '0.0',
                    'updateTime': int(datetime.now().timestamp() * 1000)
                }
            
            # Only make API call if not in demo mode
            response = await self.request(session, 'GET', '/fapi/v2/positionRisk', {'symbol': symbol})
            if 'error' in response:
                print(f"❌ Error getting position: {response['error']}")
                return None
            
            for position in response:
                if position['symbol'] == symbol and float(position['positionAmt']) != 0:
                    return position
            return None
        except Exception as e:
            print(f"❌ Error getting position: {e}")
            return None

    async def get_trades(self, session: aiohttp.ClientSession, symbol: str) -> List[Dict]:
        """Get recent trades for a symbol"""
        try:
            response = await self.request(session, 'GET', '/fapi/v1/userTrades', {'symbol': symbol})
            if 'error' in response:
                print(f"❌ Error getting trades: {response['error']}")
                return []
            
            # Sort trades by time in descending order (newest first)
            trades = sorted(response, key=lambda x: int(x['time']), reverse=True)
            return trades
        except Exception as e:
            print(f"❌ Error getting trades: {e}")
            return []

    async def place_order(
        self,
        session: aiohttp.ClientSession,
        symbol: str,
        side: str,
        qty: Optional[float] = None,
        reduce_only: bool = False,
        tp_price: Optional[float] = None,
        sl_price: Optional[float] = None
    ) -> Dict:
        print(f"\n📊 Placing {self.config.binance.bot_mode} order:")
        print(f"Symbol: {symbol}")
        print(f"Side: {side}")
        print(f"Quantity: {qty}")
        print(f"Reduce Only: {reduce_only}")
        if tp_price:
            print(f"Take Profit: {tp_price}")
        if sl_price:
            print(f"Stop Loss: {sl_price}")

        if self.config.binance.bot_mode == "DEMO":
            # In demo mode, just return a mock response without making any API calls
            order_response = {
                "orderId": f"DEMO-{int(datetime.now().timestamp())}",
                "symbol": symbol,
                "side": side,
                "type": "MARKET",
                "quantity": qty,
                "reduceOnly": reduce_only,
                "status": "FILLED",
                "price": "0.0",  # Mock price
                "executedQty": str(qty),
                "time": int(datetime.now().timestamp() * 1000)
            }
            print(f"✅ DEMO Order placed successfully: {order_response}")
            return order_response

        try:
            # Cancel all existing orders only if reduce_only = True
            if reduce_only:
                print(f"🔄 Canceling all open orders for {symbol} before reduce-only order...")
                await self.cancel_all_orders(session, symbol)

            # Get symbol precision and round quantity
            qty_precision = await self.get_symbol_precision(session, symbol)
            price_precision = await self.get_price_precision(session, symbol)
            
            if qty is not None:
                qty = round(qty, qty_precision)
                print(f"Adjusted quantity to {qty_precision} decimals: {qty}")
            else:
                print("❌ Error: Quantity is required")
                return {"error": "Quantity is required"}

            # Get balance
            balance = await self.get_account_balance(session)
            print(f"💰 Current Balance: {balance:.2f} USDT")

            # Set leverage
            leverage_set = await self.set_leverage(session, symbol, self.config.trading.leverage)
            if not leverage_set:
                print("❌ Failed to set leverage")
                return {"error": "Failed to set leverage"}

            # Place entry/reduce-only order
            entry_params = {
                'symbol': symbol,
                'side': side,
                'type': 'MARKET',
                'quantity': str(qty),
                'reduceOnly': reduce_only
            }

            entry_response = await self.request(session, 'POST', '/fapi/v1/order', entry_params)
            if 'orderId' not in entry_response:
                print(f"❌ Entry order failed: {entry_response}")
                return entry_response

            print(f"✅ Entry order placed successfully: {entry_response}")

            # If reduce-only, no TP/SL needed
            if reduce_only:
                return entry_response

            # Add delay
            await asyncio.sleep(1)

            # Get current price
            current_price = await self.get_mark_price(session, symbol)
            print(f"Current price before placing TP/SL: {current_price}")

            buffer = 0.0001

            # TP Order
            if tp_price:
                tp_side = "SELL" if side == "BUY" else "BUY"
                tp_price_rounded = round(tp_price, price_precision)
                if (side == "BUY" and current_price >= tp_price - buffer) or (side == "SELL" and current_price <= tp_price + buffer):
                    print(f"⚠️ TP price {tp_price_rounded} too close to current price {current_price}, skipping TP order")
                else:
                    tp_params = {
                        'symbol': symbol,
                        'side': tp_side,
                        'type': 'TAKE_PROFIT_MARKET',
                        'quantity': str(qty),
                        'stopPrice': str(tp_price_rounded),
                        'closePosition': True
                    }
                    tp_response = await self.request(session, 'POST', '/fapi/v1/order', tp_params)
                    if 'orderId' in tp_response:
                        print(f"✅ TP order placed successfully: {tp_response}")
                    else:
                        print(f"❌ TP order failed: {tp_response}")

            # SL Order
            if sl_price:
                sl_side = "SELL" if side == "BUY" else "BUY"
                sl_price_rounded = round(sl_price, price_precision)
                if (side == "BUY" and current_price <= sl_price + buffer) or (side == "SELL" and current_price >= sl_price - buffer):
                    print(f"⚠️ SL price {sl_price_rounded} too close to current price {current_price}, skipping SL order")
                else:
                    sl_params = {
                        'symbol': symbol,
                        'side': sl_side,
                        'type': 'STOP_MARKET',
                        'quantity': str(qty),
                        'stopPrice': str(sl_price_rounded),
                        'closePosition': True
                    }
                    sl_response = await self.request(session, 'POST', '/fapi/v1/order', sl_params)
                    if 'orderId' in sl_response:
                        print(f"✅ SL order placed successfully: {sl_response}")
                    else:
                        print(f"❌ SL order failed: {sl_response}")

            return entry_response

        except Exception as e:
            print(f"❌ Error placing order: {str(e)}")
            return {"error": str(e)}
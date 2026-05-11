"""
Bybit V5 API Client
Referência: https://bybit-exchange.github.io/docs/v5/intro
Assinatura: HMAC-SHA256(timestamp + apiKey + recvWindow + queryString/body)
"""
import hmac, hashlib, time, json, asyncio
from urllib.parse import urlencode
from typing import Optional, List
import aiohttp

from app.config import settings
from app.utils.logger import get_logger

log = get_logger("bybit")
BASE = "https://api.bybit.com"
RECV = "5000"

# Mapa de intervalos Binance → Bybit
INTERVAL_MAP = {
    "1m": "1", "3m": "3", "5m": "5", "15m": "15", "30m": "30",
    "1h": "60", "2h": "120", "4h": "240", "6h": "360",
    "12h": "720", "1d": "D", "1w": "W",
}


def sign(secret: str, ts: str, key: str, payload: str) -> str:
    raw = ts + key + RECV + payload
    return hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()


def auth_headers(key: str, secret: str, payload: str) -> dict:
    ts = str(int(time.time() * 1000))
    return {
        "X-BAPI-API-KEY":     key,
        "X-BAPI-TIMESTAMP":   ts,
        "X-BAPI-SIGN":        sign(secret, ts, key, payload),
        "X-BAPI-RECV-WINDOW": RECV,
        "Content-Type":       "application/json",
    }


class BybitClient:
    def __init__(self):
        self.key     = settings.API_KEY
        self.secret  = settings.API_SECRET
        self.session: Optional[aiohttp.ClientSession] = None
        log.info(f"🔑 Bybit key: {self.key[:8]}... ({len(self.key)} chars)")
        log.info(f"🔐 Secret: ({len(self.secret)} chars)")

    async def _sess(self) -> aiohttp.ClientSession:
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def _get(self, path: str, params: dict = None, auth: bool = False) -> dict:
        qs  = urlencode(sorted((params or {}).items()))
        url = f"{BASE}{path}?{qs}" if qs else f"{BASE}{path}"
        hdrs = auth_headers(self.key, self.secret, qs) if auth else {}
        s = await self._sess()
        async with s.get(url, headers=hdrs, timeout=aiohttp.ClientTimeout(total=10)) as r:
            raw = await r.text()
            try:
                data = json.loads(raw)
            except Exception:
                raise Exception(f"Non-JSON response: {raw[:200]}")
            rc = data.get("retCode", 0)
            if rc != 0:
                raise Exception(f"Bybit {rc}: {data.get('retMsg', '')}")
            return data.get("result", {})

    async def _post(self, path: str, body: dict = None) -> dict:
        bstr = json.dumps(body or {}, separators=(',', ':'))
        hdrs = auth_headers(self.key, self.secret, bstr)
        s = await self._sess()
        async with s.post(f"{BASE}{path}", headers=hdrs, data=bstr,
                          timeout=aiohttp.ClientTimeout(total=10)) as r:
            raw = await r.text()
            try:
                data = json.loads(raw)
            except Exception:
                raise Exception(f"Non-JSON response: {raw[:200]}")
            rc = data.get("retCode", 0)
            if rc != 0:
                raise Exception(f"Bybit {rc}: {data.get('retMsg', '')}")
            return data.get("result", {})

    # ── Public endpoints (sem auth) ───────────────────────────
    async def ping(self) -> bool:
        try:
            await self._get("/v5/market/time")
            return True
        except Exception:
            return False

    async def get_klines(self, symbol: str, interval: str = "5m",
                         limit: int = 200) -> List[list]:
        data = await self._get("/v5/market/kline", {
            "category": "linear",
            "symbol":   symbol,
            "interval": INTERVAL_MAP.get(interval, "5"),
            "limit":    str(limit),
        })
        # Bybit retorna do mais recente para o mais antigo — invertemos
        klines = list(reversed(data.get("list", [])))
        # Formato: [timestamp, open, high, low, close, volume, turnover]
        return klines

    async def get_orderbook(self, symbol: str, limit: int = 20) -> dict:
        data = await self._get("/v5/market/orderbook", {
            "category": "linear", "symbol": symbol, "limit": str(limit),
        })
        return {"bids": data.get("b", []), "asks": data.get("a", [])}

    async def get_ticker(self, symbol: str) -> dict:
        data = await self._get("/v5/market/tickers", {
            "category": "linear", "symbol": symbol,
        })
        lst = data.get("list", [{}])
        return lst[0] if lst else {}

    # ── Private endpoints (com auth) ──────────────────────────
    async def get_balance(self) -> float:
        """Retorna saldo USDT. Retorna -1 em caso de erro."""
        try:
            data = await self._get("/v5/account/wallet-balance",
                                   {"accountType": "UNIFIED"}, auth=True)
            for item in data.get("list", []):
                for coin in item.get("coin", []):
                    if coin.get("coin") == "USDT":
                        val = float(coin.get("walletBalance", 0))
                        log.info(f"💰 Saldo USDT: ${val:.2f}")
                        return val
            return 0.0
        except Exception as e:
            log.error(f"get_balance: {e}")
            return -1.0

    async def get_position(self, symbol: str) -> dict:
        try:
            data = await self._get("/v5/position/list", {
                "category": "linear", "symbol": symbol,
            }, auth=True)
            lst = data.get("list", [])
            return lst[0] if lst else {}
        except Exception as e:
            log.error(f"get_position: {e}")
            return {}

    async def place_order(self, symbol: str, side: str, qty: float,
                          order_type: str = "Market",
                          stop_loss: float = None,
                          take_profit: float = None,
                          reduce_only: bool = False) -> dict:
        body = {
            "category":    "linear",
            "symbol":      symbol,
            "side":        side,       # "Buy" or "Sell"
            "orderType":   order_type,
            "qty":         str(round(qty, 3)),
            "timeInForce": "GoodTillCancel",
            "reduceOnly":  reduce_only,
        }
        if stop_loss:
            body["stopLoss"] = str(round(stop_loss, 2))
        if take_profit:
            body["takeProfit"] = str(round(take_profit, 2))
        log.info(f"📤 ORDER {side} {qty} {symbol}")
        return await self._post("/v5/order/create", body)

    async def cancel_all(self, symbol: str) -> dict:
        try:
            return await self._post("/v5/order/cancel-all", {
                "category": "linear", "symbol": symbol,
            })
        except Exception as e:
            log.warning(f"cancel_all: {e}")
            return {}

    async def set_leverage(self, symbol: str, leverage: int) -> dict:
        try:
            return await self._post("/v5/position/set-leverage", {
                "category":     "linear",
                "symbol":       symbol,
                "buyLeverage":  str(leverage),
                "sellLeverage": str(leverage),
            })
        except Exception as e:
            log.warning(f"set_leverage: {e}")
            return {}

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

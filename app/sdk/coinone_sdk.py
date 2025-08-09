# coinone_sdk.py
"""
Simple Coinone SDK (sync). Supports common Public V2 endpoints and Private V2.1 signing.
依赖: requests
pip install requests
"""
from typing import Optional, Any, Dict, Tuple
import requests
import base64
import json
import hmac
import hashlib
import uuid
import time

# Exceptions
class CoinoneAPIError(Exception):
    def __init__(self, message: str, code: Optional[Any] = None, http_status: Optional[int] = None):
        super().__init__(message)
        self.code = code
        self.http_status = http_status

class CoinoneRateLimitError(CoinoneAPIError):
    pass


# Public client (market data)
class CoinonePublicClient:
    BASE_URL = "https://api.coinone.co.kr/public/v2"

    def __init__(self, session: Optional[requests.Session] = None, timeout: int = 10):
        self.session = session or requests.Session()
        self.timeout = timeout

    def _get(self, path: str, params: Optional[Dict] = None) -> Tuple[Dict, Dict]:
        url = f"{self.BASE_URL}{path}"
        resp = self.session.get(url, params=params, timeout=self.timeout, headers={"Accept": "application/json"})
        try:
            resp.raise_for_status()
        except requests.HTTPError as e:
            raise CoinoneAPIError(f"HTTP error: {e}", http_status=resp.status_code)
        try:
            j = resp.json()
        except ValueError:
            raise CoinoneAPIError("Invalid JSON from API", http_status=resp.status_code)
        # Common pattern: { "result": "success"/"error", ... }
        if isinstance(j, dict) and j.get("result") == "error":
            raise CoinoneAPIError(j.get("error_msg", "API error"), code=j.get("error_code"))
        return j, dict(resp.headers)

    # endpoints
    def get_range_units(self, quote_currency: str, target_currency: str) -> Tuple[Dict, Dict]:
        """GET /range_units/{quote}/{target}"""
        return self._get(f"/range_units/{quote_currency}/{target_currency}")

    def get_markets(self, quote_currency: str = "KRW") -> Tuple[Dict, Dict]:
        """GET /markets/{quote_currency}"""
        return self._get(f"/markets/{quote_currency}")

    def get_market(self, quote_currency: str, target_currency: str) -> Tuple[Dict, Dict]:
        """GET /market/{quote}/{target} (per-doc there is 개별 종목 info endpoint)"""
        return self._get(f"/market/{quote_currency}/{target_currency}")

    def get_orderbook(self, quote_currency: str, target_currency: str, size: int = 15, order_book_unit: Optional[float] = None) -> Tuple[Dict, Dict]:
        """GET /orderbook/{quote}/{target}?size=&order_book_unit="""
        params = {"size": size}
        if order_book_unit is not None:
            params["order_book_unit"] = order_book_unit
        return self._get(f"/orderbook/{quote_currency}/{target_currency}", params=params)

    def get_trades(self, quote_currency: str, target_currency: str, size: int = 200) -> Tuple[Dict, Dict]:
        """GET /trades/{quote}/{target}?size="""
        params = {"size": size}
        return self._get(f"/trades/{quote_currency}/{target_currency}", params=params)

    def get_tickers(self, quote_currency: str = "KRW", additional_data: bool = False) -> Tuple[Dict, Dict]:
        """GET /ticker_new/{quote_currency}?additional_data=true/false"""
        params = {"additional_data": "true"} if additional_data else None
        return self._get(f"/ticker_new/{quote_currency}", params=params)

    def get_ticker(self, quote_currency: str, target_currency: str, additional_data: bool = False) -> Tuple[Dict, Dict]:
        """GET /ticker_new/{quote}/{target}?additional_data="""
        params = {"additional_data": "true"} if additional_data else None
        return self._get(f"/ticker_new/{quote_currency}/{target_currency}", params=params)

    def get_chart(self, quote_currency: str, target_currency: str, interval: str, timestamp: Optional[int] = None, size: Optional[int] = None) -> Tuple[Dict, Dict]:
        """
        GET /chart/{quote}/{target}?interval=...&timestamp=...&size=...
        interval 支持: 1m,3m,5m,10m,15m,30m,1h,2h,4h,6h,1d,1w,1mon
        """
        params = {"interval": interval}
        if timestamp is not None:
            params["timestamp"] = timestamp
        if size is not None:
            params["size"] = size
        return self._get(f"/chart/{quote_currency}/{target_currency}", params=params)


# Private client (signed requests)
class CoinonePrivateClient:
    BASE_URL = "https://api.coinone.co.kr"  # private endpoints are under /v2.1/...
    def __init__(self, access_token: str, secret_key: str, session: Optional[requests.Session] = None, timeout: int = 10):
        self.access_token = access_token
        self.secret_key = secret_key
        self.session = session or requests.Session()
        self.timeout = timeout

    def _encode_payload_v21(self, params: Dict) -> bytes:
        """
        V2.1: nonce must be UUID v4 string. Attach access_token.
        Then JSON -> base64.
        """
        body = dict(params)  # copy
        body["access_token"] = self.access_token
        body["nonce"] = str(uuid.uuid4())
        # Use compact json
        json_str = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
        encoded = base64.b64encode(json_str.encode("utf-8"))
        return encoded

    def _sign(self, encoded_payload: bytes) -> str:
        return hmac.new(self.secret_key.encode("utf-8"), encoded_payload, hashlib.sha512).hexdigest()

    def _post_v21(self, path: str, params: Dict) -> Tuple[Dict, Dict]:
        url = f"{self.BASE_URL}{path}"
        encoded = self._encode_payload_v21(params)
        signature = self._sign(encoded)
        headers = {
            "Content-type": "application/json",
            "X-COINONE-PAYLOAD": encoded.decode("utf-8"),
            "X-COINONE-SIGNATURE": signature
        }
        resp = self.session.post(url, data=encoded, headers=headers, timeout=self.timeout)
        try:
            resp.raise_for_status()
        except requests.HTTPError:
            # try to extract JSON error if possible
            try:
                j = resp.json()
                raise CoinoneAPIError(j.get("error_msg", "HTTP error"), code=j.get("error_code"), http_status=resp.status_code)
            except ValueError:
                raise CoinoneAPIError("HTTP error", http_status=resp.status_code)
        try:
            j = resp.json()
        except ValueError:
            raise CoinoneAPIError("Invalid JSON from API", http_status=resp.status_code)
        if isinstance(j, dict) and j.get("result") == "error":
            # Rate limit / blocked user returns result:error and error_code 4 per docs
            if str(j.get("error_code")) == "4":
                raise CoinoneRateLimitError(j.get("error_msg", "Rate limited"), code=j.get("error_code"))
            raise CoinoneAPIError(j.get("error_msg", "API error"), code=j.get("error_code"))
        return j, dict(resp.headers)

    # example private endpoints
    def place_order(self,
                    quote_currency: str,
                    target_currency: str,
                    side: str,          # "BUY" or "SELL"
                    type_: str,         # "LIMIT", "MARKET", "STOP_LIMIT"
                    price: Optional[str] = None,
                    qty: Optional[str] = None,
                    amount: Optional[str] = None,
                    post_only: Optional[bool] = None,
                    limit_price: Optional[str] = None,
                    trigger_price: Optional[str] = None,
                    user_order_id: Optional[str] = None) -> Tuple[Dict, Dict]:
        """
        POST /v2.1/order
        返回包含 order_id 等字段 (result == "success").
        """
        payload = {
            "quote_currency": quote_currency,
            "target_currency": target_currency,
            "side": side,
            "type": type_
        }
        # optional params
        if price is not None:
            payload["price"] = price
        if qty is not None:
            payload["qty"] = qty
        if amount is not None:
            payload["amount"] = amount
        if post_only is not None:
            payload["post_only"] = bool(post_only)
        if limit_price is not None:
            payload["limit_price"] = limit_price
        if trigger_price is not None:
            payload["trigger_price"] = trigger_price
        if user_order_id is not None:
            payload["user_order_id"] = user_order_id
        return self._post_v21("/v2.1/order", payload)

    def get_balance_all(self) -> Tuple[Dict, Dict]:
        """POST /v2.1/account/balance/all"""
        payload = {}
        return self._post_v21("/v2.1/account/balance/all", payload)

    # More private endpoints can be added following the same pattern.
    def cancel_all_orders(self, quote_currency: str, target_currency: str):
        """
        POST /v2.1/cancel_all
        取消指定交易对的所有挂单
        """
        return self._post_v21("/v2.1/order/cancel/all", {"quote_currency": quote_currency,"target_currency":target_currency})



# Example usage (if run as script)
if __name__ == "__main__":
    public = CoinonePublicClient()
    try:
        data, headers = public.get_markets("KRW")
        print("Markets keys:", list(data.keys()))
    except CoinoneAPIError as e:
        print("Public API error:", e)

    # Private usage example (replace with real tokens)
    ACCESS_TOKEN = "your-access-token"
    SECRET_KEY = "your-secret-key"
    private = CoinonePrivateClient(access_token=ACCESS_TOKEN, secret_key=SECRET_KEY)
    # Example: get balances (will fail if tokens are placeholders)
    # try:
    #     bal, h = private.get_balance_all()
    #     print(bal)
    # except CoinoneAPIError as e:
    #     print("Private API error:", e)

## Running

Install deps and run the FastAPI service:

```
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Sample requests:

```
POST /public/orderbook
{
  "quote_currency": "KRW",
  "target_currency": "BTC",
  "size": 15
}

POST /v2.1/order
{
  "access_token": "...",
  "secret_key": "...",
  "quote_currency": "KRW",
  "target_currency": "BTC",
  "side": "BUY",
  "type": "LIMIT",
  "qty": "0.01",
  "price": "38000000",
  "post_only": false
}
```


"ACCESS_TOKEN": "c3eea729-a1c3-41d6-8308-a002721b787f",  # 替换为您的 Access Token
    "SECRET_KEY": "0bd6d6fa-7f78-4c7f-a58f-76545efe8ff4",


d74220e4-374e-47b7-8b88-3fd13e4bca95


7c039919-0799-4758-9358-d8d5aa182d84


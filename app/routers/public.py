from fastapi import APIRouter, Depends
from ..deps import get_public_client
from ..sdk.coinone_sdk import CoinonePublicClient

router = APIRouter(prefix="/public", tags=["Public"])

@router.get("/markets/{quote_currency}")
def markets(quote_currency: str, cli: CoinonePublicClient = Depends(get_public_client)):
    data, headers = cli.get_markets(quote_currency)
    return {
        "data": data,
        "rate_limit_remaining": headers.get("Public-Ratelimit-Remaining")
    }

@router.get("/ticker/{quote_currency}/{target_currency}")
def ticker(
    quote_currency: str,
    target_currency: str,
    cli: CoinonePublicClient = Depends(get_public_client)
):
    data, _ = cli.get_ticker(quote_currency, target_currency)
    return data

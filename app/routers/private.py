from fastapi import APIRouter, Depends
from ..deps import get_private_client
from ..sdk.coinone_sdk import CoinonePrivateClient

router = APIRouter(prefix="/private", tags=["Private"])

@router.get("/balance")
def balance(cli: CoinonePrivateClient = Depends(get_private_client)):
    data, _ = cli.get_balance_all()
    return data

@router.post("/order")
def place_order(
    quote_currency: str,
    target_currency: str,
    side: str,
    type_: str,
    amount: str = None,
    price: str = None,
    qty: str = None,
    post_only: bool = False,
    cli: CoinonePrivateClient = Depends(get_private_client)
):
    data, _ = cli.place_order(
        quote_currency=quote_currency,
        target_currency=target_currency,
        side=side,
        type_=type_,
        amount=amount,
        price=price,    
        qty=qty,
        post_only=post_only
    )
    return data

@router.post("/cancel_all")
def cancel_all_orders(quote_currency: str,target_currency: str,cli: CoinonePrivateClient = Depends(get_private_client)):
    """
    取消指定交易对的所有挂单
    """
    return cli.cancel_all_orders(quote_currency,target_currency)


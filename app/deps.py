from .sdk.coinone_sdk import CoinonePublicClient, CoinonePrivateClient
from . import config

def get_public_client() -> CoinonePublicClient:
    return CoinonePublicClient()

def get_private_client() -> CoinonePrivateClient:
    return CoinonePrivateClient(
        access_token=config.COINONE_ACCESS_TOKEN,
        secret_key=config.COINONE_SECRET_KEY
    )

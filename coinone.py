import typer
from rich.console import Console
from rich.table import Table
from rich.columns import Columns
from rich.live import Live
import time
import requests
from app.sdk.coinone_sdk import CoinonePublicClient, CoinoneAPIError
import time
import threading
from functools import wraps
import math
from decimal import Decimal

app = typer.Typer()
console = Console()

# 远端两个账户对应的 Proxy API 根地址（需已部署你现有的 FastAPI 服务）
CLIENT_1_URL = "http://43.201.114.205"  # 账户A（示例）
CLIENT_0_URL = "http://3.39.9.206"      # 账户B（示例）

# 交易参数
CURRENCY = "CBK"      # 指定币种
QUOTE = "KRW"         # 计价货币
# 没有币时，买入数量
BUY_AMOUNT = 200000
# 价格单位，去OpenAPI文档查
PRICE_UNIT = 5
# 小数点后保留几位
PRICE_PRECISION = 0
# 买单浮点数
BUY_FLOAT = 1.01
# 卖单浮点数
SELL_FLOAT = 0.99

# 初始化公共客户端（用于取订单簿、市场列表）；缩短超时以避免卡住
public_cli = CoinonePublicClient(timeout=3)

# 请求频率限制
def rate_limiter(max_calls_per_second):
    lock = threading.Lock()
    call_times = []

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal call_times
            with lock:
                now = time.monotonic()
                # 清理过期的调用时间（超过1秒的）
                call_times = [t for t in call_times if now - t < 1]
                if len(call_times) >= max_calls_per_second:
                    sleep_time = 1 - (now - call_times[0])
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                    now = time.monotonic()
                    call_times = [t for t in call_times if now - t < 1]
                call_times.append(now)
            return func(*args, **kwargs)
        return wrapper
    return decorator


def get_best_bid_ask() -> tuple[float, float]:
    """获取某个交易对的买一/卖一价格。失败时抛异常。"""
    ob, _ = public_cli.get_orderbook(quote_currency=QUOTE, target_currency=CURRENCY, size=5)
    bids = ob.get("bids") or []
    asks = ob.get("asks") or []
    if not bids or not asks:
        raise RuntimeError("订单簿为空")
    best_bid = float(bids[0]["price"])  # 买一
    best_ask = float(asks[0]["price"])  # 卖一
    if best_bid <= 0 or best_ask <= 0:
        raise RuntimeError("买一/卖一价格无效")
    return best_bid, best_ask

@rate_limiter(40)
def fetch_balances(client_url: str) -> dict:
    """从远端私有代理获取余额，返回形如 {"BTC": 0.01, ...} 的字典（仅非零）。"""
    try:
        res = requests.get(f"{client_url}/private/balance", timeout=5)
        data = res.json()
        out: dict[str, float] = {}
        if isinstance(data, dict) and data.get("result") == "success" and isinstance(data.get("balances"), list):
            for b in data["balances"]:
                cur = b.get("currency") or b.get("asset") or b.get("symbol")
                avail = b.get("available") or b.get("avail") or b.get("balance")
                if cur and avail is not None:
                    try:
                        v = float(avail)
                        if v > 0:
                            out[cur] = v
                    except ValueError:
                        continue
        elif isinstance(data, dict) and isinstance(data.get("balances"), dict):
            for k, v in data["balances"].items():
                try:
                    vv = float(v)
                    if vv > 0:
                        out[k] = vv
                except Exception:
                    continue
        return out
    except Exception:
        return {}


def build_balance_table(title: str, balances: dict) -> Table:
    """将余额字典渲染为 Rich 表格。"""
    table = Table(title=title, show_header=True, header_style="bold magenta")
    table.add_column("币种", justify="center")
    table.add_column("余额", justify="right")
    if not balances:
        table.add_row("-", "0")
    else:
        for coin, amount in sorted(balances.items(), key=lambda x: x[0]):
            table.add_row(coin, f"{amount:.8f}")
    return table




def place_limit_order(client_url: str, side: str, price: str = None, qty: str = None,amount: str = None,type_: str = "LIMIT" ) -> str | None:
    """通过远端代理下限价单（post_only 为 False，便于尽快撮合）。返回 order_id 或 None。"""
    try:
        resp = requests.post(
            f"{client_url}/private/order",
            params={
                "quote_currency": QUOTE,
                "target_currency": CURRENCY,
                "side": side,
                "type_": type_,
                "price": price,
                "qty": qty,
                "amount": amount,
                "post_only": False,
            },
            timeout=15,
        )
        print(resp)
        j = resp.json()
        if isinstance(j, dict) and j.get("result") == "success":
            return j.get("order_id")
        console.print(f"[red]下单失败: {j}[/red]")
        return None
    except Exception as e:
        console.print(f"[red]下单异常: {e}[/red]")
        return None


def cancel_order(client_url: str, quote_currency: str, target_currency: str) -> None:
    """取消指定交易对所有挂单（调用你的私有代理 /private/cancel_all）。"""
    try:
        r = requests.post(
            f"{client_url}/private/cancel_all",
            params={"quote_currency": QUOTE, "target_currency": CURRENCY},
            timeout=8,
        )
        j = r.json()[0]
        if isinstance(j, dict) and j.get("result") == "success":
            console.print(f"[yellow]取消订单成功 ({target_currency}/{quote_currency})[/yellow]")
        else:
            console.print(f"[red]取消订单失败: {j}[/red]")
    except Exception as e:
        console.print(f"[red]取消订单异常: {e}[/red]")


def display_balance_table(title: str, balances: dict):
    table = Table(title=title)
    table.add_column("币种")
    table.add_column("可用余额", justify="right")
    if not balances:
        console.print("[yellow]无余额[/yellow]")
    else:
        for cur, amt in sorted(balances.items(), key=lambda x: x[1], reverse=True):
            table.add_row(cur, f"{amt}")
    console.print(table)


@app.command()
def transfer(symbol: str = CURRENCY):
    """
    以“对称限价单”尝试在两个账户间迁移指定币种（仅演示流，无法保证双方互相成交）。
    - 若 B 的币多于 A：B 以买一价×1.01 挂卖单，A 以相同价格/数量挂买单。
    - 若 A 的币多于 B：A 以卖一价×0.99 挂卖单，B 以相同价格/数量挂买单。
    - 下单后轮询一段时间；未完全成交则撤单（需要你实现撤单 API）。
    风险提示：中心化订单簿不能定向成交，任何人都可以吃单。本流程仅作演示，存在被第三方撮合与滑点风险。
    """
    while True:
        order_id_a = None
        order_id_b = None
        try:
            # 1) 读取双方余额
            bal_a = fetch_balances(CLIENT_0_URL)
            bal_b = fetch_balances(CLIENT_1_URL)
            a_amt = float(bal_a.get(symbol, 0.0))
            b_amt = float(bal_b.get(symbol, 0.0))
            console.print(f"[cyan]A账号{symbol}：{a_amt} ｜ B账号{symbol}：{b_amt}[/cyan]")

            # 2) 获取买一/卖一用于定价
            bid, ask = get_best_bid_ask()
            console.print(f"[cyan]订单簿{symbol} | 卖: {ask} 买: {bid}[/cyan]")

            # 3) 依据谁余额多决定方向（仅演示价格与对称数量逻辑）
            if b_amt > a_amt and b_amt > 0:
                # B 多 → B 卖、A 买；价格取买一*1.01
                px = bid * BUY_FLOAT
                qty = b_amt
                # 下单之前判断px不能大于ask,并且ask必须比px大至少百分之5，如果小于则不进行下单
                if px > ask:
                    console.print("[yellow]价格不合理，不进行下单[/yellow]")
                    time.sleep(2)
                    continue
                order_id_a = place_limit_order(
                    CLIENT_0_URL, side="BUY",
                    price=f"{round(round(px/PRICE_UNIT) * PRICE_UNIT,PRICE_PRECISION)}",
                    qty=f"{qty}", amount=f"{qty}"
                )
                order_id_b = place_limit_order(
                    CLIENT_1_URL, side="SELL",
                    price=f"{round(round(px/PRICE_UNIT) * PRICE_UNIT,PRICE_PRECISION)}",
                    qty=f"{qty}", amount=f"{qty}"
                )
            elif a_amt > b_amt and a_amt > 0:
                # A 多 → A 卖、B 买；价格取卖一*0.99
                px = ask * SELL_FLOAT
                qty = a_amt
                # 下单之前判断px不能小于bid,并且bid必须比px大至少百分之5，如果小于则不进行下单
                if px < bid:
                    console.print("[yellow]价格不合理，不进行下单[/yellow]")
                    time.sleep(2)
                    continue
                order_id_a = place_limit_order(
                    CLIENT_0_URL, side="SELL",
                    price=f"{round(round(px/PRICE_UNIT) * PRICE_UNIT,PRICE_PRECISION)}",
                    qty=f"{qty}", amount=f"{qty}"
                )
                order_id_b = place_limit_order(
                    CLIENT_1_URL, side="BUY",
                    price=f"{round(round(px/PRICE_UNIT) * PRICE_UNIT,PRICE_PRECISION)}",
                    qty=f"{qty}", amount=f"{qty}"
                )
            elif a_amt == b_amt and a_amt > 0:
                # B 多 → B 卖、A 买；价格取买一*1.01
                px = bid * BUY_FLOAT
                qty = b_amt
                # 下单之前判断px不能大于ask,并且ask必须比px大至少百分之5，如果小于则不进行下单
                if px > ask:
                    console.print("[yellow]价格不合理，不进行下单[/yellow]")
                    time.sleep(2)
                    continue
                order_id_a = place_limit_order(
                    CLIENT_0_URL, side="BUY",
                    price=f"{round(round(px/PRICE_UNIT) * PRICE_UNIT,PRICE_PRECISION)}",
                    qty=f"{qty}", amount=f"{qty}"
                )
                order_id_b = place_limit_order(
                    CLIENT_1_URL, side="SELL",
                    price=f"{round(round(px/PRICE_UNIT) * PRICE_UNIT,PRICE_PRECISION)}",
                    qty=f"{qty}", amount=f"{qty}"
                )
            else:
                order_id_b = place_limit_order(
                    CLIENT_1_URL, side="BUY",
                    amount=f"{BUY_AMOUNT}",type_="MARKET"
                )
                

            # 4) 简单轮询订单状态（占位，需你在私有代理补充查询/撤单接口）
            time.sleep(0.5)
            if order_id_a:
                cancel_order(CLIENT_0_URL, QUOTE, symbol)
            if order_id_b:
                cancel_order(CLIENT_1_URL, QUOTE, symbol)
            console.print("[yellow]已尝试撤单（请实现远端撤单接口以生效）[/yellow]")
            # time.sleep(2)
        except Exception as e:
            # 出现任何异常尽力撤单
            if order_id_a:
                cancel_order(CLIENT_0_URL, QUOTE, symbol)
            if order_id_b:
                cancel_order(CLIENT_1_URL, QUOTE, symbol)
            raise e


@app.command()
def balance():
    """轮询展示两个账户的非零余额。
    """
    def make_layout():
        bal_a = fetch_balances(CLIENT_0_URL)
        bal_b = fetch_balances(CLIENT_1_URL)
        table_a = build_balance_table("账户A 余额（非零）", bal_a)
        table_b = build_balance_table("账户B 余额（非零）", bal_b)
        return Columns([table_a, table_b], equal=True, expand=True)

    console.print("[cyan]启动余额与候选监控…[/cyan]")
    with Live(make_layout(), refresh_per_second=2, console=console) as live:
        while True:
            live.update(make_layout())



if __name__ == "__main__":
    app()
# filename: merged_assets_with_mmf.py
from web3 import Web3
import requests, os
from decimal import Decimal

# ===== 基础配置 =====
ETH_RPC = os.environ.get("ETH_RPC_URL")
HSK_RPC = os.environ.get("HSK_RPC_URL")

# 以太坊主网：需要统计数量 + 价格的小计（不含 WHSK）
ADDRS = [
    "0x2171e6d3b7964fa9654ce41da8a8ffaff2cc70be",
    "0xe7Aa79B59CAc06F9706D896a047fEb9d3BDA8bD3"
]
ETH_TOKENS = {
    "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
    "WETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
    "WBTC": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",
    "HSK":  "0xE7C6BF469e97eEB0bFB74C8dbFF5BD47D4C1C98a",
}
# HashKey Chain：只展示 WHSK 的 totalSupply（不计入主网小计）
HSK_TOKENS = {
    "WHSK": "0xB210D2120d57b758EE163cFfb43e73728c471Cf1"
}

# HashKey Chain：11 个合约地址（用于读取 symbol/decimals/totalSupply）
MMF_TOKEN_ADDRS = [
    "0x7f69a2ba074dA1Fd422D994ee05C4B8CA83A32C7",
    "0x80C080acd48ED66a35Ae8A24BC1198672215A9bD",
    "0xf00A183Ae9DAA5ed969818E09fdd76a8e0B627E6",
    "0x34B842D0AcF830134D44075DCbcE43Ba04286c12",
    "0x7dAEbcD3E07b8e1a63337068570F9003372E8eA6",
    "0xc7167fC4C7d95b6faa30d63509D7392474a0B955",
    "0xE121e4081053060004ef1c3bEFeAc12e9af63659",
    "0xC574805dbEF911346BbE6F1dd10D279B49Bd0450",
    "0x7038A3a881fbDFD3551C47FB3cD5168cdc546547",
    "0x9dc14F49aB15EF4159F599a2dc116016A3E8622A",
    "0x762461409e5Ae774751601a19dbfA7C476a96E70",
]

# 仅这 5 个 MMF 需要乘价计入 “MMF原生发行金额”
MMF_PRICES_USD = {
    "PacARB": Decimal("1031.23"),
    "PacMMFi": Decimal("1018.16"),
    "AoABT":  Decimal("1012.49"),
    "BHKD":   Decimal("1.28"),
    "BUSD":   Decimal("10.1482"),
}

# ========= ERC20 ABI =========
ERC20_ABI = [
    {"name": "symbol",      "outputs": [{"type": "string"}], "inputs": [], "stateMutability": "view", "type": "function"},
    {"name": "decimals",    "outputs": [{"type": "uint8"}],  "inputs": [], "stateMutability": "view", "type": "function"},
    {"name": "balanceOf",   "outputs": [{"type": "uint256"}],"inputs": [{"name": "a", "type": "address"}], "stateMutability": "view", "type": "function"},
    {"name": "totalSupply", "outputs": [{"type": "uint256"}],"inputs": [], "stateMutability": "view", "type": "function"},
]

# ========= 工具函数 =========
def get_w3(rpc):
    w3 = Web3(Web3.HTTPProvider(rpc))
    if not w3.is_connected():
        raise RuntimeError(f"无法连接 RPC: {rpc}")
    return w3

def get_price_from_cg(contract_addr_on_eth):
    url = "https://api.coingecko.com/api/v3/simple/token_price/ethereum"
    r = requests.get(url, params={"contract_addresses": contract_addr_on_eth, "vs_currencies": "usd"}).json()
    return Decimal(str(r.get(contract_addr_on_eth.lower(), {}).get("usd", 0)))

def get_quantity(w3, token_addr, holders):
    c = w3.eth.contract(address=w3.to_checksum_address(token_addr), abi=ERC20_ABI)
    dec = c.functions.decimals().call()
    total = Decimal(0)
    for a in holders:
        bal = Decimal(c.functions.balanceOf(w3.to_checksum_address(a)).call()) / (10 ** dec)
        total += bal
    return total

def get_total_supply(w3, token_addr):
    c = w3.eth.contract(address=w3.to_checksum_address(token_addr), abi=ERC20_ABI)
    dec = c.functions.decimals().call()
    return Decimal(c.functions.totalSupply().call()) / (10 ** dec)

def get_symbol_decimals(w3, token_addr):
    c = w3.eth.contract(address=w3.to_checksum_address(token_addr), abi=ERC20_ABI)
    return c.functions.symbol().call(), c.functions.decimals().call()

# ========= 格式化函数 =========
def format_number(val, decimals=1):
    """代币数量：默认1位小数"""
    return f"{val:,.{decimals}f}"

def format_usd(val):
    """金额转成 K/M/B 格式"""
    if val >= 1_000_000_000:
        return f"{val/1_000_000_000:.2f}B"
    elif val >= 1_000_000:
        return f"{val/1_000_000:.2f}M"
    elif val >= 1_000:
        return f"{val/1_000:.2f}K"
    else:
        return f"{val:.2f}"

# ========= 主流程 =========
def main():
    w3_eth = get_w3(ETH_RPC)
    w3_hsk = get_w3(HSK_RPC)

    regular_total_usd = Decimal(0)
    hsk_price = None
    print("HashKey Chain链上资产数据:")

    # --- A) 主网小计 ---
    for sym, addr in ETH_TOKENS.items():
        qty = get_quantity(w3_eth, addr, ADDRS)
        price = get_price_from_cg(addr)
        if sym == "HSK":
            hsk_price = price
        usd_val = qty * price if price > 0 else Decimal(0)

        print(f"{sym}数量: {format_number(qty, 1)}")
        if usd_val > 0:
            print(f"{sym}资产总值(USD): {format_usd(usd_val)}")

        regular_total_usd += usd_val

    # WHSK totalSupply
    for sym, addr in HSK_TOKENS.items():
        ts = get_total_supply(w3_hsk, addr)
        print(f"{sym}数量: {format_number(ts, 1)}")

    print(f"链上常规资产总值: {format_usd(regular_total_usd)}\n")

    # --- B) MMF ---
    mmf_native_total_usd = Decimal(0)
    print("MMF发行合约（按 Symbol 展示：数量 与（若有单价）总值）：")
    for addr in MMF_TOKEN_ADDRS:
        try:
            sym, dec = get_symbol_decimals(w3_hsk, addr)
            ts = get_total_supply(w3_hsk, addr)
            if sym in MMF_PRICES_USD:
                total_val = ts * MMF_PRICES_USD[sym]
                mmf_native_total_usd += total_val
                print(f"{sym} ：{ts:,.0f} | 总价：{format_usd(total_val)}")
            else:
                print(f"{sym} ：{ts:,.0f}")
        except Exception as e:
            print(f"{addr} → 获取失败: {e}")

    print(f"\nMMF原生发行金额：{format_usd(mmf_native_total_usd)}")

    # --- C) 总额 ---
    chain_asset_total = regular_total_usd + mmf_native_total_usd
    print(f"链上资产总额：{format_usd(chain_asset_total)}")

if __name__ == "__main__":
    main()

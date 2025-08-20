# -*- coding: utf-8 -*-
import os
import requests, argparse, csv, re

GRAPHQL = "https://hashkey.blockscout.com/api/v1/graphql"
BLOCKSCOUT_BASE = "https://hashkey.blockscout.com"

# ===== 默认 CSV 路径（脚本同目录）=====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PROJECTS_CSV = os.path.join(BASE_DIR, "project_address.csv")

# ====== 规范化与名称映射（把 CSV 里的各种写法统一到目标显示名）======
def norm(s: str) -> str:
    return (s or "").strip().lower()

NAME_ALIASES = {
    "cellula": "Cellula",
    "index": "InDex",
    "asteroid": "Asteroid",
    "bountybay": "BountyBay",
    "dodo": "Dodo",
    "particle network": "Particle Network",
    "dmail": "Dmail",
    "nanofish": "Nano Fish",
    "nano fish": "Nano Fish",
    "混元kyc": "混元KYC",
    "izumi finance": "Izumi Finance",
    "cybercharge": "Cybercharge",
    "popcraft": "PopCraft",
    "mint club": "Mint Club",
    "zypher": "Zypher",
    "picwe": "PicWe",
    # 如需更多别名可继续补充
}

# ====== 输出顺序与分组 ======
GRANTS_ORDER = [
    "Cellula", "InDex", "Asteroid", "BountyBay", "Dodo",
    "Particle Network", "Dmail", "Nano Fish", "混元KYC",
]
OTHERS_ORDER = [
    "Izumi Finance", "Cybercharge", "PopCraft", "Mint Club", "Zypher", "PicWe",
]

# ---------- GraphQL 查询 ----------
def build_query_alias(addresses):
    lines = ["query {"]
    for i, addr in enumerate(addresses, start=1):
        lines.append(f'  a{i}: address(hash: "{addr}") {{ transactionsCount }}')
    lines.append("}")
    return "\n".join(lines)

def fetch_batch(addresses):
    """返回 [(addr, transactionsCount:int), ...]"""
    if not addresses:
        return []
    q = build_query_alias(addresses)
    r = requests.post(GRAPHQL, json={"query": q}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if "data" not in data:
        raise RuntimeError(f"GraphQL error: {data}")
    out = []
    for i, addr in enumerate(addresses, start=1):
        node = data["data"].get(f"a{i}")
        cnt_raw = node.get("transactionsCount") if node else None
        try:
            cnt = int(cnt_raw) if cnt_raw is not None else 0
        except Exception:
            cnt = 0
        out.append((addr, cnt))
    return out

# ---------- CSV 解析 ----------
def extract_eth_addresses(text):
    if not text:
        return []
    return re.findall(r"0x[a-fA-F0-9]{40}", text)

def read_projects_from_csv(file_path):
    """
    读取项目表：
      第1列=项目名；其它列拼起来，用正则抓 0x 地址
      返回 dict: {显示名: [addresses...]} （同名合并地址）
    """
    projects = {}
    with open(file_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for idx, row in enumerate(reader):
            if not row:
                continue
            raw_name = (row[0] or "").strip()
            if idx == 0 and (raw_name == "项目名" or raw_name.lower() == "name"):
                continue
            rest = "\n".join(col for col in row[1:] if col)
            merged = raw_name + "\n" + rest
            addrs_raw = extract_eth_addresses(merged)
            if not addrs_raw:
                continue

            # 规范化名称并映射到目标显示名
            key = norm(raw_name)
            display = NAME_ALIASES.get(key, raw_name.strip() or f"ROW_{idx+1}")

            # 去重（不区分大小写），保留首次出现的原样
            seen, addrs = set(), []
            for a in addrs_raw:
                k = a.lower()
                if k not in seen:
                    seen.add(k)
                    addrs.append(a)

            projects.setdefault(display, []).extend(addrs)
    # 同名合并后再次去重
    for name, addrs in list(projects.items()):
        seen, uniq = set(), []
        for a in addrs:
            k = a.lower()
            if k not in seen:
                seen.add(k)
                uniq.append(a)
        projects[name] = uniq
    return projects

# ---------- 计算 ----------
def sum_interactions_for_addresses(addresses, batch_size=25) -> int:
    total = 0
    for i in range(0, len(addresses), batch_size):
        chunk = addresses[i:i+batch_size]
        for _, cnt in fetch_batch(chunk):
            total += cnt
    return total

def compute_by_groups(projects_map, batch_size=25):
    """
    输入：projects_map = {display_name: [addresses]}
    输出：
      grants_rows: [(name, count)] 按 GRANTS_ORDER
      others_rows: [(name, count)] 按 OTHERS_ORDER 以及未分组
      grants_total: int
    """
    # 先计算所有项目计数
    counts = {}
    for name, addrs in projects_map.items():
        counts[name] = sum_interactions_for_addresses(addrs, batch_size=batch_size)

    # Grants 部分（按既定顺序挑选且只输出存在于 CSV 的项目）
    grants_rows = []
    grants_total = 0
    for name in GRANTS_ORDER:
        if name in counts:
            c = counts[name]
            grants_rows.append((name, c))
            grants_total += c

    # 其他部分（先输出你指定的 6 个顺序中存在的，再补充未分组的其余项目）
    others_rows = []
    picked = set(GRANTS_ORDER)
    for name in OTHERS_ORDER:
        if name in counts and name not in picked:
            others_rows.append((name, counts[name]))
            picked.add(name)

    # 把 CSV 里剩余但不在两套名单的项目也输出到“其他（未分组）”
    for name, c in counts.items():
        if name not in picked:
            others_rows.append((name, c))

    return grants_rows, grants_total, others_rows

# ---------- 主程序 ----------
def main():
    ap = argparse.ArgumentParser(description="Grants / 其他 项目交互统计（分组输出）")
    ap.add_argument("--projects-csv", help="项目表 CSV（默认读取 project_address.csv）")
    ap.add_argument("--batch", type=int, default=25, help="GraphQL 批量大小，默认 25")
    args = ap.parse_args()

    csv_path = args.projects_csv or DEFAULT_PROJECTS_CSV
    if not os.path.exists(csv_path):
        raise SystemExit(f"找不到项目表 CSV：{csv_path}")

    projects_map = read_projects_from_csv(csv_path)
    if not projects_map:
        raise SystemExit("未在 CSV 中解析到任何项目与地址。")

    grants_rows, grants_total, others_rows = compute_by_groups(projects_map, batch_size=args.batch)

    # === 按要求格式打印（不加日期；日期由 lark.py 统一加）===
    print("Grants 项目数据更新:")
    for name, total in grants_rows:
        print(f"{name}交互数:{total}")
    print(f"Grants项目总交互数:{grants_total}")

    if others_rows:
        print("\n其他项目交互数:")
        for name, total in others_rows:
            print(f"{name}交互数:{total}")

if __name__ == "__main__":
    main()

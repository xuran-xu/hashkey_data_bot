# -*- coding: utf-8 -*-
# filename: lark.py
import sys, os, subprocess, requests, datetime

# ===== Webhook（可相同也可不同）=====
WEBHOOK_ASSET   = os.environ.get("WEBHOOK_ASSET", "")
WEBHOOK_PROJECT = os.environ.get("WEBHOOK_PROJECT", "")

# ===== 脚本路径（默认同目录）=====
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
ASSET_PATH   = os.path.join(BASE_DIR, "asset.py")
PROJECT_PATH = os.path.join(BASE_DIR, "project.py")

# ========= 公共工具 =========
def safe_decode(b: bytes) -> str:
    for enc in ("utf-8", "gbk", "mbcs", "cp936"):
        try:
            return b.decode(enc)
        except Exception:
            pass
    return b.decode("utf-8", errors="replace")

def push_single(webhook: str, title: str, text: str, timeout: int = 15):
    """只推送一条，不分片。"""
    if not webhook:
        print(f"[run_and_push] 未提供 webhook（{title}），跳过推送。")
        return
    # 固定格式时间戳
    timestamp_line = f"数据更新时间: {datetime.datetime.now():%Y-%m-%d}\n"
    payload = {
        "msg_type": "text",
        "content": {"text": timestamp_line + text}
    }
    r = requests.post(webhook, json=payload, timeout=timeout)
    r.raise_for_status()

def run_script(name: str, path: str):
    """运行子脚本，实时打印输出，并返回 (文本, 退出码)。"""
    if not os.path.exists(path):
        raise FileNotFoundError(f"找不到 {name}：{path}")

    print(f"[run_and_push] 正在运行 {name} ……")
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    proc = subprocess.Popen(
        [sys.executable, "-u", path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        bufsize=0,
    )

    lines = []
    assert proc.stdout is not None
    for raw in iter(lambda: proc.stdout.readline(), b""):
        if not raw:
            break
        line = safe_decode(raw)
        print(line, end="")
        lines.append(line)

    proc.wait()
    print(f"[run_and_push] {name} 运行结束（退出码 {proc.returncode}）。\n")
    return "".join(lines), proc.returncode

if __name__ == "__main__":
    # 1) asset
    asset_report, asset_rc = run_script("asset.py", ASSET_PATH)
    if asset_rc == 0:
        push_single(WEBHOOK_ASSET, "asset.py 报告", asset_report)
        print("[run_and_push] asset 报告已推送。\n")
    else:
        print("[run_and_push] asset.py 执行失败，已跳过推送。")

    # 2) project
    try:
        project_report, project_rc = run_script("project.py", PROJECT_PATH)
        if project_rc == 0:
            push_single(WEBHOOK_PROJECT, "project.py 报告", project_report)
            print("[run_and_push] project 报告已推送。")
        else:
            print("[run_and_push] project.py 执行失败，已跳过推送。")
    except FileNotFoundError as e:
        print(f"[run_and_push] 跳过 project.py：{e}")

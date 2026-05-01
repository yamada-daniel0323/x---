"""
Flask + スケジューラー + Cloudflare Tunnel を一括起動するスクリプト
使い方:
  python start_remote.py          # 外部公開あり
  python start_remote.py --local  # ローカルのみ（Tunnel なし）
"""
import subprocess
import sys
import os
import re
import threading
import time
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

FLASK_PORT  = 5000
DASH_USER   = os.environ.get("DASH_USER", "admin")
DASH_PASS   = os.environ.get("DASH_PASS", "")
LOCAL_ONLY  = "--local" in sys.argv

Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("logs/x_automation.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("start_remote")


def run_scheduler():
    logger.info("スケジューラー起動中...")
    try:
        from scheduler import run
        run()
    except Exception as e:
        logger.error(f"スケジューラーエラー: {e}", exc_info=True)


def run_flask():
    logger.info(f"Flask 起動中 (port {FLASK_PORT})...")
    import app as flask_app
    flask_app.app.run(host="0.0.0.0", port=FLASK_PORT, debug=False, use_reloader=False)


def run_tunnel():
    logger.info("Cloudflare Tunnel 起動中...")
    proc = subprocess.Popen(
        ["cloudflared", "tunnel", "--url", f"http://localhost:{FLASK_PORT}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    url_found = False
    for line in proc.stdout:
        line = line.rstrip()
        if not url_found:
            m = re.search(r"https://[a-z0-9\-]+\.trycloudflare\.com", line)
            if m:
                url = m.group(0)
                print("\n" + "=" * 54)
                print("  外部アクセス URL（スマホ・外出先から使えます）")
                print(f"  {url}")
                print(f"  ユーザー名 : {DASH_USER}")
                print(f"  パスワード : {DASH_PASS}")
                print("=" * 54 + "\n")
                url_found = True


if __name__ == "__main__":
    print("\n" + "=" * 54)
    print("  X自動化 統合起動")
    print(f"  ローカル  : http://localhost:{FLASK_PORT}")
    print("  モード    : " + ("ローカルのみ" if LOCAL_ONLY else "外部公開あり"))
    print("=" * 54 + "\n")

    # スケジューラー（バックグラウンドスレッド）
    sched_thread = threading.Thread(target=run_scheduler, daemon=True, name="scheduler")
    sched_thread.start()
    time.sleep(1)

    # Flask（バックグラウンドスレッド）
    flask_thread = threading.Thread(target=run_flask, daemon=True, name="flask")
    flask_thread.start()
    time.sleep(2)

    if LOCAL_ONLY:
        print("ローカルモードで起動しました。Ctrl+C で停止。\n")
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            print("\n終了します")
    else:
        try:
            run_tunnel()
        except KeyboardInterrupt:
            print("\n終了します")

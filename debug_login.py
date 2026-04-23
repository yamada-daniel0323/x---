"""ログインデバッグ用スクリプト"""
import os
import time
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()
Path("logs").mkdir(exist_ok=True)

USERNAME = os.environ["X_USERNAME"]
PASSWORD = os.environ["X_PASSWORD"]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    print("1. ログインページへ移動...")
    page.goto("https://x.com/i/flow/login", wait_until="networkidle", timeout=30000)
    time.sleep(2)
    page.screenshot(path="logs/debug_01_login_page.png")
    print(f"   URL: {page.url}")

    print("2. ユーザー名を入力...")
    page.wait_for_selector('input[autocomplete="username"]', timeout=15000)
    page.fill('input[autocomplete="username"]', USERNAME)
    time.sleep(1)
    page.keyboard.press("Enter")
    time.sleep(4)
    page.screenshot(path="logs/debug_02_after_username.png")
    print(f"   URL: {page.url}")
    print(f"   タイトル: {page.title()}")

    # 現在の全inputを列挙
    inputs = page.query_selector_all("input")
    print(f"   画面上のinput要素: {len(inputs)}個")
    for i, inp in enumerate(inputs):
        print(f"     [{i}] name={inp.get_attribute('name')} type={inp.get_attribute('type')} autocomplete={inp.get_attribute('autocomplete')} data-testid={inp.get_attribute('data-testid')}")

    time.sleep(10)  # ブラウザを見る時間
    browser.close()

print("\nスクリーンショット保存先: logs/debug_01_*.png, logs/debug_02_*.png")

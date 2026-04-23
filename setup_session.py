"""
初回セットアップ: 実際のChromeでログインしてセッションを保存する。
ブラウザでXにログインしてから、このスクリプトを実行してください。
"""
import json
import yaml
import subprocess
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

session_file = config["browser"]["session_file"]

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Users\{}\AppData\Local\Google\Chrome\Application\chrome.exe".format(
        Path.home().name
    ),
]
chrome_path = next((p for p in CHROME_PATHS if Path(p).exists()), None)

print("=" * 50)
print("  セッションセットアップ")
print("=" * 50)

if not chrome_path:
    print("[警告] Chromeが見つかりません。Playwright内蔵Chromiumを使用します。")
    print("       ボット判定されやすくなります。")
else:
    print(f"Chrome: {chrome_path}")

print()
print("Chromeが開きます。Xに手動でログインしてください。")
print("ホーム画面が表示されたら自動的にセッションが保存されます。")
print("=" * 50)

with sync_playwright() as p:
    launch_kwargs = dict(
        headless=False,
        args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
    )
    if chrome_path:
        launch_kwargs["executable_path"] = chrome_path

    browser = p.chromium.launch(**launch_kwargs)
    context = browser.new_context(no_viewport=True)
    page = context.new_page()
    page.goto("https://x.com/login")

    print("\nXにログインしてください...")
    print("ログイン完了を自動検知します（最大5分待機）")

    try:
        page.wait_for_selector(
            '[data-testid="SideNav_NewTweet_Button"]',
            timeout=300000,
        )
        print("\nログイン検知！セッションを保存中...")
        context.storage_state(path=session_file)

        # 保存結果を検証
        saved = json.loads(Path(session_file).read_text(encoding="utf-8"))
        auth_cookies = {c["name"] for c in saved.get("cookies", [])}
        required = {"auth_token", "ct0"}
        if required.issubset(auth_cookies):
            print(f"セッション保存完了: {session_file}")
            print(f"認証Cookie確認: {', '.join(auth_cookies & required)}")
        else:
            missing = required - auth_cookies
            print(f"[警告] 認証Cookieが不足しています: {missing}")
            print("       ログインが完了しているか確認してください。")

    except Exception as e:
        print(f"\nタイムアウトまたはエラー: {e}")
        print("ブラウザを手動で閉じる前にセッションを保存しようとします...")
        try:
            context.storage_state(path=session_file)
            print(f"セッション保存: {session_file}")
        except Exception as e2:
            print(f"保存失敗: {e2}")
    finally:
        try:
            browser.close()
        except Exception:
            pass

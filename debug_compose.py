"""
テキスト入力方法を複数試してどれが効くか確認する
"""
import time, sys
from dotenv import load_dotenv; load_dotenv()
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
import yaml
from pathlib import Path

with open('config.yaml', encoding='utf-8') as f:
    config = yaml.safe_load(f)
chrome_path = config['browser'].get('chrome_path', '')

TEST_TEXT = 'テストだよ'

def check_btn(page):
    btn = page.query_selector('[data-testid="tweetButtonInline"]')
    if btn:
        return btn.get_attribute('aria-disabled'), btn.get_attribute('disabled')
    return None, None

with sync_playwright() as p:
    launch_kwargs = dict(
        headless=False,
        args=['--disable-blink-features=AutomationControlled'],
    )
    if chrome_path and Path(chrome_path).exists():
        launch_kwargs['executable_path'] = chrome_path

    browser = p.chromium.launch(**launch_kwargs)
    context = browser.new_context(
        storage_state='session.json',
        locale='ja-JP',
        timezone_id='Asia/Tokyo',
        permissions=['clipboard-read', 'clipboard-write'],
    )
    page = context.new_page()
    Stealth().apply_stealth_sync(page)

    page.goto('https://x.com', wait_until='load', timeout=30000)
    time.sleep(3)

    # 投稿ダイアログを開く
    page.click('[data-testid="SideNav_NewTweet_Button"]')
    time.sleep(2)
    page.screenshot(path='logs/d01_open.png')

    ta = page.wait_for_selector('[data-testid="tweetTextarea_0"]', timeout=10000)
    ta.click()
    time.sleep(0.5)

    # ---- 方法1: クリップボード貼り付け ----
    print('--- 方法1: clipboard paste ---')
    page.evaluate(f'navigator.clipboard.writeText({repr(TEST_TEXT)})')
    page.keyboard.press('Control+v')
    time.sleep(1.5)
    page.screenshot(path='logs/d02_clipboard.png')
    aria, dis = check_btn(page)
    print(f'  aria-disabled={aria} disabled={dis}')
    content = page.evaluate("document.querySelector('[data-testid=\"tweetTextarea_0\"]').innerText")
    print(f'  textarea: {repr(content)}')

    browser.close()

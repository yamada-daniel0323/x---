import os
import subprocess
import time
import random
import logging
import yaml
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from playwright_stealth import Stealth
from history import record

logger = logging.getLogger(__name__)

X_URL = "https://x.com"
LOGIN_URL = "https://x.com/i/flow/login"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]


def _set_clipboard(text: str):
    """PowerShell経由でWindowsクリップボードにテキストをセット（ブラウザフォーカス不要）"""
    env = os.environ.copy()
    env["_CLIP_TEXT"] = text
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value $env:_CLIP_TEXT"],
        env=env, capture_output=True, check=True,
    )


def _rand_sleep(lo: float = 1.5, hi: float = 3.5):
    time.sleep(random.uniform(lo, hi))


def _human_sleep():
    """人間が考えたり気が散ったりする自然な間"""
    base = random.uniform(1.5, 4.0)
    # 20%の確率でちょっと長く止まる（スマホ見たり別タブ見たり）
    if random.random() < 0.2:
        base += random.uniform(3.0, 8.0)
    time.sleep(base)


def _move_mouse_naturally(page, target_x: int, target_y: int):
    """マウスを直線ではなくランダムな曲線で移動"""
    steps = random.randint(8, 15)
    cur_x = random.randint(300, 800)
    cur_y = random.randint(200, 600)
    for i in range(steps):
        t = (i + 1) / steps
        # ベジェ曲線的なランダムウォーク
        jitter_x = random.randint(-30, 30) * (1 - t)
        jitter_y = random.randint(-20, 20) * (1 - t)
        x = int(cur_x + (target_x - cur_x) * t + jitter_x)
        y = int(cur_y + (target_y - cur_y) * t + jitter_y)
        page.mouse.move(x, y)
        time.sleep(random.uniform(0.02, 0.07))


def _human_click(page, selector: str):
    """マウスを自然に動かしてからクリック"""
    el = page.wait_for_selector(selector, timeout=15000)
    box = el.bounding_box()
    if box:
        # ボックス内のランダムな点をクリック（中心より少しずれる）
        tx = box["x"] + box["width"] * random.uniform(0.3, 0.7)
        ty = box["y"] + box["height"] * random.uniform(0.3, 0.7)
        _move_mouse_naturally(page, int(tx), int(ty))
        time.sleep(random.uniform(0.1, 0.3))
        page.mouse.click(tx, ty)
    else:
        el.click()


def _scroll_timeline(page):
    """タイムラインを人間らしくスクロールして読む（ふりをする）"""
    scroll_count = random.randint(2, 5)
    for _ in range(scroll_count):
        distance = random.randint(200, 600)
        page.mouse.wheel(0, distance)
        time.sleep(random.uniform(0.8, 2.5))
    # たまに少し戻る
    if random.random() < 0.4:
        page.mouse.wheel(0, -random.randint(100, 300))
        time.sleep(random.uniform(0.5, 1.5))


def load_config() -> dict:
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def post_tweet(text: str, image_path: str = "") -> bool:
    config = load_config()
    session_file = config["browser"]["session_file"]
    headless = config["browser"]["headless"]

    username = os.environ["X_USERNAME"]
    password = os.environ["X_PASSWORD"]

    with sync_playwright() as p:
        chrome_path = config["browser"].get("chrome_path", "")
        launch_kwargs = dict(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        if chrome_path and Path(chrome_path).exists():
            launch_kwargs["executable_path"] = chrome_path
        browser = p.chromium.launch(**launch_kwargs)

        ua = random.choice(USER_AGENTS)
        ctx_kwargs = dict(
            user_agent=ua,
            viewport={"width": random.randint(1280, 1920), "height": random.randint(800, 1080)},
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
        )
        if Path(session_file).exists():
            ctx_kwargs["storage_state"] = session_file
        context = browser.new_context(**ctx_kwargs)
        page = context.new_page()
        Stealth().apply_stealth_sync(page)

        try:
            page.goto(X_URL, wait_until="load", timeout=30000)
            _rand_sleep(2, 4)

            if "login" in page.url or not _is_logged_in(page):
                logger.info("ログイン実行中...")
                try:
                    _login(page, username, password)
                    context.storage_state(path=session_file)
                    logger.info("ログイン完了・セッション保存")
                except Exception as login_err:
                    if Path(session_file).exists():
                        Path(session_file).unlink()
                    raise login_err

            # ホームに着いたら人間らしくタイムラインを少し眺める
            _scroll_timeline(page)
            _human_sleep()

            success = _compose_tweet(page, text, image_path)
            if success:
                record(text, status="success")
                logger.info("投稿成功")
            else:
                record(text, status="failed")
                logger.error("投稿確認できませんでした")
            return success

        except Exception as e:
            logger.error(f"投稿失敗: {e}", exc_info=True)
            record(text, status="failed")
            return False

        finally:
            # ブラウザをすぐ閉じず少し待つ（自然な離脱）
            time.sleep(random.uniform(1.5, 3.0))
            browser.close()


def _is_logged_in(page) -> bool:
    try:
        page.wait_for_selector('[data-testid="SideNav_NewTweet_Button"]', timeout=5000)
        return True
    except PlaywrightTimeout:
        return False


def _login(page, username: str, password: str):
    page.goto(LOGIN_URL, wait_until="load", timeout=30000)
    _rand_sleep(1.5, 3)

    page.wait_for_selector('input[autocomplete="username"]', timeout=15000)
    _rand_sleep(0.5, 1.2)
    page.fill('input[autocomplete="username"]', username)
    _rand_sleep(0.8, 1.5)

    next_btn = page.locator('button[type="button"]').filter(has_text="次へ").first
    if next_btn.count() > 0:
        next_btn.click()
    else:
        page.keyboard.press("Enter")
    _rand_sleep(2.5, 4)

    # 中間ステップ（電話番号・メール確認など）
    try:
        verify_input = page.wait_for_selector(
            'input[data-testid="ocfEnterTextTextInput"]', timeout=6000
        )
        if verify_input:
            logger.info("中間認証ステップ検出 → ユーザー名を入力")
            page.fill('input[data-testid="ocfEnterTextTextInput"]', username)
            _rand_sleep(0.8, 1.5)
            next_btn2 = page.query_selector('[data-testid="ocfEnterTextNextButton"]')
            if next_btn2:
                next_btn2.click()
            else:
                page.keyboard.press("Enter")
            _rand_sleep(2.5, 4)
    except PlaywrightTimeout:
        pass

    try:
        page.wait_for_selector('input[name="password"]', timeout=15000)
    except PlaywrightTimeout:
        page.screenshot(path="logs/login_debug.png")
        logger.error(f"パスワード画面に進めず。URL: {page.url}")
        raise

    _rand_sleep(0.5, 1.0)
    page.fill('input[name="password"]', password)
    _rand_sleep(0.5, 1.5)
    page.keyboard.press("Enter")

    page.wait_for_selector('[data-testid="SideNav_NewTweet_Button"]', timeout=20000)
    _rand_sleep(1, 2)


def _compose_tweet(page, text: str, image_path: str = "") -> bool:
    # 投稿ボタンへ自然なマウス移動でクリック
    _human_click(page, '[data-testid="SideNav_NewTweet_Button"]')
    _rand_sleep(1.2, 2.5)

    # モーダルのテキストエリアを待つ
    textarea_loc = page.locator('[data-testid="tweetTextarea_0"]').first
    textarea_loc.wait_for(timeout=10000)
    _rand_sleep(0.4, 0.9)
    textarea_loc.click()
    _rand_sleep(0.3, 0.7)

    # 画像アップロード（指定されている場合）
    if image_path and Path(image_path).exists():
        file_input = page.locator('input[data-testid="fileInput"]').first
        file_input.set_input_files(str(Path(image_path).resolve()))
        page.wait_for_selector('[data-testid="attachments"]', timeout=15000)
        logger.info(f"画像添付: {image_path}")
        _rand_sleep(1.0, 2.0)

    # OSクリップボード経由でテキスト入力（ブラウザフォーカス不要）
    _set_clipboard(text)
    _rand_sleep(0.3, 0.6)
    textarea_loc.press("Control+v")

    # 入力後、人間らしく内容を確認する間を置く
    _human_sleep()

    # たまに入力内容を読み直すように少し待つ
    if random.random() < 0.3:
        logger.debug("投稿内容を見直し中...")
        time.sleep(random.uniform(2.0, 5.0))

    # Ctrl+Enter で投稿
    page.wait_for_selector('[data-testid="tweetButtonInline"]', timeout=10000)
    textarea_loc.press('Control+Enter')
    _rand_sleep(3, 5)

    # 成功確認
    try:
        page.wait_for_selector('[data-testid="toast"]', timeout=8000)
        return True
    except PlaywrightTimeout:
        error_el = page.query_selector('[data-testid="tweetButtonInline"]')
        return error_el is None

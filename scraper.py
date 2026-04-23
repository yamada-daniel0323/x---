import csv
import time
import random
import logging
import yaml
import re
from pathlib import Path
from urllib.parse import quote
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from playwright_stealth import Stealth

logger = logging.getLogger(__name__)


def load_config() -> dict:
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _rand_sleep(lo: float = 1.5, hi: float = 3.5):
    time.sleep(random.uniform(lo, hi))


def parse_count(text: str) -> int:
    if not text:
        return 0
    text = text.strip().replace(",", "")
    if "万" in text:
        return int(float(text.replace("万", "")) * 10000)
    if re.search(r'[Kk]$', text):
        return int(float(text[:-1]) * 1000)
    if re.search(r'M$', text):
        return int(float(text[:-1]) * 1000000)
    try:
        return int(text)
    except ValueError:
        return 0


def _extract_tweets(page, source: str, max_count: int) -> list[dict]:
    """現在のページからツイートを抽出する共通処理"""
    results = []
    seen_ids = set()
    scroll_attempts = 0

    while len(results) < max_count and scroll_attempts < 10:
        tweets = page.query_selector_all('[data-testid="tweet"]')

        for tweet in tweets:
            try:
                link = tweet.query_selector('a[href*="/status/"]')
                if not link:
                    continue
                href = link.get_attribute("href")
                tweet_id = re.search(r"/status/(\d+)", href)
                if not tweet_id:
                    continue
                tid = tweet_id.group(1)
                if tid in seen_ids:
                    continue
                seen_ids.add(tid)

                text_el = tweet.query_selector('[data-testid="tweetText"]')
                text = text_el.inner_text() if text_el else ""
                if not text:
                    continue

                # いいね数: span が複数ネストされている場合があるので aria-label からも取る
                likes = 0
                like_btn = tweet.query_selector('[data-testid="like"]')
                if like_btn:
                    aria = like_btn.get_attribute("aria-label") or ""
                    # 日本語: "147件のいいね" / 英語: "147 Likes"
                    m = re.search(r"([\d,]+(?:\.\d+)?[KkMm万]?)\s*(?:件の)?(?:いいね|Like)", aria)
                    if m:
                        likes = parse_count(m.group(1))
                    else:
                        span = like_btn.query_selector('span[data-testid="app-text-transition-container"] span')
                        if not span:
                            span = like_btn.query_selector("span > span")
                        likes = parse_count(span.inner_text() if span else "0")

                rts = 0
                rt_btn = tweet.query_selector('[data-testid="retweet"]')
                if rt_btn:
                    span = rt_btn.query_selector('span[data-testid="app-text-transition-container"] span')
                    if not span:
                        span = rt_btn.query_selector("span > span")
                    rts = parse_count(span.inner_text() if span else "0")

                # ユーザー名取得
                user_el = tweet.query_selector('[data-testid="User-Name"] a')
                user_href = user_el.get_attribute("href") if user_el else ""
                username = user_href.strip("/").split("/")[-1] if user_href else "unknown"

                results.append({
                    "source": source,
                    "account": username,
                    "tweet_id": tid,
                    "text": text,
                    "likes": likes,
                    "retweets": rts,
                    "url": f"https://x.com/{username}/status/{tid}",
                })

                if len(results) >= max_count:
                    break

            except Exception as e:
                logger.debug(f"ツイートパースエラー: {e}")
                continue

        page.evaluate(f"window.scrollBy(0, {random.randint(1200, 1800)})")
        _rand_sleep(1.5, 3.5)
        scroll_attempts += 1

    return results


def scrape_keyword(page, keyword: str, max_tweets: int) -> list[dict]:
    """キーワード・ハッシュタグ検索でツイートを収集"""
    search_url = f"https://x.com/search?q={quote(keyword)}&src=typed_query&f=top"
    try:
        page.goto(search_url, wait_until="load", timeout=30000)
        _rand_sleep(2, 4)
        page.wait_for_selector('[data-testid="tweet"]', timeout=15000)
    except PlaywrightTimeout:
        logger.error(f"検索失敗: {keyword}")
        return []

    results = _extract_tweets(page, source=keyword, max_count=max_tweets)
    logger.info(f"キーワード「{keyword}」: {len(results)}件取得")
    return results


def scrape_account(page, username: str, max_tweets: int) -> list[dict]:
    """アカウントのタイムラインからツイートを収集"""
    url = f"https://x.com/{username}"
    try:
        page.goto(url, wait_until="load", timeout=30000)
        _rand_sleep(2, 4)
        page.wait_for_selector('[data-testid="tweet"]', timeout=15000)
    except PlaywrightTimeout:
        logger.error(f"@{username}: タイムライン読み込み失敗")
        return []

    results = _extract_tweets(page, source=f"@{username}", max_count=max_tweets)
    logger.info(f"@{username}: {len(results)}件取得")
    return results


def collect_buzz(session_file: str = None) -> list[dict]:
    config = load_config()
    scrape_cfg = config["scraping"]
    if session_file is None:
        session_file = config["browser"]["session_file"]

    all_tweets = []

    ua_list = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    ]

    with sync_playwright() as p:
        chrome_path = config["browser"].get("chrome_path", "")
        launch_kwargs = dict(
            headless=config["browser"]["headless"],
            args=["--disable-blink-features=AutomationControlled"],
        )
        if chrome_path and Path(chrome_path).exists():
            launch_kwargs["executable_path"] = chrome_path

        browser = p.chromium.launch(**launch_kwargs)
        ctx_kwargs = dict(
            user_agent=random.choice(ua_list),
            viewport={"width": random.randint(1280, 1920), "height": random.randint(800, 1080)},
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
        )
        if Path(session_file).exists():
            ctx_kwargs["storage_state"] = session_file
        context = browser.new_context(**ctx_kwargs)
        page = context.new_page()
        Stealth().apply_stealth_sync(page)

        # キーワード検索
        for keyword in scrape_cfg.get("keywords", []):
            logger.info(f"検索中: {keyword}")
            tweets = scrape_keyword(page, keyword, scrape_cfg["tweets_per_account"])
            all_tweets.extend(tweets)
            _rand_sleep(3, 6)

        # アカウント監視（設定されている場合）
        for username in scrape_cfg.get("accounts", []):
            logger.info(f"@{username} をスクレイピング中...")
            tweets = scrape_account(page, username, scrape_cfg["tweets_per_account"])
            all_tweets.extend(tweets)
            _rand_sleep(3, 6)

        browser.close()

    # 重複除去・いいね数フィルタ・ソート
    seen = set()
    unique = []
    for t in all_tweets:
        if t["tweet_id"] not in seen:
            seen.add(t["tweet_id"])
            unique.append(t)

    min_likes = scrape_cfg["min_likes"]
    buzz = [t for t in unique if t["likes"] >= min_likes]
    buzz.sort(key=lambda x: x["likes"], reverse=True)

    logger.info(f"バズツイート: {len(buzz)}件（{min_likes}いいね以上）")
    return buzz


def save_results(buzz: list[dict], output_file: str):
    fieldnames = ["source", "account", "tweet_id", "likes", "retweets", "text", "url"]
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(buzz)
    logger.info(f"保存完了: {output_file} ({len(buzz)}件)")


def append_to_tweets_csv(buzz: list[dict], tweets_file: str):
    existing = set()
    if Path(tweets_file).exists():
        with open(tweets_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing.add(row["text"].strip())

    new_entries = []
    for t in buzz:
        text = t["text"].strip()
        if text not in existing:
            new_entries.append(text)

    if new_entries:
        with open(tweets_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            for text in new_entries:
                writer.writerow([text])
        logger.info(f"tweets.csvに{len(new_entries)}件追記しました")


def run():
    config = load_config()
    scrape_cfg = config["scraping"]

    buzz = collect_buzz()

    if not buzz:
        logger.info("バズツイートが見つかりませんでした")
        return

    save_results(buzz, scrape_cfg["output_file"])

    if scrape_cfg.get("auto_append"):
        append_to_tweets_csv(buzz, config["content"]["file"])

    print(f"\n{'='*50}")
    print(f"バズツイート収集結果: {len(buzz)}件")
    print(f"{'='*50}")
    for t in buzz[:5]:
        print(f"\n{t['source']} | @{t['account']} | いいね {t['likes']:,} | RT {t['retweets']:,}")
        print(f"{t['text'][:80]}...")
        print(f"{t['url']}")
    print(f"\n全件: {scrape_cfg['output_file']}")

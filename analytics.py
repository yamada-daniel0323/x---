import csv
import time
import random
import logging
import re
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from playwright_stealth import Stealth

logger = logging.getLogger(__name__)

ANALYTICS_URL = "https://analytics.twitter.com/user/{username}/home"
TWEET_ANALYTICS_URL = "https://analytics.twitter.com/user/{username}/tweets"
FOLLOWERS_FILE = "logs/followers_history.csv"
TWEET_STATS_FILE = "logs/tweet_stats.csv"


def _ensure_files():
    Path("logs").mkdir(exist_ok=True)
    if not Path(FOLLOWERS_FILE).exists():
        with open(FOLLOWERS_FILE, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=["date", "followers"]).writeheader()
    if not Path(TWEET_STATS_FILE).exists():
        with open(TWEET_STATS_FILE, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=[
                "date", "tweet_preview", "impressions", "engagements",
                "likes", "retweets", "replies", "engagement_rate"
            ]).writeheader()


def _parse_number(text: str) -> int:
    if not text:
        return 0
    text = text.strip().replace(",", "").replace(" ", "")
    try:
        if "K" in text or "k" in text:
            return int(float(text.lower().replace("k", "")) * 1000)
        if "M" in text:
            return int(float(text.replace("M", "")) * 1000000)
        if "万" in text:
            return int(float(text.replace("万", "")) * 10000)
        return int(float(text))
    except ValueError:
        return 0


def _rand_sleep(lo: float = 1.5, hi: float = 3.5):
    time.sleep(random.uniform(lo, hi))


def scrape_analytics(session_file: str = None) -> dict:
    _ensure_files()

    import yaml
    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    headless = config["browser"]["headless"]
    if session_file is None:
        session_file = config["browser"]["session_file"]

    result = {
        "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "followers": 0,
        "impressions_28d": 0,
        "engagements_28d": 0,
        "tweets": [],
    }

    ua_list = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
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

        try:
            # --- フォロワー数をプロフィールから取得 ---
            page.goto("https://x.com/home", wait_until="load", timeout=60000)
            _rand_sleep(3, 5)

            # サイドバーのアカウント情報からユーザー名取得
            try:
                username = ""
                account_el = page.query_selector('[data-testid="SideNav_AccountSwitcher_Button"]')
                if account_el:
                    # UserAvatar-Container-<username> から取得
                    avatar_el = account_el.query_selector('[data-testid^="UserAvatar-Container-"]')
                    if avatar_el:
                        testid = avatar_el.get_attribute("data-testid") or ""
                        m = re.match(r"UserAvatar-Container-(.+)", testid)
                        if m:
                            username = m.group(1)
            except Exception:
                username = ""

            if username:
                page.goto(f"https://x.com/{username}", wait_until="load", timeout=60000)
                _rand_sleep(2, 4)

                # フォロワー数: verified_followers または followers リンクから取得
                try:
                    for selector in [
                        f'a[href="/{username}/verified_followers"]',
                        f'a[href="/{username}/followers"]',
                        'a[href*="/verified_followers"]',
                        'a[href*="/followers"]',
                    ]:
                        followers_el = page.query_selector(selector)
                        if followers_el:
                            text = followers_el.inner_text().strip()
                            num_part = re.split(r"[\s\n]", text)[0]
                            val = _parse_number(num_part)
                            if val >= 0:
                                result["followers"] = val
                            break
                except Exception:
                    pass

                # プロフィールタイムラインからツイート統計取得
                try:
                    articles = page.query_selector_all('[data-testid="tweet"]')
                    total_impressions = 0
                    total_engagements = 0
                    for art in articles[:20]:
                        text_el = art.query_selector('[data-testid="tweetText"]')
                        tweet_text = text_el.inner_text().strip()[:50] if text_el else ""

                        analytics_link = art.query_selector('a[href*="/analytics"]')
                        impressions = _parse_number(analytics_link.inner_text().strip()) if analytics_link else 0

                        like_el = art.query_selector('[data-testid="like"] span span')
                        likes = _parse_number(like_el.inner_text()) if like_el else 0

                        rt_el = art.query_selector('[data-testid="retweet"] span span')
                        retweets = _parse_number(rt_el.inner_text()) if rt_el else 0

                        reply_el = art.query_selector('[data-testid="reply"] span span')
                        replies = _parse_number(reply_el.inner_text()) if reply_el else 0

                        engagements = likes + retweets + replies
                        rate = round(engagements / impressions * 100, 2) if impressions > 0 else 0.0
                        total_impressions += impressions
                        total_engagements += engagements

                        result["tweets"].append({
                            "tweet_preview": tweet_text,
                            "impressions": impressions,
                            "engagements": engagements,
                            "likes": likes,
                            "retweets": retweets,
                            "replies": replies,
                            "engagement_rate": rate,
                        })

                    result["impressions_28d"] = total_impressions
                    result["engagements_28d"] = total_engagements
                except Exception as e:
                    logger.warning(f"ツイート統計取得エラー: {e}")

        except Exception as e:
            logger.error(f"Analytics スクレイピングエラー: {e}", exc_info=True)
        finally:
            browser.close()

    return result


def save_analytics(data: dict):
    today = datetime.now().strftime("%Y-%m-%d")

    # フォロワー数履歴
    if data["followers"] > 0:
        with open(FOLLOWERS_FILE, "a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=["date", "followers"]).writerow({
                "date": today,
                "followers": data["followers"],
            })

    # ツイート統計
    if data["tweets"]:
        with open(TWEET_STATS_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "date", "tweet_preview", "impressions", "engagements",
                "likes", "retweets", "replies", "engagement_rate"
            ])
            for tweet in data["tweets"]:
                writer.writerow({"date": today, **tweet})

    logger.info("Analytics データ保存完了")


def load_followers_history() -> list[dict]:
    if not Path(FOLLOWERS_FILE).exists():
        return []
    with open(FOLLOWERS_FILE, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_tweet_stats() -> list[dict]:
    if not Path(TWEET_STATS_FILE).exists():
        return []
    with open(TWEET_STATS_FILE, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def print_summary(data: dict):
    print(f"\n{'='*55}")
    print(f"  X アナリティクス サマリー")
    print(f"  取得日時: {data['scraped_at']}")
    print(f"{'='*55}")
    print(f"  フォロワー数       : {data['followers']:,}")
    print(f"  インプレッション(28日): {data['impressions_28d']:,}")
    print(f"  エンゲージメント(28日): {data['engagements_28d']:,}")

    if data["tweets"]:
        print(f"\n  【ツイート別成績 上位5件】")
        top = sorted(data["tweets"], key=lambda x: x["impressions"], reverse=True)[:5]
        for i, t in enumerate(top, 1):
            print(f"\n  {i}. {t['tweet_preview']}...")
            print(f"     impressions: {t['impressions']:,} | likes: {t['likes']:,} | RT: {t['retweets']:,} | rate: {t['engagement_rate']}%")
    print(f"{'='*55}\n")


def run():
    data = scrape_analytics()
    save_analytics(data)
    print_summary(data)
    return data

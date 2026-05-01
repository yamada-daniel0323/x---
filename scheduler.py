import schedule
import time
import random
import logging
import yaml
from datetime import datetime, timedelta
from content import get_next_tweet
from browser_poster import post_tweet
import scheduler_state as state

logger = logging.getLogger(__name__)


def _load_config() -> dict:
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── ジョブ本体 ───────────────────────────────────────

def post_job():
    if state.load().get("paused"):
        logger.info("スケジューラー一時停止中 → 投稿スキップ")
        return
    try:
        logger.info("投稿ジョブ開始")
        tweet, image = get_next_tweet()
        logger.info(f"投稿内容: {tweet[:40]}...")
        success = post_tweet(tweet, image)
        status = "success" if success else "failed"
        state.record_post(tweet, status)
        if not success:
            logger.error("投稿失敗。次回スケジュールで再試行します。")
    except Exception as e:
        logger.error(f"投稿ジョブエラー: {e}", exc_info=True)
        state.record_post("エラー", "error")


def analytics_job():
    if state.load().get("paused"):
        return
    try:
        logger.info("アナリティクス収集ジョブ開始")
        from analytics import run as analytics_run
        analytics_run()
        state.record_analytics("success")
    except Exception as e:
        logger.error(f"アナリティクスジョブエラー: {e}", exc_info=True)
        state.record_analytics("error")


def scrape_and_generate_job():
    """バズネタ収集 → AI でオリジナルツイート生成 → tweets.csv に追記"""
    if state.load().get("paused"):
        return
    try:
        config = _load_config()
        scrape_cfg = config["scraping"]

        logger.info("バズネタ収集ジョブ開始")
        from scraper import collect_buzz, save_results
        buzz = collect_buzz()

        if buzz:
            save_results(buzz, scrape_cfg["output_file"])
            logger.info(f"バズネタ {len(buzz)}件 収集完了")
        else:
            logger.info("バズネタが見つかりませんでした")

        state.record_scrape("success")

        # AI でオリジナルツイート生成
        generate_count = scrape_cfg.get("generate_count", 0)
        if generate_count > 0:
            logger.info(f"AI によるツイート生成開始 ({generate_count}件)...")
            from generator import generate_and_save
            generated = generate_and_save(count=generate_count)
            logger.info(f"AI 生成完了: {len(generated)}件 → tweets.csv に追記")
        else:
            logger.info("generate_count=0 のため AI 生成をスキップ")

    except Exception as e:
        logger.error(f"収集・生成ジョブエラー: {e}", exc_info=True)
        state.record_scrape("error")


# ── ランダムスケジューリング ──────────────────────────

def _window_to_minutes(start: str, end: str) -> tuple[int, int]:
    """'HH:MM' → 分に変換"""
    sh, sm = map(int, start.split(":"))
    eh, em = map(int, end.split(":"))
    return sh * 60 + sm, eh * 60 + em


def _random_time_in_window(start: str, end: str) -> str:
    """ウィンドウ内のランダムな時刻を 'HH:MM' で返す"""
    lo, hi = _window_to_minutes(start, end)
    minutes = random.randint(lo, hi)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _schedule_today_posts():
    """今日の投稿時刻をランダムに決めてスケジュールする（毎日 00:05 に呼ばれる）"""
    # 前日のランダム投稿ジョブをクリア
    schedule.clear("daily_post")

    config = _load_config()
    sched_cfg = config["schedule"]
    windows = sched_cfg.get("windows", [["09:00", "10:00"]])
    posts_per_day = sched_cfg.get("posts_per_day", len(windows))

    # ウィンドウが足りない場合はランダムにサンプリング
    selected_windows = random.sample(windows, min(posts_per_day, len(windows)))
    selected_windows.sort(key=lambda w: w[0])

    scheduled_times = []
    for w in selected_windows:
        t = _random_time_in_window(w[0], w[1])
        now_str = datetime.now().strftime("%H:%M")
        # すでに過ぎた時刻はスキップ
        if t <= now_str:
            logger.info(f"時刻 {t} はすでに過ぎているためスキップ")
            continue
        schedule.every().day.at(t).do(post_job).tag("daily_post")
        scheduled_times.append(t)
        logger.info(f"本日の投稿スケジュール: {t} （ウィンドウ {w[0]}〜{w[1]}）")

    if not scheduled_times:
        logger.warning("本日の投稿スケジュールが0件です（全ウィンドウが過去の時刻）")

    _refresh_next_jobs()


def _refresh_next_jobs():
    jobs = []
    for j in schedule.get_jobs():
        if j.next_run:
            fn = getattr(j.job_func, "__name__", None) or getattr(j.job_func, "func", j.job_func).__name__
            jobs.append({
                "tag": fn,
                "next_run": j.next_run.strftime("%Y-%m-%d %H:%M:%S"),
            })
    jobs.sort(key=lambda x: x["next_run"])
    state.update_next_jobs(jobs[:10])


# ── メインループ ────────────────────────────────────

def run():
    config = _load_config()
    sched_cfg = config["schedule"]

    # バズ収集 + AI 生成（毎日 scrape_time）
    scrape_time = sched_cfg.get("scrape_time", "07:00")
    schedule.every().day.at(scrape_time).do(scrape_and_generate_job)
    logger.info(f"収集・生成スケジュール: 毎日 {scrape_time}")

    # アナリティクス収集
    analytics_time = sched_cfg.get("analytics_time", "23:30")
    schedule.every().day.at(analytics_time).do(analytics_job)
    logger.info(f"アナリティクス収集: 毎日 {analytics_time}")

    # 毎日 00:05 にその日の投稿時刻を再抽選
    schedule.every().day.at("00:05").do(_schedule_today_posts)

    # 起動直後に今日分を即時スケジューリング
    _schedule_today_posts()

    state.set_running(True)
    _refresh_next_jobs()
    logger.info("スケジューラー起動完了。Ctrl+C で停止。")

    try:
        while True:
            schedule.run_pending()
            _refresh_next_jobs()
            time.sleep(30)
    finally:
        state.set_running(False)

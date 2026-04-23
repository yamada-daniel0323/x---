import schedule
import time
import random
import logging
import yaml
from content import get_next_tweet
from browser_poster import post_tweet

logger = logging.getLogger(__name__)


def post_job():
    try:
        logger.info("投稿ジョブ開始")
        tweet, image = get_next_tweet()
        logger.info(f"投稿内容: {tweet[:30]}..." + (" [画像あり]" if image else ""))
        success = post_tweet(tweet, image)
        if not success:
            logger.error("投稿失敗。次回スケジュールで再試行します。")
    except Exception as e:
        logger.error(f"投稿ジョブエラー: {e}", exc_info=True)


def post_job_with_jitter():
    """±15分のランダム遅延を入れてから投稿（同じ時刻の繰り返しを避ける）"""
    jitter = random.randint(-15 * 60, 15 * 60)  # 秒
    if jitter > 0:
        logger.info(f"投稿を {jitter // 60}分{jitter % 60}秒 後にずらします")
        time.sleep(jitter)
    elif jitter < 0:
        logger.info(f"投稿を即時実行（{abs(jitter) // 60}分早め）")
    post_job()


def analytics_job():
    try:
        logger.info("アナリティクス収集ジョブ開始")
        from analytics import run as analytics_run
        analytics_run()
    except Exception as e:
        logger.error(f"アナリティクスジョブエラー: {e}", exc_info=True)


def scrape_job():
    try:
        logger.info("バズネタ収集ジョブ開始")
        from scraper import collect_buzz, save_results, append_to_tweets_csv
        import yaml as _yaml
        with open("config.yaml", "r", encoding="utf-8") as f:
            config = _yaml.safe_load(f)

        buzz = collect_buzz()
        if buzz:
            save_results(buzz, config["scraping"]["output_file"])
            if config["scraping"].get("auto_append"):
                append_to_tweets_csv(buzz, config["content"]["file"])
            logger.info(f"バズネタ収集完了: {len(buzz)}件")

            # バズネタをもとにオリジナルツイートを生成してtweets.csvに追加
            generate_count = config["scraping"].get("generate_count", 5)
            if generate_count > 0:
                logger.info(f"バズネタからツイートを{generate_count}件生成中...")
                from generator import generate_and_save
                generate_and_save(count=generate_count)
        else:
            logger.info("バズネタが見つかりませんでした")
    except Exception as e:
        logger.error(f"収集ジョブエラー: {e}", exc_info=True)


def run():
    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    for t in config["schedule"]["times"]:
        schedule.every().day.at(t).do(post_job_with_jitter)
        logger.info(f"投稿スケジュール: 毎日 {t} (±15分ゆらぎあり)")

    scrape_time = config["schedule"].get("scrape_time", "07:00")
    schedule.every().day.at(scrape_time).do(scrape_job)
    logger.info(f"収集スケジュール: 毎日 {scrape_time}")

    analytics_time = config["schedule"].get("analytics_time", "23:30")
    schedule.every().day.at(analytics_time).do(analytics_job)
    logger.info(f"アナリティクス収集: 毎日 {analytics_time}")

    logger.info("スケジューラー起動。Ctrl+Cで停止。")
    while True:
        schedule.run_pending()
        time.sleep(30)

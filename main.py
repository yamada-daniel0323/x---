import os
import sys
import logging
import yaml
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def setup_logging():
    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    log_file = config["logging"]["file"]
    Path(log_file).parent.mkdir(exist_ok=True)

    level = getattr(logging, config["logging"]["level"])
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def check_env():
    required = ["X_USERNAME", "X_PASSWORD"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        print(f"エラー: .envに未設定項目があります: {', '.join(missing)}")
        print(".env.exampleを参考に.envファイルを作成してください。")
        sys.exit(1)


def main():
    setup_logging()
    check_env()
    logger = logging.getLogger(__name__)

    if len(sys.argv) > 1 and sys.argv[1] == "--now":
        # 即時テスト投稿
        from content import get_next_tweet
        from browser_poster import post_tweet

        tweet, image = get_next_tweet()
        print(f"\n投稿内容:\n{'='*40}\n{tweet}")
        if image:
            print(f"画像: {image}")
        print('='*40)
        confirm = input("投稿しますか？ (y/N): ").strip().lower()
        if confirm == "y":
            success = post_tweet(tweet, image)
            print("投稿完了！" if success else "投稿失敗。ログを確認してください。")
        else:
            print("キャンセルしました。")

    elif len(sys.argv) > 1 and sys.argv[1] == "--history":
        # 投稿履歴表示
        from history import show_history
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        show_history(limit)

    elif len(sys.argv) > 1 and sys.argv[1] == "--analytics":
        # アナリティクス取得・表示
        from analytics import run as analytics_run
        data = analytics_run()
        if "--chart" in sys.argv:
            from chart import run_all
            run_all()

    elif len(sys.argv) > 1 and sys.argv[1] == "--chart":
        # グラフのみ生成（保存済みデータから）
        from chart import run_all
        run_all()

    elif len(sys.argv) > 1 and sys.argv[1] == "--scrape":
        # バズツイート収集
        from scraper import run as scrape_run
        scrape_run()

    elif len(sys.argv) > 1 and sys.argv[1] == "--generate":
        # バズネタからオリジナルツイートを生成
        from generator import run as generate_run
        generate_run()

    elif len(sys.argv) > 1 and sys.argv[1] == "--reset-session":
        # セッションリセット
        import yaml
        with open("config.yaml", "r") as f:
            config = yaml.safe_load(f)
        session_file = config["browser"]["session_file"]
        if Path(session_file).exists():
            Path(session_file).unlink()
            print("セッションをリセットしました。次回起動時に再ログインします。")
        else:
            print("セッションファイルは存在しません。")

    else:
        from scheduler import run
        run()


if __name__ == "__main__":
    main()

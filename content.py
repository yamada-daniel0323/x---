import csv
import random
import logging
import yaml
from pathlib import Path
from history import has_been_posted

logger = logging.getLogger(__name__)

_sequential_index = 0


def load_tweets(filepath: str) -> list[dict]:
    tweets = []
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            text = row["text"].strip().strip('"')
            if not text:
                continue
            image = row.get("image", "").strip()
            # 画像パスが指定されていても実在しない場合は無視
            if image and not Path(image).exists():
                logger.warning(f"画像ファイルが見つかりません: {image} → スキップ")
                image = ""
            tweets.append({"text": text, "image": image})
    return tweets


def get_next_tweet() -> tuple[str, str]:
    """(text, image_path) を返す。image_path は空文字の場合あり"""
    global _sequential_index

    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    tweets = load_tweets(config["content"]["file"])
    if not tweets:
        raise ValueError("tweets.csvにツイート内容がありません")

    mode = config["content"]["mode"]

    if mode == "random":
        unposted = [t for t in tweets if not has_been_posted(t["text"])]
        pool = unposted if unposted else tweets
        if not unposted:
            logger.warning("全ツイートが投稿済みです。再利用します。")
        entry = random.choice(pool)
    else:
        for i in range(len(tweets)):
            candidate = tweets[(_sequential_index + i) % len(tweets)]
            if not has_been_posted(candidate["text"]):
                entry = candidate
                _sequential_index = (_sequential_index + i + 1) % len(tweets)
                break
        else:
            logger.warning("全ツイートが投稿済みです。再利用します。")
            entry = tweets[_sequential_index % len(tweets)]
            _sequential_index += 1

    logger.info(f"ツイート選択: {entry['text'][:30]}..." + (" [画像あり]" if entry["image"] else ""))
    return entry["text"], entry["image"]

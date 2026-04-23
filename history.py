import csv
import hashlib
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

HISTORY_FILE = "logs/post_history.csv"
FIELDNAMES = ["posted_at", "text_hash", "text_preview", "tweet_id", "status"]


def _ensure_file():
    Path(HISTORY_FILE).parent.mkdir(exist_ok=True)
    if not Path(HISTORY_FILE).exists():
        with open(HISTORY_FILE, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FIELDNAMES).writeheader()


def _hash(text: str) -> str:
    return hashlib.md5(text.strip().encode()).hexdigest()


def has_been_posted(text: str) -> bool:
    _ensure_file()
    target = _hash(text)
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["text_hash"] == target and row["status"] == "success":
                return True
    return False


def record(text: str, tweet_id: str = "", status: str = "success"):
    _ensure_file()
    with open(HISTORY_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writerow({
            "posted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "text_hash": _hash(text),
            "text_preview": text[:50].replace("\n", " "),
            "tweet_id": tweet_id,
            "status": status,
        })
    logger.info(f"履歴記録: [{status}] {text[:30]}...")


def show_history(limit: int = 20):
    _ensure_file()
    rows = []
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    recent = rows[-limit:][::-1]
    print(f"\n{'='*60}")
    print(f"投稿履歴（直近{len(recent)}件）")
    print(f"{'='*60}")
    for r in recent:
        status_mark = "✓" if r["status"] == "success" else "✗"
        print(f"{status_mark} {r['posted_at']} | {r['text_preview']}")
    print(f"\n合計: {len(rows)}件")

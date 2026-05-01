"""スケジューラーの状態を logs/scheduler_state.json に読み書きする共有モジュール"""
import json
from datetime import datetime
from pathlib import Path

STATE_FILE = "logs/scheduler_state.json"

_default = {
    "running": False,
    "paused": False,
    "started_at": None,
    "last_post": {"time": None, "text": None, "status": None},
    "last_scrape": {"time": None, "status": None},
    "last_analytics": {"time": None, "status": None},
    "next_jobs": [],
}


def load() -> dict:
    try:
        return json.loads(Path(STATE_FILE).read_text(encoding="utf-8"))
    except Exception:
        return dict(_default)


def save(state: dict):
    Path(STATE_FILE).parent.mkdir(exist_ok=True)
    Path(STATE_FILE).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def set_running(running: bool):
    s = load()
    s["running"] = running
    if running:
        s["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save(s)


def set_paused(paused: bool):
    s = load()
    s["paused"] = paused
    save(s)


def record_post(text: str, status: str):
    s = load()
    s["last_post"] = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "text": text[:50],
        "status": status,
    }
    save(s)


def record_scrape(status: str):
    s = load()
    s["last_scrape"] = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": status,
    }
    save(s)


def record_analytics(status: str):
    s = load()
    s["last_analytics"] = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": status,
    }
    save(s)


def update_next_jobs(jobs: list):
    s = load()
    s["next_jobs"] = jobs
    save(s)

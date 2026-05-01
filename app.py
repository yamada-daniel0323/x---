import csv
import os
import time
import yaml
import logging
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, Response

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "x-auto-default-secret-key-change-me")

logging.basicConfig(level=logging.INFO)




def load_config() -> dict:
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_config(config: dict):
    with open("config.yaml", "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)


def load_tweets() -> list[dict]:
    from history import has_been_posted
    cfg = load_config()
    tweets = []
    filepath = cfg["content"]["file"]
    if not Path(filepath).exists():
        return tweets
    with open(filepath, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            text = row["text"].strip().strip('"')
            if text:
                tweets.append({"text": text, "posted": has_been_posted(text)})
    return tweets


def load_history(limit: int = 100) -> list[dict]:
    from history import HISTORY_FILE
    if not Path(HISTORY_FILE).exists():
        return []
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return list(reversed(rows[-limit:]))


def load_buzz() -> list[dict]:
    cfg = load_config()
    filepath = cfg["scraping"]["output_file"]
    if not Path(filepath).exists():
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_followers_latest() -> str:
    from analytics import FOLLOWERS_FILE
    if not Path(FOLLOWERS_FILE).exists():
        return "--"
    with open(FOLLOWERS_FILE, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return "--"
    val = int(rows[-1]["followers"])
    return f"{val:,}"


def load_impressions_latest() -> str:
    from analytics import load_tweet_stats
    stats = load_tweet_stats()
    if not stats:
        return "--"
    total = sum(int(r.get("impressions") or 0) for r in stats[-50:])
    return f"{total:,}"


# ── Auth ────────────────────────────────────────────

@app.before_request
def check_auth():
    user = os.environ.get("DASH_USER", "")
    passwd = os.environ.get("DASH_PASS", "")
    if not user:
        return
    auth = request.authorization
    if not auth or auth.username != user or auth.password != passwd:
        return Response(
            "認証が必要です", 401,
            {"WWW-Authenticate": 'Basic realm="X Dashboard"'}
        )


# ── Routes ──────────────────────────────────────────

@app.route("/")
def dashboard():
    tweets = load_tweets()
    history = load_history(10)
    from history import HISTORY_FILE
    posted = sum(1 for t in tweets if t["posted"])
    return render_template("dashboard.html",
        followers=load_followers_latest(),
        impressions=load_impressions_latest(),
        posted_count=posted,
        unposted_count=len(tweets) - posted,
        recent=history,
    )


@app.route("/tweets")
def tweets_page():
    return render_template("tweets.html", tweets=load_tweets())


@app.route("/tweets/add", methods=["POST"])
def add_tweet():
    text = request.form.get("text", "").strip()
    if not text:
        flash("内容を入力してください", "danger")
        return redirect(url_for("tweets_page"))
    if len(text) > 280:
        flash("280文字以内で入力してください", "danger")
        return redirect(url_for("tweets_page"))

    cfg = load_config()
    filepath = cfg["content"]["file"]
    write_header = not Path(filepath).exists()
    with open(filepath, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(["text"])
        w.writerow([text])
    flash("ツイートを追加しました", "success")
    return redirect(url_for("tweets_page"))


@app.route("/tweets/post/<int:idx>", methods=["POST"])
def post_tweet_by_index(idx):
    try:
        from browser_poster import post_tweet
        cfg = load_config()
        tweets = []
        with open(cfg["content"]["file"], "r", encoding="utf-8") as f:
            tweets = [row["text"].strip().strip('"') for row in csv.DictReader(f) if row["text"].strip()]
        if idx < 0 or idx >= len(tweets):
            flash("ツイートが見つかりません", "danger")
            return redirect(url_for("tweets_page"))
        tweet = tweets[idx]
        success = post_tweet(tweet)
        if success:
            flash(f"投稿しました: {tweet[:50]}...", "success")
        else:
            flash("投稿に失敗しました。ログを確認してください。", "danger")
    except Exception as e:
        flash(f"エラー: {e}", "danger")
    return redirect(url_for("tweets_page"))


@app.route("/tweets/delete/<int:idx>", methods=["POST"])
def delete_tweet(idx):
    cfg = load_config()
    filepath = cfg["content"]["file"]
    tweets = []
    with open(filepath, "r", encoding="utf-8") as f:
        tweets = [row["text"] for row in csv.DictReader(f)]
    if 0 <= idx < len(tweets):
        tweets.pop(idx)
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["text"])
        for t in tweets:
            w.writerow([t])
    flash("削除しました", "success")
    return redirect(url_for("tweets_page"))


@app.route("/buzz")
def buzz_page():
    return render_template("buzz.html", buzz=load_buzz())


@app.route("/buzz/add-to-tweets", methods=["POST"])
def buzz_add():
    text = request.form.get("text", "").strip()
    if text:
        cfg = load_config()
        filepath = cfg["content"]["file"]
        write_header = not Path(filepath).exists()
        with open(filepath, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if write_header:
                w.writerow(["text"])
            w.writerow([text])
        flash("ツイートに追加しました", "success")
    return redirect(url_for("buzz_page"))


@app.route("/history")
def history_page():
    return render_template("history.html", rows=load_history(200))


@app.route("/analytics")
def analytics_page():
    return render_template("analytics.html")


@app.route("/analytics/data")
def analytics_data():
    from analytics import load_followers_history, load_tweet_stats
    from flask import jsonify

    followers_rows = load_followers_history()
    tweet_rows = load_tweet_stats()

    # フォロワー推移
    followers_chart = {
        "labels": [r["date"] for r in followers_rows],
        "data": [int(r["followers"]) for r in followers_rows],
    }

    # 日別インプレッション・エンゲージメント集計
    by_date: dict = {}
    for r in tweet_rows:
        d = r["date"]
        if d not in by_date:
            by_date[d] = {"impressions": 0, "engagements": 0, "count": 0}
        by_date[d]["impressions"] += int(r.get("impressions") or 0)
        by_date[d]["engagements"] += int(r.get("engagements") or 0)
        by_date[d]["count"] += 1

    sorted_dates = sorted(by_date.keys())
    daily_chart = {
        "labels": sorted_dates,
        "impressions": [by_date[d]["impressions"] for d in sorted_dates],
        "engagement_rates": [
            round(by_date[d]["engagements"] / by_date[d]["impressions"] * 100, 2)
            if by_date[d]["impressions"] > 0 else 0.0
            for d in sorted_dates
        ],
    }

    # ツイートランキング（全件）
    ranking = []
    for r in tweet_rows:
        ranking.append({
            "date": r["date"],
            "tweet_preview": r.get("tweet_preview", ""),
            "impressions": int(r.get("impressions") or 0),
            "engagements": int(r.get("engagements") or 0),
            "likes": int(r.get("likes") or 0),
            "retweets": int(r.get("retweets") or 0),
            "replies": int(r.get("replies") or 0),
            "engagement_rate": float(r.get("engagement_rate") or 0),
        })
    ranking.sort(key=lambda x: x["impressions"], reverse=True)

    # KPI サマリー
    total_impressions = sum(r["impressions"] for r in ranking)
    total_engagements = sum(r["engagements"] for r in ranking)
    avg_rate = round(total_engagements / total_impressions * 100, 2) if total_impressions > 0 else 0.0
    latest_followers = int(followers_rows[-1]["followers"]) if followers_rows else 0

    return jsonify({
        "kpi": {
            "followers": latest_followers,
            "total_impressions": total_impressions,
            "avg_engagement_rate": avg_rate,
            "total_posts": len(ranking),
        },
        "followers_chart": followers_chart,
        "daily_chart": daily_chart,
        "ranking": ranking,
    })


@app.route("/analytics/fetch", methods=["POST"])
def analytics_fetch():
    try:
        from analytics import run as analytics_run
        analytics_run()
        flash("アナリティクスデータを取得しました", "success")
    except Exception as e:
        flash(f"取得失敗: {e}", "danger")
    return redirect(url_for("analytics_page"))


@app.route("/settings")
def settings_page():
    cfg = load_config()
    tweets = load_tweets()
    history = load_history(9999)
    buzz = load_buzz()
    return render_template("settings.html",
        config=cfg,
        tweet_count=len(tweets),
        history_count=len(history),
        buzz_count=len(buzz),
    )


@app.route("/settings/save", methods=["POST"])
def settings_save():
    cfg = load_config()
    f = request.form
    cfg["schedule"]["times"] = [t.strip() for t in f.get("times", "").split(",") if t.strip()]
    cfg["schedule"]["scrape_time"] = f.get("scrape_time", "07:00").strip()
    cfg["schedule"]["analytics_time"] = f.get("analytics_time", "23:30").strip()
    cfg["scraping"]["accounts"] = [a.strip() for a in f.get("accounts", "").split(",") if a.strip()]
    cfg["scraping"]["min_likes"] = int(f.get("min_likes", 1000))
    cfg["scraping"]["auto_append"] = f.get("auto_append") == "true"
    cfg["content"]["mode"] = f.get("mode", "random")
    save_config(cfg)
    flash("設定を保存しました", "success")
    return redirect(url_for("settings_page"))


@app.route("/scheduler/status")
def scheduler_status():
    from flask import jsonify
    import scheduler_state as state
    return jsonify(state.load())


@app.route("/scheduler/pause", methods=["POST"])
def scheduler_pause():
    import scheduler_state as state
    state.set_paused(True)
    flash("スケジューラーを一時停止しました", "warning")
    return redirect(url_for("dashboard"))


@app.route("/scheduler/resume", methods=["POST"])
def scheduler_resume():
    import scheduler_state as state
    state.set_paused(False)
    flash("スケジューラーを再開しました", "success")
    return redirect(url_for("dashboard"))


@app.route("/post-now", methods=["POST"])
def post_now():
    try:
        from content import get_next_tweet
        from browser_poster import post_tweet
        tweet = get_next_tweet()
        success = post_tweet(tweet)
        if success:
            flash(f"投稿しました: {tweet[:50]}...", "success")
        else:
            flash("投稿に失敗しました。ログを確認してください。", "danger")
    except Exception as e:
        flash(f"エラー: {e}", "danger")
    return redirect(url_for("dashboard"))


@app.route("/scrape-now", methods=["POST"])
def scrape_now():
    try:
        from scraper import run as scrape_run
        scrape_run()
        flash("バズネタを収集しました", "success")
    except Exception as e:
        flash(f"収集失敗: {e}", "danger")
    return redirect(url_for("buzz_page"))


if __name__ == "__main__":
    Path("logs").mkdir(exist_ok=True)
    Path("static").mkdir(exist_ok=True)
    print("\n" + "="*45)
    print("  X自動化ダッシュボード起動中")
    print("  PC:     http://localhost:5000")
    print("  スマホ: http://<このPCのIP>:5000")
    print("="*45 + "\n")
    app.run(host="0.0.0.0", port=5000, debug=False)

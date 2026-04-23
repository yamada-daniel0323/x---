import csv
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def _setup_matplotlib():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    try:
        import japanize_matplotlib  # noqa: F401
    except ImportError:
        plt.rcParams["font.family"] = "MS Gothic"
    return plt


def chart_followers(output: str = "logs/chart_followers.png"):
    from analytics import load_followers_history
    plt = _setup_matplotlib()

    rows = load_followers_history()
    if len(rows) < 2:
        print("フォロワー履歴データが不足しています（2日分以上必要）")
        return

    dates = [r["date"] for r in rows]
    counts = [int(r["followers"]) for r in rows]

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(dates, counts, marker="o", color="#1DA1F2", linewidth=2)
    ax.fill_between(range(len(dates)), counts, alpha=0.1, color="#1DA1F2")
    ax.set_xticks(range(len(dates)))
    ax.set_xticklabels(dates, rotation=45, ha="right", fontsize=8)
    ax.set_title("フォロワー数推移", fontsize=14)
    ax.set_ylabel("フォロワー数")
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.savefig(output, dpi=150)
    plt.close()
    print(f"保存: {output}")


def chart_impressions(output: str = "logs/chart_impressions.png"):
    from analytics import load_tweet_stats
    plt = _setup_matplotlib()

    rows = load_tweet_stats()
    if not rows:
        print("ツイート統計データがありません")
        return

    # 日付ごとにインプレッション合計
    by_date: dict[str, int] = {}
    for r in rows:
        d = r["date"]
        by_date[d] = by_date.get(d, 0) + int(r.get("impressions") or 0)

    dates = sorted(by_date.keys())
    impressions = [by_date[d] for d in dates]

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(dates, impressions, color="#1DA1F2", alpha=0.8)
    ax.set_xticklabels(dates, rotation=45, ha="right", fontsize=8)
    ax.set_title("日別インプレッション数", fontsize=14)
    ax.set_ylabel("インプレッション数")
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.savefig(output, dpi=150)
    plt.close()
    print(f"保存: {output}")


def chart_engagement(output: str = "logs/chart_engagement.png"):
    from analytics import load_tweet_stats
    plt = _setup_matplotlib()

    rows = load_tweet_stats()
    if not rows:
        print("ツイート統計データがありません")
        return

    # エンゲージメント率の高い上位10ツイート
    sorted_rows = sorted(rows, key=lambda x: float(x.get("engagement_rate") or 0), reverse=True)[:10]
    labels = [r["tweet_preview"][:20] + "..." for r in sorted_rows]
    rates = [float(r.get("engagement_rate") or 0) for r in sorted_rows]

    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.barh(labels[::-1], rates[::-1], color="#17BF63", alpha=0.8)
    ax.bar_label(bars, fmt="%.1f%%", padding=3, fontsize=8)
    ax.set_title("エンゲージメント率 上位ツイート", fontsize=14)
    ax.set_xlabel("エンゲージメント率 (%)")
    plt.tight_layout()
    plt.savefig(output, dpi=150)
    plt.close()
    print(f"保存: {output}")


def run_all():
    print("\nグラフ生成中...")
    chart_followers()
    chart_impressions()
    chart_engagement()
    print("\n全グラフ生成完了:")
    print("  logs/chart_followers.png   - フォロワー数推移")
    print("  logs/chart_impressions.png - 日別インプレッション")
    print("  logs/chart_engagement.png  - エンゲージメント率上位")

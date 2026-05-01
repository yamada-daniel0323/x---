import csv
import logging
import random
import yaml
from pathlib import Path
import anthropic

logger = logging.getLogger(__name__)

# モジュールレベルでクライアントを生成（プロンプトキャッシュの再利用に必要）
client = anthropic.Anthropic()

SYSTEM_PROMPT = """あなたはアダルト向けAI生成漫画・イラストを扱うXアカウントの中の人です。
バズっているツイートを参考に、オリジナルの投稿文を日本語で作成してください。

ルール:
- 元のツイートを丸コピーしない（表現・構成を変える）
- 280文字以内
- 絵文字を適度に使って親しみやすく
- ハッシュタグは1〜3個（#AI漫画 #AIイラスト #R18 など関連タグから選ぶ）
- 艶っぽさ・刺激的な表現を含めてよい（過激すぎない範囲で）
- 投稿文のみ出力（説明文・前置き不要）"""


def load_config() -> dict:
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_buzz_tweets(filepath: str, limit: int = 20) -> list[dict]:
    if not Path(filepath).exists():
        return []
    tweets = []
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tweets.append(row)
    # いいね数でソート済みを想定しているが念のため
    tweets.sort(key=lambda x: int(x.get("likes", 0) or 0), reverse=True)
    return tweets[:limit]


def build_user_prompt(buzz_tweets: list[dict]) -> str:
    samples = "\n".join(
        f"- いいね{t.get('likes', '?')}件: {t['text'][:100]}"
        for t in buzz_tweets[:10]
    )
    return f"""以下のバズツイートを参考にして、オリジナルの投稿文を1つ作成してください。

【参考バズツイート】
{samples}

投稿文:"""


def generate_tweet(buzz_filepath: str = None) -> str | None:
    config = load_config()
    if buzz_filepath is None:
        buzz_filepath = config["scraping"]["output_file"]

    buzz = load_buzz_tweets(buzz_filepath)
    if not buzz:
        logger.warning("バズツイートが見つかりません。generator をスキップします。")
        return None

    # バズツイートをシャッフルして多様性を出す
    sample = random.sample(buzz, min(10, len(buzz)))

    try:
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=300,
            system=[{
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": build_user_prompt(sample)}],
        )
        cache_read = getattr(response.usage, "cache_read_input_tokens", 0)
        if cache_read:
            logger.debug(f"プロンプトキャッシュヒット: {cache_read} tokens")
        text = response.content[0].text.strip()
        logger.info(f"生成ツイート: {text[:50]}...")
        return text
    except Exception as e:
        logger.error(f"Claude API エラー: {e}", exc_info=True)
        return None


def generate_and_save(count: int = 5, output_file: str = None):
    """バズネタからツイートを生成してtweets.csvに追記する"""
    config = load_config()
    if output_file is None:
        output_file = config["content"]["file"]

    # 既存テキストを読み込んで重複を避ける
    existing = set()
    if Path(output_file).exists():
        with open(output_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing.add(row["text"].strip())

    generated = []
    for i in range(count):
        text = generate_tweet()
        if text and text not in existing:
            generated.append({"text": text, "image": ""})
            existing.add(text)
            logger.info(f"生成 {i+1}/{count} 完了")

    if generated:
        with open(output_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["text", "image"])
            for entry in generated:
                writer.writerow(entry)
        logger.info(f"tweets.csvに{len(generated)}件の生成ツイートを追記しました")
    else:
        logger.warning("生成できたツイートがありませんでした")

    return generated


def run():
    """CLIから直接実行する場合のエントリポイント"""
    import sys
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    results = generate_and_save(count)
    print(f"\n生成ツイート {len(results)}件:")
    for r in results:
        print(f"\n{'='*40}\n{r['text']}")

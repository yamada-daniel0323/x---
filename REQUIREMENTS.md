# X自動投稿ツール 要件定義書

最終更新: 2026-04-22

---

## 1. システム概要

アダルト向けAI生成漫画・イラストに特化したXアカウントの運用を自動化するツール。
Playwright によるブラウザ自動化で投稿・収集を行い、Claude API によるオリジナル文章生成とスケジューラーによる定期実行を組み合わせて、ほぼ無人でアカウントを運営する。

---

## 2. 機能一覧

### 2.1 自動投稿

| 項目 | 内容 |
|------|------|
| 投稿方法 | Playwright + stealth でブラウザを操作し、X.com から直接投稿 |
| テキスト入力 | DraftJS エディタに CompositionEvent + execCommand で日本語入力 |
| 投稿トリガー | Ctrl+Enter でサブミット |
| 画像添付 | `input[data-testid="fileInput"]` への `set_input_files()` |
| 人間らしさ | マウス曲線移動・ランダムスリープ・タイムラインスクロール |
| セッション管理 | `session.json`（Playwright storage_state）でログイン状態を保持 |
| ログイン自動化 | セッション切れ時に username/password + 中間認証ステップを自動処理 |

### 2.2 スケジューラー

| 項目 | 内容 |
|------|------|
| 投稿スケジュール | `config.yaml` の `schedule.times` で複数時刻を指定 |
| 時刻ゆらぎ | ±15分のランダム遅延（同一時刻の繰り返しを回避） |
| 収集スケジュール | 毎日 `scrape_time`（デフォルト 07:00）にバズネタ収集 |
| アナリティクス | 毎日 `analytics_time`（デフォルト 23:30）に自動取得 |

### 2.3 コンテンツ管理

| 項目 | 内容 |
|------|------|
| 投稿ソース | `tweets.csv`（`text`, `image` の2カラム） |
| 選択モード | `random`（未投稿優先）/ `sequential`（順番通り） |
| 重複回避 | MD5ハッシュで投稿済みテキストを管理（`logs/post_history.csv`） |
| 画像 | `images/` フォルダに事前配置、CSV の `image` カラムでパス指定 |
| 画像なし投稿 | `image` カラムが空でもテキストのみ投稿 |

### 2.4 バズネタ収集（スクレイパー）

| 項目 | 内容 |
|------|------|
| 収集方法 | X.com のキーワード検索（`/search?q=...&f=top`） |
| 収集対象 | `config.yaml` の `scraping.keywords` に設定したキーワード・ハッシュタグ |
| アカウント監視 | `scraping.accounts` にアカウント名を設定すると個別タイムラインも収集 |
| フィルタ | `min_likes` 以上のいいね数のツイートのみ保存 |
| 出力 | `buzz_tweets.csv`（source, account, tweet_id, likes, retweets, text, url） |
| いいね数パース | aria-label から正規表現で取得（万・K・M 単位に対応） |

現在のキーワード設定（アダルトAI漫画特化）:
```
#AI漫画 #R18 -is:retweet
#AI生成漫画 -is:retweet
#AIイラスト #R18 -is:retweet
AI生成 漫画 R18 -is:retweet
```

### 2.5 AI ツイート生成（ジェネレーター）

| 項目 | 内容 |
|------|------|
| 使用モデル | Claude Haiku 4.5（`claude-haiku-4-5`） |
| 入力 | `buzz_tweets.csv` の上位10件をサンプリング |
| 出力 | 280文字以内のオリジナル日本語ツイート |
| スタイル | バズツイートを「参考」にしてオリジナル文を生成（丸コピー禁止） |
| 生成件数 | `config.yaml` の `generate_count`（デフォルト 5件/日） |
| 追記先 | `tweets.csv`（既存テキストと重複チェックあり） |
| 自動化タイミング | スクレイプ完了直後にスケジューラーが自動実行 |

### 2.6 アナリティクス

| 項目 | 内容 |
|------|------|
| 取得先 | `analytics.twitter.com` をブラウザで直接スクレイピング |
| 取得データ | フォロワー数・28日間インプレッション・28日間エンゲージメント・ツイート別統計 |
| 保存先 | `logs/followers_history.csv` / `logs/tweet_stats.csv` |

### 2.7 グラフ生成

| グラフ | ファイル |
|--------|---------|
| フォロワー数推移 | `logs/chart_followers.png` |
| 日別インプレッション | `logs/chart_impressions.png` |
| エンゲージメント率上位ツイート | `logs/chart_engagement.png` |

---

## 3. システム構成

```
x自動化/
├── main.py               # エントリポイント・CLIコマンド分岐
├── scheduler.py          # スケジューラー（schedule ライブラリ）
├── browser_poster.py     # 投稿ロジック（Playwright）
├── content.py            # tweets.csv からツイート選択
├── generator.py          # Claude API でオリジナル文生成
├── scraper.py            # X.com からバズネタ収集
├── analytics.py          # アナリティクス取得・保存
├── chart.py              # グラフ生成（matplotlib）
├── history.py            # 投稿履歴管理
├── import_cookies.py     # Cookie-Editor JSON → session.json 変換
├── config.yaml           # 設定ファイル
├── .env                  # 認証情報（X_USERNAME, X_PASSWORD, ANTHROPIC_API_KEY）
├── tweets.csv            # 投稿ソース（text, image）
├── buzz_tweets.csv       # 収集済みバズツイート
├── images/               # 投稿用画像置き場
└── logs/
    ├── x_automation.log      # アプリログ
    ├── post_history.csv      # 投稿履歴
    ├── followers_history.csv # フォロワー数履歴
    ├── tweet_stats.csv       # ツイート別統計
    └── chart_*.png           # 生成グラフ
```

---

## 4. データフロー

```
[毎日 07:00]
  scraper.py
    └── X.com キーワード検索でバズツイート収集
    └── buzz_tweets.csv に保存
    └── generator.py でオリジナルツイートを生成
    └── tweets.csv に追記

[毎日 09:00 / 12:00 / 18:00 / 21:00（±15分ゆらぎ）]
  content.py
    └── tweets.csv からランダム選択（未投稿優先）
  browser_poster.py
    └── Playwright でブラウザ起動 → ログイン確認 → 投稿
    └── history.py に結果を記録

[毎日 23:30]
  analytics.py
    └── analytics.twitter.com からデータ取得
    └── followers_history.csv / tweet_stats.csv に保存
```

---

## 5. 設定ファイル（config.yaml）

| キー | デフォルト | 説明 |
|------|-----------|------|
| `schedule.times` | `["09:00","12:00","18:00","21:00"]` | 投稿時刻リスト |
| `schedule.scrape_time` | `"07:00"` | バズネタ収集時刻 |
| `schedule.analytics_time` | `"23:30"` | アナリティクス収集時刻 |
| `content.file` | `"tweets.csv"` | 投稿ソースファイル |
| `content.mode` | `"random"` | `random` / `sequential` |
| `browser.headless` | `false` | ヘッドレスモード |
| `browser.session_file` | `"session.json"` | セッション保存先 |
| `browser.chrome_path` | （空）| 実Chrome のパス。空でPlaywright内蔵Chromium |
| `scraping.keywords` | （上記4件） | 検索キーワードリスト |
| `scraping.accounts` | `[]` | 監視アカウントリスト |
| `scraping.min_likes` | `50` | バズ判定閾値（いいね数） |
| `scraping.tweets_per_account` | `20` | 1キーワードあたり取得数 |
| `scraping.output_file` | `"buzz_tweets.csv"` | 収集結果保存先 |
| `scraping.auto_append` | `false` | buzz_tweets を tweets.csv に直接追記するか |
| `scraping.generate_count` | `5` | Claude で生成するツイート数（0で無効） |
| `logging.level` | `"INFO"` | ログレベル |
| `logging.file` | `"logs/x_automation.log"` | ログファイル |

---

## 6. 環境変数（.env）

| 変数名 | 必須 | 説明 |
|--------|------|------|
| `X_USERNAME` | ○ | X アカウントのユーザー名 |
| `X_PASSWORD` | ○ | X アカウントのパスワード |
| `ANTHROPIC_API_KEY` | ○（生成機能使用時） | Claude API キー |

---

## 7. CLIコマンド

```bash
python main.py                  # スケジューラー起動（常時稼働）
python main.py --now            # 即時テスト投稿（確認プロンプトあり）
python main.py --generate       # バズネタからツイートを生成してtweets.csvに追記
python main.py --scrape         # バズネタ収集のみ手動実行
python main.py --analytics      # アナリティクス取得のみ手動実行
python main.py --analytics --chart  # アナリティクス取得 + グラフ生成
python main.py --chart          # グラフ生成のみ（保存済みデータから）
python main.py --history        # 投稿履歴を表示（デフォルト20件）
python main.py --history 50     # 投稿履歴を50件表示
python main.py --reset-session  # session.json を削除（次回起動時に再ログイン）
python import_cookies.py        # Cookie-Editor エクスポートJSONをsession.jsonに変換
```

---

## 8. 依存ライブラリ

```
playwright
playwright-stealth
schedule
pyyaml
python-dotenv
anthropic
matplotlib
japanize-matplotlib  # オプション（グラフの日本語表示）
```

---

## 9. ボット対策（stealth）

- `playwright-stealth` で自動化シグナルを除去
- ランダム UA（Chrome / Firefox 複数バージョン）
- ランダムビューポートサイズ（1280〜1920 × 800〜1080）
- `ja-JP` ロケール・`Asia/Tokyo` タイムゾーン設定
- マウスをベジェ曲線的にランダム移動してからクリック
- 投稿前にタイムラインをランダム量スクロール（人間が読むふり）
- 投稿時刻に ±15分のランダム遅延
- Cookie-Editor からエクスポートしたセッションを再利用してログイン回避

---

## 10. 今後の拡張候補（未実装）

- Flask ベースの Web UI（`app.py` が存在するが未接続）
- 生成ツイートのキュー管理（今は直接 tweets.csv に追記）
- 投稿パフォーマンスによる自動キーワードチューニング
- リプライ・いいね等のエンゲージメント自動化
- 複数アカウント対応

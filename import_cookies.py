"""
Cookie-Editor等のChrome拡張でエクスポートしたcookies.jsonを
Playwrightのsession.jsonに変換してインポートする。

使い方:
  1. Chromeで x.com にログインした状態で
     Cookie-Editor拡張 → Export → JSON でコピー
  2. プロジェクトフォルダに cookies.json として保存
  3. python import_cookies.py を実行
"""
import json
import time
import yaml
from pathlib import Path


COOKIES_FILE = "cookies.json"
CONFIG_FILE = "config.yaml"


def load_config() -> dict:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


SAME_SITE_MAP = {
    "no_restriction": "None",
    "lax": "Lax",
    "strict": "Strict",
    "none": "None",
}

def convert_cookies(raw_cookies: list) -> list:
    """Cookie-Editor形式 → Playwright形式に変換"""
    converted = []
    for c in raw_cookies:
        raw_ss = (c.get("sameSite") or "").lower()
        same_site = SAME_SITE_MAP.get(raw_ss, "Lax")
        cookie = {
            "name": c["name"],
            "value": c["value"],
            "domain": c.get("domain", ".x.com"),
            "path": c.get("path", "/"),
            "secure": c.get("secure", True),
            "httpOnly": c.get("httpOnly", False),
            "sameSite": same_site,
        }
        # expires: Cookie-EditorはUNIX秒、Playwrightも同じ
        if "expirationDate" in c:
            cookie["expires"] = int(c["expirationDate"])
        elif "expires" in c and c["expires"] not in (-1, None):
            cookie["expires"] = int(c["expires"])
        else:
            cookie["expires"] = int(time.time()) + 86400 * 30  # 30日後
        converted.append(cookie)
    return converted


def main():
    if not Path(COOKIES_FILE).exists():
        print(f"[エラー] {COOKIES_FILE} が見つかりません。")
        print("Cookie-Editor拡張でExport → JSONしてcookies.jsonとして保存してください。")
        return

    config = load_config()
    session_file = config["browser"]["session_file"]

    with open(COOKIES_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)

    # Cookie-EditorはリストかDict形式がある
    if isinstance(raw, dict) and "cookies" in raw:
        raw = raw["cookies"]

    cookies = convert_cookies(raw)

    session = {
        "cookies": cookies,
        "origins": [],
    }

    with open(session_file, "w", encoding="utf-8") as f:
        json.dump(session, f, ensure_ascii=False, indent=2)

    print(f"変換完了: {len(cookies)}個のCookieを {session_file} に保存しました。")
    print("次回の投稿からこのセッションが自動的に使われます。")


if __name__ == "__main__":
    main()

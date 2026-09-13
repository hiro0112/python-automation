"""Playwright を使って quotes.toscrape.com/js（JavaScriptで名言が描画されるページ）から
名言テキストと著者名を収集するスクレイピングスクリプト。

- 対象サイト: https://quotes.toscrape.com/js
- 取得項目: 名言テキスト / 著者名
- 出力: quotes_YYYYMMDD.md （Markdown形式） / quotes_YYYYMMDD.png（ページのスクリーンショット）
- 実行モード: ブラウザを画面に表示して実行（headless=False）
- robots.txt を確認し、許可されていないパスへはアクセスしない
- リクエストの間に 1〜3 秒のランダムな待機時間を設ける
- 接続エラー発生時はログにエラーを出力してスクリプトを終了する

使い方:
    python scrape_quotes.py

事前準備:
    pip install playwright
    playwright install chromium
"""

from __future__ import annotations

import logging
import random
import sys
import time
from datetime import date
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

BASE_URL = "https://quotes.toscrape.com/"
TARGET_URL = urljoin(BASE_URL, "js")
ROBOTS_URL = urljoin(BASE_URL, "robots.txt")
USER_AGENT = "python-automation-scraper/1.0 (+https://github.com/hiro0112/python-automation)"
NAV_TIMEOUT_MS = 15_000
MIN_WAIT_SEC = 1.0
MAX_WAIT_SEC = 3.0

LOG_FILE = "scrape_quotes.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# Windowsコンソールの既定コードページ（例: cp932）による文字化けを防ぐため、
# 標準出力をUTF-8に固定する。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def load_robot_parser(robots_url: str) -> RobotFileParser:
    """robots.txt を読み込む。取得できない場合は全許可扱いとする。"""
    rp = RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.read()
        logger.info("robots.txt を読み込みました: %s", robots_url)
    except Exception as exc:  # noqa: BLE001 - robots.txt 取得失敗時は全許可として続行
        logger.warning("robots.txt の読み込みに失敗しました（全許可として扱います）: %s", exc)
    return rp


def can_fetch(rp: RobotFileParser, url: str) -> bool:
    allowed = rp.can_fetch(USER_AGENT, url)
    if not allowed:
        logger.warning("robots.txt により禁止されているためアクセスをスキップします: %s", url)
    return allowed


def wait_politely() -> None:
    wait_sec = random.uniform(MIN_WAIT_SEC, MAX_WAIT_SEC)
    logger.info("次のリクエストまで %.2f 秒待機します", wait_sec)
    time.sleep(wait_sec)


def scrape_quotes(target_url: str, screenshot_path: str) -> list[dict]:
    """Playwright でページを描画し、名言テキストと著者名、スクリーンショットを取得する。"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        try:
            page = browser.new_page()
            page.set_default_timeout(NAV_TIMEOUT_MS)
            page.goto(target_url, wait_until="networkidle")
            page.wait_for_selector(".quote", timeout=NAV_TIMEOUT_MS)

            page.screenshot(path=screenshot_path, full_page=True)
            logger.info("スクリーンショットを保存しました: %s", screenshot_path)

            quotes = []
            quote_elements = page.locator(".quote")
            count = quote_elements.count()
            for i in range(count):
                element = quote_elements.nth(i)
                text = element.locator(".text").inner_text().strip()
                author = element.locator(".author").inner_text().strip()
                quotes.append({"text": text, "author": author})

            logger.info("%s から %d 件の名言を取得しました", target_url, len(quotes))
            return quotes
        finally:
            browser.close()


def save_as_markdown(quotes: list[dict], output_path: str, source_url: str) -> None:
    """収集した名言をMarkdown形式で保存する。"""
    today_str = date.today().strftime("%Y-%m-%d")
    lines = [
        "# quotes.toscrape.com 名言集",
        "",
        f"- 取得日: {today_str}",
        f"- 収集元: {source_url}",
        f"- 件数: {len(quotes)} 件",
        "",
        "| 名言 | 著者 |",
        "| --- | --- |",
    ]
    for quote in quotes:
        text = quote["text"].replace("|", "\\|")
        author = quote["author"].replace("|", "\\|")
        lines.append(f"| {text} | {author} |")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    logger.info("Markdownファイルを保存しました: %s", output_path)


def main() -> None:
    logger.info("スクレイピングを開始します: %s", TARGET_URL)

    rp = load_robot_parser(ROBOTS_URL)

    if not can_fetch(rp, TARGET_URL):
        logger.error("対象ページへのアクセスが robots.txt により禁止されています。終了します。")
        sys.exit(1)

    wait_politely()

    today_compact = date.today().strftime("%Y%m%d")
    markdown_path = f"quotes_{today_compact}.md"
    screenshot_path = f"quotes_{today_compact}.png"

    try:
        quotes = scrape_quotes(TARGET_URL, screenshot_path)
    except PlaywrightTimeoutError as exc:
        logger.error("接続エラーが発生しました（タイムアウト） (%s): %s", TARGET_URL, exc)
        sys.exit(1)
    except PlaywrightError as exc:
        logger.error("接続エラーが発生しました (%s): %s", TARGET_URL, exc)
        sys.exit(1)

    if not quotes:
        logger.warning("名言が1件も取得できませんでした。")

    save_as_markdown(quotes, markdown_path, TARGET_URL)

    logger.info("スクレイピングが完了しました。合計 %d 件の名言を取得しました。", len(quotes))


if __name__ == "__main__":
    main()

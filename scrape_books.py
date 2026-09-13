"""books.toscrape.com から書籍情報（タイトル・価格・在庫状況）を収集するスクレイピングスクリプト。

- 対象サイト: https://books.toscrape.com/
- 取得項目: 書籍タイトル / 価格 / 在庫状況
- 出力: books_YYYYMMDD.md （Markdown形式）
- robots.txt を確認し、許可されていないパスへはアクセスしない
- 各リクエストの間に 1〜3 秒のランダムな待機時間を設ける
- 接続エラー発生時はログにエラーを出力してスクリプトを終了する

使い方:
    python scrape_books.py
"""

from __future__ import annotations

import logging
import random
import sys
import time
from datetime import date
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import requests
import truststore
from bs4 import BeautifulSoup

# Windows環境ではセキュリティソフト等がTLS通信を検査するために独自のルート証明書を
# 利用している場合があり、certifi同梱のCA一覧だけでは証明書検証に失敗することがある。
# OSの証明書ストアを利用して検証するように差し替える（検証自体は無効化しない）。
truststore.inject_into_ssl()

# Windowsコンソールの既定コードページ（例: cp932）による文字化けを防ぐため、
# 標準出力をUTF-8に固定する。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_URL = "https://books.toscrape.com/"
ROBOTS_URL = urljoin(BASE_URL, "robots.txt")
USER_AGENT = "python-automation-scraper/1.0 (+https://github.com/hiro0112/python-automation)"
REQUEST_TIMEOUT = 10  # seconds
MIN_WAIT_SEC = 1.0
MAX_WAIT_SEC = 3.0

LOG_FILE = "scrape_books.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


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


def fetch_html(session: requests.Session, url: str) -> str:
    """指定URLのHTMLを取得する。接続エラー時はログを出力して終了する。"""
    try:
        response = session.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        logger.error("接続エラーが発生しました (%s): %s", url, exc)
        sys.exit(1)
    response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def parse_books_from_page(html: str, page_url: str) -> list[dict]:
    """一覧ページのHTMLから書籍情報（タイトル・価格・在庫状況）を抽出する。"""
    soup = BeautifulSoup(html, "html.parser")
    books = []
    for article in soup.select("article.product_pod"):
        title_tag = article.select_one("h3 a")
        title = title_tag["title"].strip() if title_tag and title_tag.has_attr("title") else "不明"

        price_tag = article.select_one("p.price_color")
        price = price_tag.get_text(strip=True) if price_tag else "不明"

        availability_tag = article.select_one("p.instock.availability")
        availability = availability_tag.get_text(strip=True) if availability_tag else "不明"

        books.append({"title": title, "price": price, "availability": availability})

    logger.info("%s から %d 件の書籍情報を取得しました", page_url, len(books))
    return books


def get_next_page_url(html: str, current_url: str) -> str | None:
    """一覧ページの「next」リンクがあれば絶対URLを返す。無ければ None。"""
    soup = BeautifulSoup(html, "html.parser")
    next_tag = soup.select_one("li.next a")
    if next_tag and next_tag.has_attr("href"):
        return urljoin(current_url, next_tag["href"])
    return None


def scrape_all_books(rp: RobotFileParser) -> list[dict]:
    """全ページを巡回して書籍情報を収集する。"""
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    all_books: list[dict] = []
    current_url = urljoin(BASE_URL, "catalogue/page-1.html")
    is_first_request = True

    while current_url:
        if not can_fetch(rp, current_url):
            break

        if not is_first_request:
            wait_sec = random.uniform(MIN_WAIT_SEC, MAX_WAIT_SEC)
            logger.info("次のリクエストまで %.2f 秒待機します", wait_sec)
            time.sleep(wait_sec)
        is_first_request = False

        html = fetch_html(session, current_url)
        all_books.extend(parse_books_from_page(html, current_url))
        current_url = get_next_page_url(html, current_url)

    return all_books


def save_as_markdown(books: list[dict], output_path: str) -> None:
    """収集した書籍情報をMarkdown形式で保存する。"""
    today_str = date.today().strftime("%Y-%m-%d")
    lines = [
        "# books.toscrape.com 書籍情報",
        "",
        f"- 取得日: {today_str}",
        f"- 収集元: {BASE_URL}",
        f"- 件数: {len(books)} 件",
        "",
        "| タイトル | 価格 | 在庫状況 |",
        "| --- | --- | --- |",
    ]
    for book in books:
        title = book["title"].replace("|", "\\|")
        lines.append(f"| {title} | {book['price']} | {book['availability']} |")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    logger.info("Markdownファイルを保存しました: %s", output_path)


def main() -> None:
    logger.info("スクレイピングを開始します: %s", BASE_URL)

    rp = load_robot_parser(ROBOTS_URL)

    if not can_fetch(rp, BASE_URL):
        logger.error("トップページへのアクセスが robots.txt により禁止されています。終了します。")
        sys.exit(1)

    books = scrape_all_books(rp)

    if not books:
        logger.warning("書籍情報が1件も取得できませんでした。")

    output_filename = f"books_{date.today().strftime('%Y%m%d')}.md"
    save_as_markdown(books, output_filename)

    logger.info("スクレイピングが完了しました。合計 %d 件の書籍情報を取得しました。", len(books))


if __name__ == "__main__":
    main()

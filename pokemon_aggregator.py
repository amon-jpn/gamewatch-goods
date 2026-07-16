# -*- coding: utf-8 -*-
"""ポケモンカード コレクター向けニュースアグリゲーター

Google News RSS の検索クエリをソースとして、コレクター（PSA鑑定・相場・
新弾情報などに関心がある人）向けの記事だけをキーワードスコアリングで厳選し、
archive.json に蓄積したうえで pokemon_news.xml (RSS) を生成する。

引き継ぎメモ:
- ソースを追加したい      → SOURCES にエントリを足す
- 絞り込みを調整したい    → POSITIVE_KEYWORDS / NEGATIVE_KEYWORDS / SCORE_THRESHOLD
- 掲載件数・保持期間      → FEED_MAX_ITEMS / ARCHIVE_DAYS
"""

import difflib
import json
import os
import re
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

import feedparser
from feedgen.feed import FeedGenerator

import llm_utils

REPO_URL = "https://github.com/amon-jpn/pokemon_aggregator"
ICON_URL = "https://raw.githubusercontent.com/amon-jpn/pokemon_aggregator/main/pikabou.jpg"
OUTPUT_FILE = "pokemon_news.xml"
ARCHIVE_FILE = "archive.json"

ARCHIVE_DAYS = 45          # 記事履歴の保持日数（重複判定と掲載の対象期間）
FEED_MAX_ITEMS = 60        # RSSに載せる最大件数
SIMILARITY_THRESHOLD = 0.85  # タイトル類似度がこれを超えたら重複とみなす
SCORE_THRESHOLD = 3        # 合計スコアがこの値以上の記事だけ採用
SUMMARIZE_MAX_PER_RUN = 50  # 1回の実行でLLM要約を付ける最大記事数


def google_news_url(query: str) -> str:
    """Google News の検索クエリをRSS URLに変換する"""
    q = urllib.parse.quote(query)
    return f"https://news.google.com/rss/search?q={q}&hl=ja&gl=JP&ceid=JP:ja"


# カテゴリごとの取得ソース。同じ記事が複数クエリにヒットした場合は
# 先に書いたカテゴリが優先される。
SOURCES = [
    {
        "category": "鑑定・PSA",
        "url": google_news_url('"ポケカ" OR "ポケモンカード" PSA OR BGS OR 鑑定'),
    },
    {
        "category": "相場・高騰",
        "url": google_news_url('"ポケカ" OR "ポケモンカード" 高騰 OR 相場 OR 買取'),
    },
    {
        "category": "新弾・予約",
        "url": google_news_url('"ポケカ" OR "ポケモンカード" 新弾 OR 抽選 OR 予約 OR 発売 OR 収録'),
    },
]

# 加点キーワード（値はスコア）。英字は大文字小文字を区別しない。
POSITIVE_KEYWORDS = {
    "PSA": 3,
    "BGS": 3,
    "鑑定": 3,
    "グレーディング": 2,
    "ポケカ": 2,
    "ポケモンカード": 2,
    "高騰": 2,
    "相場": 2,
    "買取": 2,
    "抽選": 2,
    "新弾": 2,
    "拡張パック": 2,
    "プロモ": 2,
    "SAR": 2,
    "予約": 1,
    "発売": 1,
    "収録": 1,
    "開封": 1,
    "レアリティ": 1,
    "コレクション": 1,
}

# 減点キーワード（コレクター無関係の話題を弾く）
NEGATIVE_KEYWORDS = {
    "ポケポケ": -5,  # スマホアプリ版（物理カードではない）
    "ポケモンGO": -5,
    "ポケモンスリープ": -5,
    "ポケモンユナイト": -5,
    "レイド": -4,
    "攻略": -3,
    "アニメ": -3,
    "映画": -3,
    "劇場版": -3,
    "ぬいぐるみ": -2,
}


# スパム転載サイトの排除。タイトル末尾のランダム英数字ID や
# ツイート本文のURL断片は、SNS転載スパムに典型的なパターン。
SPAM_TITLE_PATTERN = re.compile(r"\([A-Za-z0-9]{6,}\)\s*$|https?://")
BLOCKED_SOURCES = {"KuCoin"}


def is_spam(title, source_name):
    return bool(SPAM_TITLE_PATTERN.search(title)) or source_name in BLOCKED_SOURCES


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "").strip()


def score_text(text: str) -> int:
    """加点・減点キーワードの合計スコアを返す"""
    upper = text.upper()
    score = 0
    for word, weight in POSITIVE_KEYWORDS.items():
        if word.upper() in upper:
            score += weight
    for word, weight in NEGATIVE_KEYWORDS.items():
        if word.upper() in upper:
            score += weight
    return score


def clean_title(entry):
    """Google Newsのタイトル「記事名 - 媒体名」を分離して返す"""
    title = entry.get("title", "").strip()
    source_name = ""
    if hasattr(entry, "source") and entry.source.get("title"):
        source_name = entry.source["title"].strip()
        suffix = f" - {source_name}"
        if title.endswith(suffix):
            title = title[: -len(suffix)].strip()
    return title, source_name


def entry_date(entry):
    if getattr(entry, "published_parsed", None):
        return datetime.fromtimestamp(time.mktime(entry.published_parsed), tz=timezone.utc)
    return datetime.now(timezone.utc)


def load_archive():
    if not os.path.exists(ARCHIVE_FILE):
        return []
    with open(ARCHIVE_FILE, encoding="utf-8") as f:
        return json.load(f).get("entries", [])


def save_archive(entries):
    with open(ARCHIVE_FILE, "w", encoding="utf-8") as f:
        json.dump({"entries": entries}, f, ensure_ascii=False, indent=1)


def is_duplicate(title, known_titles):
    return any(
        difflib.SequenceMatcher(None, title, seen).ratio() > SIMILARITY_THRESHOLD
        for seen in known_titles
    )


def collect():
    """全ソースを取得し、スコア閾値を超えた記事候補を返す"""
    candidates = []
    for source in SOURCES:
        print(f"📡 取得中 [{source['category']}]")
        feed = feedparser.parse(source["url"])
        for entry in feed.entries:
            title, source_name = clean_title(entry)
            if not title or not entry.get("link"):
                continue
            if is_spam(title, source_name):
                continue
            summary = strip_html(entry.get("summary", ""))
            score = score_text(f"{title} {summary}")
            if score < SCORE_THRESHOLD:
                continue
            candidates.append(
                {
                    "title": title,
                    "link": entry.link,
                    "source": source_name,
                    "category": source["category"],
                    "score": score,
                    "published": entry_date(entry).isoformat(),
                }
            )
    return candidates


def merge_into_archive(archive, candidates):
    """候補をアーカイブへ重複排除しながら統合する"""
    known_links = {e["link"] for e in archive}
    known_titles = [e["title"] for e in archive]
    added = 0
    for item in sorted(candidates, key=lambda x: x["published"], reverse=True):
        if item["link"] in known_links:
            continue
        if is_duplicate(item["title"], known_titles):
            continue
        archive.append(item)
        known_links.add(item["link"])
        known_titles.append(item["title"])
        added += 1

    cutoff = (datetime.now(timezone.utc) - timedelta(days=ARCHIVE_DAYS)).isoformat()
    archive = [e for e in archive if e["published"] >= cutoff]
    archive.sort(key=lambda e: e["published"], reverse=True)
    return archive, added


def build_feed(entries):
    fg = FeedGenerator()
    fg.id(REPO_URL)
    fg.title("ポケカ コレクターニュース")
    fg.description(
        "PSA鑑定・相場・新弾情報など、ポケモンカードのコレクターに関係する"
        "ニュースだけを自動収集・重複排除して配信するRSSフィードです"
    )
    fg.link(href=REPO_URL, rel="alternate")
    fg.language("ja")
    fg.lastBuildDate(datetime.now(timezone.utc))
    fg.image(url=ICON_URL, title="ポケカ コレクターニュース", link=REPO_URL)

    for item in entries[:FEED_MAX_ITEMS]:
        fe = fg.add_entry()
        fe.title(f"【{item['category']}】{item['title']}")
        fe.link(href=item["link"])
        source_note = f"出典: {item['source']}" if item["source"] else ""
        if item.get("summary"):
            description = f"{item['summary']}（{source_note}）" if source_note else item["summary"]
        else:
            description = source_note or item["title"]
        fe.description(description)
        fe.pubDate(datetime.fromisoformat(item["published"]))

    rss_content = fg.rss_str(pretty=True).decode("utf-8")
    style_line = '<?xml-stylesheet type="text/xsl" href="style.xsl"?>'
    rss_content = rss_content.replace(
        "<?xml version='1.0' encoding='UTF-8'?>",
        f'<?xml version="1.0" encoding="UTF-8"?>\n{style_line}',
    )
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(rss_content)


def add_summaries(archive):
    """要約がまだ付いていない記事にLLMで一言解説を付ける（キー未設定ならスキップ）"""
    targets = [e for e in archive if "summary" not in e][:SUMMARIZE_MAX_PER_RUN]
    if not targets:
        return
    summaries = llm_utils.summarize_entries(targets)
    if not summaries:
        # キー未設定や失敗時は何も記録せず、次回（キー設定後）に再挑戦できるようにする
        return
    for i, entry in enumerate(targets):
        # 呼び出し成功時は空でも記録し、同じ記事を毎回投げ直さないようにする
        entry["summary"] = summaries.get(i, "")
    print(f"📝 LLM要約を{len(summaries)}件付与しました")


def main():
    archive = load_archive()
    candidates = collect()
    archive, added = merge_into_archive(archive, candidates)
    add_summaries(archive)
    save_archive(archive)
    build_feed(archive)
    print(f"✅ 完了: 新着{added}件 / アーカイブ{len(archive)}件 / フィード掲載{min(len(archive), FEED_MAX_ITEMS)}件")


if __name__ == "__main__":
    main()

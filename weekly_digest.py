# -*- coding: utf-8 -*-
"""週刊ポケカ高騰ダイジェスト生成スクリプト

archive.json（pokemon_aggregator.py が蓄積した記事履歴）から直近7日分を取り出し、
Claude で週刊ダイジェスト（Markdown）を生成して以下を出力する:

- digests/YYYY-MM-DD.md : ダイジェスト本文（アーカイブ）
- digest.xml            : 週刊ダイジェスト購読用RSS（直近12週分）

ANTHROPIC_API_KEY が未設定の場合は、LLMなしで記事リストだけの
シンプルなダイジェストにフォールバックする。
"""

import json
import os
from datetime import datetime, timedelta, timezone

import markdown as md
from feedgen.feed import FeedGenerator

import llm_utils
import site_builder

ARCHIVE_FILE = "archive.json"
DIGEST_DIR = "digests"
DIGEST_FEED_FILE = "digest.xml"
FEED_MAX_DIGESTS = 12  # RSSに載せる週数
PAGES_URL = "https://amon-jpn.github.io/pokemon_aggregator"
REPO_URL = "https://github.com/amon-jpn/pokemon_aggregator"

JST = timezone(timedelta(hours=9))


def load_week_entries():
    if not os.path.exists(ARCHIVE_FILE):
        return []
    with open(ARCHIVE_FILE, encoding="utf-8") as f:
        entries = json.load(f).get("entries", [])
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    return [e for e in entries if e["published"] >= cutoff]


def fallback_body(entries):
    """LLMが使えないときの、記事リストだけのダイジェスト"""
    lines = ["## 今週の記事一覧", ""]
    by_category = {}
    for e in entries:
        by_category.setdefault(e["category"], []).append(e)
    for category, items in by_category.items():
        lines.append(f"### {category}")
        for e in items:
            source = f"（{e['source']}）" if e.get("source") else ""
            url = e.get("real_url") or e["link"]
            title = e.get("title_ja") or e["title"]
            lines.append(f"- [{title}]({url}){source}")
        lines.append("")
    return "\n".join(lines).strip()


def build_digest_feed(digest_files):
    """digests/ 内のMarkdownからRSSフィードを生成する"""
    fg = FeedGenerator()
    fg.id(f"{PAGES_URL}/digest.xml")
    fg.title("週刊ポケカ高騰ダイジェスト")
    fg.description(
        "1週間分のポケモンカード相場・高騰・鑑定・新弾ニュースをまとめた週刊ダイジェストです"
    )
    fg.link(href=REPO_URL, rel="alternate")
    fg.language("ja")
    fg.lastBuildDate(datetime.now(timezone.utc))

    for filename in sorted(digest_files, reverse=True)[:FEED_MAX_DIGESTS]:
        date_str = filename.replace(".md", "")
        with open(os.path.join(DIGEST_DIR, filename), encoding="utf-8") as f:
            body_md = f.read()
        fe = fg.add_entry()
        fe.title(f"週刊ポケカ高騰ダイジェスト（{date_str}）")
        fe.link(href=f"{REPO_URL}/blob/main/{DIGEST_DIR}/{filename}")
        fe.description(md.markdown(body_md))
        fe.pubDate(datetime.fromisoformat(date_str).replace(hour=21, tzinfo=JST))

    with open(DIGEST_FEED_FILE, "w", encoding="utf-8") as f:
        f.write(fg.rss_str(pretty=True).decode("utf-8"))


def main():
    entries = load_week_entries()
    if not entries:
        print("今週の記事がないため、ダイジェストは生成しませんでした。")
        return

    today = datetime.now(JST).date().isoformat()
    week_label = f"{(datetime.now(JST) - timedelta(days=7)).date().isoformat()}〜{today}"

    body = llm_utils.generate_digest_body(entries, week_label)
    if body is None:
        print("ℹ️ LLMなしのフォールバック形式で生成します")
        body = fallback_body(entries)
    else:
        # LLM本文には元記事リンクが含まれないため、リンク付き記事一覧を末尾に付ける
        body = f"{body}\n\n{fallback_body(entries)}"

    os.makedirs(DIGEST_DIR, exist_ok=True)
    digest_md = f"# 週刊ポケカ高騰ダイジェスト（{week_label}）\n\n{body}\n"
    path = os.path.join(DIGEST_DIR, f"{today}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(digest_md)

    # サイトのダイジェスト欄用に、日英の箇条書きハイライトも保存する
    highlights = llm_utils.generate_digest_highlights(entries, week_label)
    if highlights:
        with open(path.replace(".md", ".highlights.json"), "w", encoding="utf-8") as f:
            json.dump(highlights, f, ensure_ascii=False, indent=1)
        print(f"✨ ハイライト{len(highlights)}項目を保存しました")

    build_digest_feed([f for f in os.listdir(DIGEST_DIR) if f.endswith(".md")])

    # トップページのダイジェスト欄を最新化する
    with open(ARCHIVE_FILE, encoding="utf-8") as f:
        site_builder.build_site(json.load(f).get("entries", []))

    print(f"✅ 完了: {path}（対象記事{len(entries)}件）と {DIGEST_FEED_FILE} を更新しました")


if __name__ == "__main__":
    main()

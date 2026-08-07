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

import calendar
import difflib
import html
import json
import os
import re
import urllib.parse
from datetime import datetime, timedelta, timezone

import feedparser
import requests
from feedgen.feed import FeedGenerator
from googlenewsdecoder import gnewsdecoder

import llm_utils
import site_builder

REPO_URL = "https://github.com/amon-jpn/pokemon_aggregator"
PAGES_URL = "https://amon-jpn.github.io/pokemon_aggregator"
ICON_URL = f"{PAGES_URL}/pikabou.jpg"
OUTPUT_FILE = "pokemon_news.xml"
ARCHIVE_FILE = "archive.json"

ARCHIVE_DAYS = 45          # 記事履歴の保持日数（重複判定と掲載の対象期間）
FEED_MAX_ITEMS = 60        # RSSに載せる最大件数
SIMILARITY_THRESHOLD = 0.85  # タイトル類似度がこれを超えたら重複とみなす
SCORE_THRESHOLD = 3        # 合計スコアがこの値以上の記事だけ採用
SUMMARIZE_MAX_PER_RUN = 50  # 1回の実行でLLM要約を付ける最大記事数
TRANSLATE_MAX_PER_RUN = 50  # 1回の実行でLLM英訳を付ける最大記事数
ENRICH_MAX_PER_RUN = 30    # 1回の実行で元記事URL・画像を取得する最大記事数
MAX_ATTEMPTS = 3           # URL解決・要約・翻訳の失敗時に再挑戦する回数（実行ごとに1回）


def google_news_url(query: str) -> str:
    """Google News の検索クエリをRSS URLに変換する"""
    q = urllib.parse.quote(query)
    return f"https://news.google.com/rss/search?q={q}&hl=ja&gl=JP&ceid=JP:ja"


def google_news_url_en(query: str) -> str:
    """英語圏Google News の検索クエリをRSS URLに変換する

    PokeBeach等の海外専門サイトはCloudflareで直接アクセスを弾くため、
    Google News経由で取得する（Googleのクロール済みデータが返るので
    こちらから対象サイトへ直接アクセスする必要がない）。
    """
    q = urllib.parse.quote(query)
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


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
    # 海外専門サイト。サイト限定検索なので全記事がTCC関連＝bonusで底上げし、
    # NEGATIVE_KEYWORDS（TCG Pocket等）だけで弾く
    {
        "category": "海外ニュース",
        "url": google_news_url_en("site:pokebeach.com OR site:pokeguardian.com"),
        "bonus": 3,
    },
    {
        "category": "海外ニュース",
        "url": google_news_url_en('"Pokemon TCG" OR "Pokemon cards" PSA OR grading OR market OR price'),
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
    # 英語圏ソース用
    "Pokemon TCG": 2,
    "Pokemon card": 2,  # "Pokemon cards" にも部分一致する
    "grading": 2,
    "graded": 2,
    "reveal": 2,  # revealed / reveals にも一致
    "expansion": 1,
    "market": 1,
    "price": 1,
    "preorder": 1,
    "pre-order": 1,
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
    # 英語圏ソース用（TCG Pocketはポケポケの英語名）
    "TCG Pocket": -5,
    "Pokemon GO": -5,
    "Pokemon Unite": -5,
    "Pokemon Sleep": -5,
    # 競技プレイ（デッキ解説・メタ分析）はコレクター向けではないので弾く
    "in Standard": -3,
    "in Expanded": -3,
    "Format": -2,
}


# スパム転載サイトの排除。タイトル末尾のランダム英数字ID や
# ツイート本文のURL断片は、SNS転載スパムに典型的なパターン。
SPAM_TITLE_PATTERN = re.compile(r"\([A-Za-z0-9]{6,}\)\s*$|https?://")
BLOCKED_SOURCES = {"KuCoin", "ニュースメディアVOIX"}


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
        # published_parsed はUTC。time.mktime はローカル時刻として解釈してしまうため
        # calendar.timegm を使う（CI外のJST環境でも日時がズレない）
        return datetime.fromtimestamp(calendar.timegm(entry.published_parsed), tz=timezone.utc)
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
        # feedparserに直接URLを渡すとタイムアウトなしで待ち続けるため、
        # requestsで30秒制限を付けて取得する。1ソースの失敗で全体は止めない
        try:
            resp = requests.get(
                source["url"], timeout=30,
                headers={"User-Agent": "Mozilla/5.0 (pokemon_aggregator)"},
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"⚠️ 取得失敗のためスキップ [{source['category']}]: {e}")
            continue
        feed = feedparser.parse(resp.content)
        for entry in feed.entries:
            title, source_name = clean_title(entry)
            if not title or not entry.get("link"):
                continue
            if is_spam(title, source_name):
                continue
            summary = strip_html(entry.get("summary", ""))
            score = score_text(f"{title} {summary}") + source.get("bonus", 0)
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
    # 保持期間より古い候補は追加してもすぐ削除されるだけなので最初から弾く
    min_date = (datetime.now(timezone.utc) - timedelta(days=ARCHIVE_DAYS)).isoformat()
    for item in sorted(candidates, key=lambda x: x["published"], reverse=True):
        if item["published"] < min_date:
            continue
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
        # 日本語フィードなので、海外記事はLLMの日本語訳タイトルを優先する
        fe.title(f"【{item['category']}】{item.get('title_ja') or item['title']}")
        # リンクは元記事URL優先。IDはGoogle NewsのURLで固定し、
        # 後からreal_urlが付いてもRSSリーダー上で重複しないようにする
        fe.link(href=item.get("real_url") or item["link"])
        fe.guid(item["link"], permalink=False)
        source_note = f"出典: {item['source']}" if item["source"] else ""
        if item.get("summary"):
            text = f"{item['summary']}（{source_note}）" if source_note else item["summary"]
        else:
            text = source_note or item["title"]
        # 出典名・要約・画像URLは外部由来のため、HTMLに埋め込む前にエスケープする
        description = f"<p>{html.escape(text)}</p>"
        if item.get("image"):
            img_url = html.escape(item["image"], quote=True)
            description = f'<img src="{img_url}" style="max-width:100%"/>{description}'
            fe.enclosure(item["image"], 0, "image/jpeg")
        fe.description(description)
        fe.pubDate(datetime.fromisoformat(item["published"]))

    rss_content = fg.rss_str(pretty=True).decode("utf-8")
    style_line = '<?xml-stylesheet type="text/xsl" href="style.xsl"?>'
    rss_content = rss_content.replace(
        "<?xml version='1.0' encoding='UTF-8'?>",
        f'<?xml version="1.0" encoding="UTF-8"?>\n{style_line}',
    )
    # Feedly等が対応するwebfeeds拡張でフィードアイコンを指定する
    rss_content = rss_content.replace(
        "<rss ", '<rss xmlns:webfeeds="http://webfeeds.org/rss/1.0" ', 1
    )
    rss_content = rss_content.replace(
        "<channel>",
        "<channel>\n"
        f"    <webfeeds:icon>{ICON_URL}</webfeeds:icon>\n"
        f"    <webfeeds:logo>{ICON_URL}</webfeeds:logo>\n"
        "    <webfeeds:accentColor>FFCB05</webfeeds:accentColor>",
        1,
    )
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(rss_content)


OG_IMAGE_PATTERN = re.compile(
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']'
    r'|<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
    re.IGNORECASE,
)


def fetch_og_image(url):
    """記事ページからOGP画像（サムネイル）のURLを取得する"""
    try:
        resp = requests.get(
            url, timeout=10, headers={"User-Agent": "Mozilla/5.0 (pokemon_aggregator)"}
        )
        if not resp.ok:  # エラーページのog:image（無関係な画像）を拾わない
            return ""
        match = OG_IMAGE_PATTERN.search(resp.text[:300000])
        if match:
            return (match.group(1) or match.group(2)).strip()
    except Exception:
        pass
    return ""


def enrich_entries(archive):
    """Google Newsのリダイレクトを元記事URLに変換し、サムネイル画像を取得する

    失敗時は次回実行（6時間後）に再挑戦し、MAX_ATTEMPTS回失敗したら
    空文字を記録して打ち切る（毎回リトライし続けないようにする）。
    """
    targets = [e for e in archive if "real_url" not in e][:ENRICH_MAX_PER_RUN]
    resolved = 0
    for entry in targets:
        real_url = ""
        try:
            result = gnewsdecoder(entry["link"], interval=1)
            if result.get("status"):
                real_url = result["decoded_url"]
        except Exception:
            pass
        if real_url:
            entry["real_url"] = real_url
            entry["image"] = fetch_og_image(real_url)
            entry.pop("enrich_fails", None)
            resolved += 1
        else:
            fails = entry.get("enrich_fails", 0) + 1
            if fails >= MAX_ATTEMPTS:
                entry["real_url"] = ""
                entry["image"] = ""
                entry.pop("enrich_fails", None)
            else:
                entry["enrich_fails"] = fails
    if targets:
        print(f"🖼️ 元記事URL解決 {resolved}/{len(targets)}件")


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
        if i in summaries:
            entry["summary"] = summaries[i]
            entry.pop("summary_fails", None)
        else:
            # LLMが返し損ねた記事は次回に再挑戦し、MAX_ATTEMPTS回で打ち切る
            fails = entry.get("summary_fails", 0) + 1
            if fails >= MAX_ATTEMPTS:
                entry["summary"] = ""
                entry.pop("summary_fails", None)
            else:
                entry["summary_fails"] = fails
    print(f"📝 LLM要約を{len(summaries)}件付与しました")


def add_translations(archive):
    """日本語タイトルがまだない海外記事にLLMで日本語訳を付ける"""
    targets = [
        e for e in archive
        if e["category"] == "海外ニュース" and "title_ja" not in e
    ][:TRANSLATE_MAX_PER_RUN]
    if not targets:
        return
    translations = llm_utils.translate_entries(targets)
    if not translations:
        return
    for i, entry in enumerate(targets):
        if i in translations:
            entry["title_ja"] = translations[i]
            entry.pop("translate_fails", None)
        else:
            fails = entry.get("translate_fails", 0) + 1
            if fails >= MAX_ATTEMPTS:
                entry["title_ja"] = ""
                entry.pop("translate_fails", None)
            else:
                entry["translate_fails"] = fails
    print(f"🌐 日本語訳を{len(translations)}件付与しました")


def main():
    archive = load_archive()
    candidates = collect()
    archive, added = merge_into_archive(archive, candidates)
    enrich_entries(archive)
    add_summaries(archive)
    add_translations(archive)
    save_archive(archive)
    build_feed(archive)
    site_builder.build_site(archive)
    print(f"✅ 完了: 新着{added}件 / アーカイブ{len(archive)}件 / フィード掲載{min(len(archive), FEED_MAX_ITEMS)}件")


if __name__ == "__main__":
    main()

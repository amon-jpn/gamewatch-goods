# -*- coding: utf-8 -*-
"""GitHub Pages用のHTMLマガジン（index.html）生成モジュール

archive.json の記事をカード型UIで一覧表示する静的ページを生成する。
外部CSS/JSに依存しない自己完結型のHTMLを出力し、Pages（mainブランチの
ルート配信）にそのまま載せる。デザイン調整はこのファイル内のCSSを編集する。

日英切り替え: 各テキストを <span class="ja"> / <span class="en"> の対で
埋め込み、bodyのlang-enクラスをJSでトグルして表示を切り替える（再取得なし）。
記事の英訳は pokemon_aggregator.add_translations がLLMで付与する
title_en / summary_en を使い、未翻訳の記事は原文にフォールバックする。
"""

import glob
import html
import os
import re
from datetime import datetime, timedelta, timezone

SITE_FILE = "index.html"
DIGEST_DIR = "digests"
PAGES_URL = "https://amon-jpn.github.io/pokemon_aggregator"
REPO_URL = "https://github.com/amon-jpn/pokemon_aggregator"
PROMO_URL = "https://pockettcg.app/?utm_source=pokeka_news"

JST = timezone(timedelta(hours=9))

WEEKDAYS_JA = "月火水木金土日"
WEEKDAYS_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# カテゴリごとのバッジ色・英語名・サムネイルなし記事のプレースホルダ絵文字
CATEGORY_STYLE = {
    "鑑定・PSA": {"color": "#7c5cbf", "emoji": "🔍", "en": "Grading & PSA"},
    "相場・高騰": {"color": "#2e9e5b", "emoji": "📈", "en": "Market & Prices"},
    "新弾・予約": {"color": "#2a7fc9", "emoji": "🎁", "en": "New Sets & Preorders"},
    "海外ニュース": {"color": "#d0642a", "emoji": "🌏", "en": "International"},
}
DEFAULT_STYLE = {"color": "#8a8a8a", "emoji": "📰", "en": "News"}


def bilingual(ja, en):
    """日英対のspanを返す。表示側はbodyのlang-enクラスで切り替える"""
    return f'<span class="ja">{ja}</span><span class="en">{en}</span>'


def format_dates(iso_str):
    dt = datetime.fromisoformat(iso_str).astimezone(JST)
    ja = f"{dt.month}月{dt.day}日({WEEKDAYS_JA[dt.weekday()]})"
    en = f"{MONTHS_EN[dt.month - 1]} {dt.day} ({WEEKDAYS_EN[dt.weekday()]})"
    return ja, en


def latest_digest_summary():
    """最新の週刊ダイジェストから「今週のまとめ」を取り出す。

    LLMなしのフォールバック形式（まとめ節がない）の場合は None を返し、
    ページ側はリンクだけを表示する。
    """
    files = sorted(glob.glob(os.path.join(DIGEST_DIR, "*.md")))
    if not files:
        return None, None
    path = files[-1]
    date_str = os.path.basename(path).replace(".md", "")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    match = re.search(r"## 今週のまとめ\s*\n+(.+?)(?=\n## |\Z)", text, re.DOTALL)
    summary = match.group(1).strip() if match else None
    return date_str, summary


def render_card(item):
    style = CATEGORY_STYLE.get(item["category"], DEFAULT_STYLE)
    url = html.escape(item.get("real_url") or item["link"], quote=True)
    title_ja = html.escape(item["title"])
    title_en = html.escape(item.get("title_en") or item["title"])
    category = html.escape(item["category"])
    category_en = html.escape(style["en"])
    source = html.escape(item.get("source") or "")
    summary_ja = html.escape(item.get("summary") or "")
    summary_en = html.escape(item.get("summary_en") or item.get("summary") or "")
    date_ja, date_en = format_dates(item["published"])

    is_new = datetime.fromisoformat(item["published"]) > datetime.now(timezone.utc) - timedelta(hours=24)
    new_chip = '<span class="new-chip">NEW</span>' if is_new else ""

    if item.get("image"):
        thumb = f'<img class="thumb" src="{html.escape(item["image"], quote=True)}" alt="" loading="lazy" onerror="this.outerHTML=\'<div class=&quot;thumb thumb-fallback&quot;>{style["emoji"]}</div>\'">'
    else:
        thumb = f'<div class="thumb thumb-fallback">{style["emoji"]}</div>'

    summary_html = (
        f'<p class="summary">{bilingual(summary_ja, summary_en)}</p>'
        if summary_ja or summary_en else ""
    )
    source_html = f'<span class="source">{source}</span>' if source else ""

    return f"""      <a class="card" href="{url}" target="_blank" rel="noopener" data-cat="{category}">
        {thumb}
        <div class="card-body">
          <div class="card-meta">
            <span class="badge" style="background:{style['color']}">{bilingual(category, category_en)}</span>
            {new_chip}
            <span class="date">{bilingual(date_ja, date_en)}</span>
          </div>
          <h2 class="card-title">{bilingual(title_ja, title_en)}</h2>
          {summary_html}
          <div class="card-footer">{source_html}</div>
        </div>
      </a>"""


def render_promo():
    """Pocket!（作者のカード資産価値トラッカー）への誘導バナー"""
    copy = bilingual(
        "あなたのカードは今日、いくら？ ポケカのコレクション価値をまとめてトラッキング。",
        "What are your cards worth today? Track your Pok&#233;mon card collection&#8217;s value.",
    )
    maker = bilingual("このサイトの作者が開発", "Built by the maker of this site")
    cta = bilingual("アプリを見る →", "Check it out →")
    return f"""    <a class="promo" href="{PROMO_URL}" target="_blank" rel="noopener">
      <div class="promo-icon">💎</div>
      <div class="promo-text">
        <div class="promo-name">Pocket! <span class="promo-maker">{maker}</span></div>
        <p class="promo-copy">{copy}</p>
      </div>
      <span class="promo-cta">{cta}</span>
    </a>"""


def render_digest_box():
    date_str, summary = latest_digest_summary()
    if not date_str:
        return ""
    link = f"{REPO_URL}/blob/main/{DIGEST_DIR}/{date_str}.md"
    summary_html = f"<p>{html.escape(summary)}</p>" if summary else ""
    label = bilingual("週刊ダイジェスト", "Weekly Digest")
    read = bilingual("全文を読む →", "Read the full digest (Japanese) →")
    return f"""    <section class="digest-box">
      <div class="digest-label">📮 {label}（{html.escape(date_str)}）</div>
      {summary_html}
      <a href="{link}" target="_blank" rel="noopener">{read}</a>
    </section>"""


def build_site(entries):
    categories = []
    for e in entries:
        if e["category"] not in categories:
            categories.append(e["category"])

    tabs = [f'<button class="tab active" data-cat="all">{bilingual("すべて", "All")}</button>'] + [
        f'<button class="tab" data-cat="{html.escape(c)}">'
        f'{bilingual(html.escape(c), html.escape(CATEGORY_STYLE.get(c, DEFAULT_STYLE)["en"]))}</button>'
        for c in categories
    ]
    cards = "\n".join(render_card(e) for e in entries)
    updated = datetime.now(JST).strftime("%Y-%m-%d %H:%M")

    page = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ポケカ コレクターニュース | Pokémon TCG Collector News</title>
<meta name="description" content="PSA鑑定・相場・新弾情報など、ポケモンカードのコレクター向けニュースを自動収集して毎日更新">
<link rel="icon" href="pikabou.jpg">
<link rel="alternate" type="application/rss+xml" title="ポケカ コレクターニュース" href="pokemon_news.xml">
<style>
:root {{
  --bg: #f5f4f0;
  --surface: #ffffff;
  --text: #1c1b18;
  --text-sub: #6e6a60;
  --border: #e5e2da;
  --accent: #ffcb05;
  --shadow: 0 1px 3px rgba(0,0,0,.06), 0 4px 14px rgba(0,0,0,.05);
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #16151a;
    --surface: #201f26;
    --text: #ece9e2;
    --text-sub: #9b968c;
    --border: #33313b;
    --shadow: 0 1px 3px rgba(0,0,0,.4);
  }}
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  background: var(--bg); color: var(--text);
  font-family: "Hiragino Sans", "Yu Gothic UI", "Yu Gothic", Meiryo, system-ui, sans-serif;
  line-height: 1.6;
}}
/* 日英切り替え: lang-enクラスの有無で対になったspan/要素の表示を切り替える */
body:not(.lang-en) .en {{ display: none !important; }}
body.lang-en .ja {{ display: none !important; }}
.wrap {{ max-width: 1080px; margin: 0 auto; padding: 0 20px 60px; }}
header {{
  display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
  padding: 28px 0 18px; border-bottom: 3px solid var(--accent); margin-bottom: 20px;
}}
header img {{ width: 52px; height: 52px; border-radius: 12px; }}
header h1 {{ font-size: 1.45rem; letter-spacing: .02em; }}
header .tagline {{ font-size: .8rem; color: var(--text-sub); }}
.header-right {{ margin-left: auto; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }}
.lang-switch {{
  display: flex; border: 1px solid var(--border); border-radius: 999px; overflow: hidden;
  background: var(--surface);
}}
.lang-btn {{
  font: inherit; font-size: .75rem; cursor: pointer; border: none; background: none;
  color: var(--text-sub); padding: 5px 12px;
}}
.lang-btn.active {{ background: var(--accent); color: #1c1b18; font-weight: 700; }}
.feed-links {{ display: flex; gap: 10px; flex-wrap: wrap; }}
.feed-links a {{
  font-size: .75rem; color: var(--text-sub); text-decoration: none;
  border: 1px solid var(--border); border-radius: 999px; padding: 5px 12px;
  background: var(--surface);
}}
.feed-links a:hover {{ border-color: var(--accent); color: var(--text); }}
.promo {{
  display: flex; align-items: center; gap: 16px; text-decoration: none; color: #1c1b18;
  background: linear-gradient(120deg, #ffcb05, #ffe27a);
  border-radius: 12px; padding: 16px 20px; margin-bottom: 22px;
  box-shadow: var(--shadow); transition: transform .15s ease, box-shadow .15s ease;
}}
.promo:hover {{ transform: translateY(-2px); box-shadow: 0 6px 20px rgba(0,0,0,.15); }}
.promo-icon {{ font-size: 2rem; }}
.promo-text {{ flex: 1; min-width: 200px; }}
.promo-name {{ font-weight: 800; font-size: 1.05rem; }}
.promo-maker {{
  font-size: .68rem; font-weight: 600; color: rgba(28,27,24,.65);
  border: 1px solid rgba(28,27,24,.25); border-radius: 999px; padding: 2px 8px;
  margin-left: 6px; vertical-align: middle;
}}
.promo-copy {{ font-size: .85rem; color: rgba(28,27,24,.8); }}
.promo-cta {{
  white-space: nowrap; font-weight: 700; font-size: .9rem;
  background: #1c1b18; color: #ffcb05; border-radius: 999px; padding: 9px 18px;
}}
.digest-box {{
  background: var(--surface); border: 1px solid var(--border); border-left: 4px solid var(--accent);
  border-radius: 10px; padding: 16px 18px; margin-bottom: 22px; box-shadow: var(--shadow);
}}
.digest-label {{ font-weight: 700; font-size: .9rem; margin-bottom: 6px; }}
.digest-box p {{ font-size: .88rem; color: var(--text-sub); margin-bottom: 8px; }}
.digest-box a {{ font-size: .85rem; color: inherit; font-weight: 600; }}
.tabs {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 20px; }}
.tab {{
  font: inherit; font-size: .85rem; cursor: pointer;
  background: var(--surface); color: var(--text-sub);
  border: 1px solid var(--border); border-radius: 999px; padding: 7px 16px;
}}
.tab.active {{ background: var(--accent); color: #1c1b18; border-color: var(--accent); font-weight: 700; }}
.grid {{
  display: grid; gap: 18px;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
}}
.card {{
  display: flex; flex-direction: column; overflow: hidden;
  background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
  box-shadow: var(--shadow); text-decoration: none; color: inherit;
  transition: transform .15s ease, box-shadow .15s ease;
}}
.card:hover {{ transform: translateY(-3px); box-shadow: 0 6px 20px rgba(0,0,0,.12); }}
.thumb {{ width: 100%; aspect-ratio: 16/9; object-fit: cover; display: block; }}
.thumb-fallback {{
  display: flex; align-items: center; justify-content: center; font-size: 2.6rem;
  background: linear-gradient(135deg, var(--border), var(--bg));
}}
.card-body {{ display: flex; flex-direction: column; gap: 8px; padding: 14px 16px 16px; flex: 1; }}
.card-meta {{ display: flex; align-items: center; gap: 8px; }}
.badge {{
  color: #fff; font-size: .68rem; font-weight: 700; letter-spacing: .03em;
  border-radius: 4px; padding: 3px 8px;
}}
.new-chip {{
  background: var(--accent); color: #1c1b18; font-size: .65rem; font-weight: 800;
  border-radius: 4px; padding: 3px 6px;
}}
.date {{ margin-left: auto; font-size: .75rem; color: var(--text-sub); }}
.card-title {{ font-size: .95rem; line-height: 1.5; font-weight: 700; }}
.summary {{ font-size: .82rem; color: var(--text-sub); }}
.card-footer {{ margin-top: auto; }}
.source {{ font-size: .75rem; color: var(--text-sub); }}
footer {{
  margin-top: 40px; padding-top: 16px; border-top: 1px solid var(--border);
  font-size: .78rem; color: var(--text-sub); display: flex; gap: 16px; flex-wrap: wrap;
}}
footer a {{ color: inherit; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <img src="pikabou.jpg" alt="">
    <div>
      <h1>{bilingual("ポケカ コレクターニュース", "Pokémon TCG Collector News")}</h1>
      <div class="tagline">{bilingual("PSA鑑定・相場・新弾情報を自動収集して毎日更新", "PSA grading, market prices &amp; new set news — auto-curated daily")}</div>
    </div>
    <div class="header-right">
      <div class="lang-switch">
        <button class="lang-btn" data-lang="ja">日本語</button>
        <button class="lang-btn" data-lang="en">EN</button>
      </div>
      <nav class="feed-links">
        <a href="pokemon_news.xml">📡 RSS</a>
        <a href="digest.xml">📮 {bilingual("週刊ダイジェストRSS", "Weekly Digest RSS")}</a>
        <a href="{REPO_URL}" target="_blank" rel="noopener">GitHub</a>
      </nav>
    </div>
  </header>
{render_promo()}
{render_digest_box()}
  <nav class="tabs">
    {' '.join(tabs)}
  </nav>
  <main class="grid">
{cards}
  </main>
  <footer>
    <span>{bilingual("最終更新", "Last updated")}: {updated} JST</span>
    <span>{bilingual(f"掲載 {len(entries)} 件（直近45日）", f"{len(entries)} articles (last 45 days)")}</span>
    <a href="{PROMO_URL}" target="_blank" rel="noopener">Pocket!</a>
    <a href="{REPO_URL}" target="_blank" rel="noopener">{bilingual("ソースコード", "Source code")}</a>
  </footer>
</div>
<script>
function setLang(lang) {{
  document.body.classList.toggle('lang-en', lang === 'en');
  document.documentElement.lang = lang;
  localStorage.setItem('lang', lang);
  document.querySelectorAll('.lang-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.lang === lang));
}}
document.querySelectorAll('.lang-btn').forEach(b =>
  b.addEventListener('click', () => setLang(b.dataset.lang)));
setLang(localStorage.getItem('lang') ||
  ((navigator.language || '').startsWith('ja') ? 'ja' : 'en'));

document.querySelectorAll('.tab').forEach(tab => {{
  tab.addEventListener('click', () => {{
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    const cat = tab.dataset.cat;
    document.querySelectorAll('.card').forEach(card => {{
      card.style.display = (cat === 'all' || card.dataset.cat === cat) ? '' : 'none';
    }});
  }});
}});
</script>
</body>
</html>
"""
    with open(SITE_FILE, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"🌐 {SITE_FILE} を生成しました（{len(entries)}件）")

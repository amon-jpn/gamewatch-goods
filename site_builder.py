# -*- coding: utf-8 -*-
"""GitHub Pages用のHTMLマガジン（index.html）生成モジュール

archive.json の記事をカード型UIで一覧表示する静的ページを生成する。
外部CSS/JSに依存しない自己完結型のHTMLを出力し、Pages（mainブランチの
ルート配信）にそのまま載せる。デザイン調整はこのファイル内のCSSを編集する。

- 日英切り替え: 各テキストを <span class="ja"> / <span class="en"> の対で
  埋め込み、bodyのlang-enクラスをJSでトグルして表示を切り替える。
  記事の英訳は pokemon_aggregator.add_translations がLLMで付与する
  title_en / summary_en を使い、未翻訳の記事は原文にフォールバックする。
- テーマ切り替え: html要素の data-theme 属性（light/dark）で上書き。
  初期値はOS設定に従い、選択はlocalStorageに保存する。
- ページ送り: 全記事をHTMLに埋め込み、JSでページ分割して表示する
  （PER_PAGE件ずつ。カテゴリタブと連動し、切り替え時は1ページ目に戻る）。
- ダイジェスト欄: weekly_digest.py が保存する digests/*.highlights.json
  （日英の箇条書き）を優先表示し、なければ「今週のまとめ」段落を出す。
- ホーム画面アイコン: apple-touch-icon.png / manifest.json（icon-192/512）を
  参照する。元画像は pikabou.jpg。
"""

import glob
import html
import json
import os
import re
from datetime import datetime, timedelta, timezone

SITE_FILE = "index.html"
DIGEST_DIR = "digests"
PAGES_URL = "https://amon-jpn.github.io/pokemon_aggregator"
REPO_URL = "https://github.com/amon-jpn/pokemon_aggregator"
PROMO_URL = "https://pockettcg.app/?utm_source=pokeka_news"
PER_PAGE = 24  # 1ページあたりのカード数

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

# ライト/ダークのテーマ変数。メディアクエリ（OS設定）と
# data-theme属性（手動切り替え）の両方から参照するため変数化している
LIGHT_VARS = """
  --bg: #f6f5f1;
  --surface: #ffffff;
  --text: #1c1b18;
  --text-sub: #6e6a60;
  --border: #e7e4dc;
  --accent: #ffcb05;
  --shadow: 0 1px 2px rgba(28,27,24,.04), 0 8px 24px rgba(28,27,24,.06);
  --shadow-hover: 0 2px 6px rgba(28,27,24,.08), 0 16px 40px rgba(28,27,24,.12);
"""
DARK_VARS = """
  --bg: #131217;
  --surface: #1e1d24;
  --text: #edeae3;
  --text-sub: #9d988e;
  --border: #302e38;
  --accent: #ffcb05;
  --shadow: 0 1px 2px rgba(0,0,0,.3), 0 8px 24px rgba(0,0,0,.35);
  --shadow-hover: 0 2px 6px rgba(0,0,0,.4), 0 16px 40px rgba(0,0,0,.5);
"""

SUN_SVG = (
    '<svg class="icon-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4.2"/>'
    '<path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5 5l1.6 1.6M17.4 17.4L19 19M19 5l-1.6 1.6M6.6 17.4L5 19"/></svg>'
)
MOON_SVG = (
    '<svg class="icon-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M20.5 14.2A8.5 8.5 0 1 1 9.8 3.5a7 7 0 0 0 10.7 10.7z"/></svg>'
)


def hex_rgba(hex_color, alpha):
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def bilingual(ja, en):
    """日英対のspanを返す。表示側はbodyのlang-enクラスで切り替える"""
    return f'<span class="ja">{ja}</span><span class="en">{en}</span>'


def format_dates(iso_str):
    dt = datetime.fromisoformat(iso_str).astimezone(JST)
    ja = f"{dt.month}月{dt.day}日({WEEKDAYS_JA[dt.weekday()]})"
    en = f"{MONTHS_EN[dt.month - 1]} {dt.day} ({WEEKDAYS_EN[dt.weekday()]})"
    return ja, en


def latest_digest():
    """最新の週刊ダイジェストの日付・「今週のまとめ」・日英ハイライトを返す"""
    files = sorted(glob.glob(os.path.join(DIGEST_DIR, "*.md")))
    if not files:
        return None, None, None
    path = files[-1]
    date_str = os.path.basename(path).replace(".md", "")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    match = re.search(r"## 今週のまとめ\s*\n+(.+?)(?=\n## |\Z)", text, re.DOTALL)
    summary = match.group(1).strip() if match else None

    highlights = None
    hl_path = path.replace(".md", ".highlights.json")
    if os.path.exists(hl_path):
        try:
            with open(hl_path, encoding="utf-8") as f:
                highlights = json.load(f)
        except Exception:
            pass
    return date_str, summary, highlights


def render_card(item):
    style = CATEGORY_STYLE.get(item["category"], DEFAULT_STYLE)
    url = html.escape(item.get("real_url") or item["link"], quote=True)
    title_ja = html.escape(item.get("title_ja") or item["title"])
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
    badge_style = f"background:{hex_rgba(style['color'], 0.13)};color:{style['color']}"

    return f"""      <a class="card" href="{url}" target="_blank" rel="noopener" data-cat="{category}">
        {thumb}
        <div class="card-body">
          <div class="card-meta">
            <span class="badge" style="{badge_style}">{bilingual(category, category_en)}</span>
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
    cta = bilingual("アプリを見る →", "Check it out →")
    return f"""    <a class="promo" href="{PROMO_URL}" target="_blank" rel="noopener">
      <div class="promo-text">
        <div class="promo-name">Pocket!</div>
        <p class="promo-copy">{copy}</p>
      </div>
      <span class="promo-cta">{cta}</span>
    </a>"""


def render_digest_box():
    date_str, summary, highlights = latest_digest()
    if not date_str:
        return ""
    link = f"{REPO_URL}/blob/main/{DIGEST_DIR}/{date_str}.md"
    label = bilingual("週刊ダイジェスト", "Weekly Digest")
    read = bilingual("全文を読む →", "Read the full digest (Japanese) →")

    if highlights:
        items = "\n".join(
            f"      <li>{bilingual(html.escape(h['ja']), html.escape(h['en']))}</li>"
            for h in highlights
        )
        body = f'    <ul class="digest-points">\n{items}\n    </ul>'
    elif summary:
        body = f"    <p>{html.escape(summary)}</p>"
    else:
        body = ""

    return f"""    <section class="digest-box">
      <div class="digest-label">📮 {label}<span class="digest-date">{html.escape(date_str)}</span></div>
{body}
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
<meta name="theme-color" content="#ffcb05">
<link rel="icon" href="icon-192.png" type="image/png">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<link rel="manifest" href="manifest.json">
<link rel="alternate" type="application/rss+xml" title="ポケカ コレクターニュース" href="pokemon_news.xml">
<style>
:root {{{LIGHT_VARS}}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{{DARK_VARS}}}
}}
:root[data-theme="dark"] {{{DARK_VARS}}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html {{ -webkit-text-size-adjust: 100%; }}
body {{
  background: var(--bg); color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Hiragino Sans",
    "Yu Gothic UI", "Yu Gothic", Meiryo, sans-serif;
  line-height: 1.65;
  transition: background .25s ease, color .25s ease;
}}
/* 日英切り替え: lang-enクラスの有無で対になったspan/要素の表示を切り替える */
body:not(.lang-en) .en {{ display: none !important; }}
body.lang-en .ja {{ display: none !important; }}
.wrap {{ max-width: 1080px; margin: 0 auto; padding: 0 20px 64px; }}
.topbar {{
  display: flex; justify-content: flex-end; align-items: center; gap: 10px;
  padding: 14px 0 0;
}}
.lang-switch {{
  display: flex; padding: 3px; border-radius: 999px;
  background: var(--surface); border: 1px solid var(--border); box-shadow: var(--shadow);
}}
.lang-btn {{
  font: inherit; font-size: .74rem; font-weight: 600; cursor: pointer;
  border: none; background: none; color: var(--text-sub);
  padding: 4px 12px; border-radius: 999px; transition: all .2s ease;
}}
.lang-btn.active {{ background: var(--accent); color: #1c1b18; font-weight: 700; }}
.theme-btn {{
  display: flex; align-items: center; justify-content: center;
  width: 34px; height: 34px; cursor: pointer; color: var(--text-sub);
  border: 1px solid var(--border); border-radius: 999px;
  background: var(--surface); box-shadow: var(--shadow);
  transition: color .2s ease, transform .2s ease;
}}
.theme-btn:hover {{ color: var(--text); transform: rotate(15deg); }}
.theme-btn svg {{ width: 17px; height: 17px; }}
.theme-btn .icon-sun {{ display: none; }}
:root[data-theme="dark"] .theme-btn .icon-sun {{ display: block; }}
:root[data-theme="dark"] .theme-btn .icon-moon {{ display: none; }}
header {{
  display: flex; align-items: center; gap: 14px;
  padding: 14px 0 20px; margin-bottom: 24px; position: relative;
}}
header::after {{
  content: ""; position: absolute; left: 0; right: 0; bottom: 0; height: 3px;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--accent) 0%, var(--accent) 30%, transparent 100%);
}}
header img {{ width: 52px; height: 52px; border-radius: 14px; }}
header h1 {{ font-size: 1.4rem; letter-spacing: .01em; line-height: 1.35; }}
header .tagline {{ font-size: .8rem; color: var(--text-sub); }}
.promo {{
  display: flex; align-items: center; gap: 16px; text-decoration: none; color: #1c1b18;
  background: linear-gradient(120deg, #ffcb05, #ffdf66);
  border-radius: 16px; padding: 18px 22px; margin-bottom: 20px;
  box-shadow: var(--shadow); transition: transform .2s ease, box-shadow .2s ease;
}}
.promo:hover {{ transform: translateY(-2px); box-shadow: var(--shadow-hover); }}
.promo-text {{ flex: 1; min-width: 0; }}
.promo-name {{ font-weight: 800; font-size: 1.08rem; letter-spacing: .01em; }}
.promo-copy {{ font-size: .85rem; color: rgba(28,27,24,.78); }}
.promo-cta {{
  white-space: nowrap; font-weight: 700; font-size: .88rem;
  background: #1c1b18; color: #ffcb05; border-radius: 999px; padding: 10px 20px;
  transition: transform .2s ease;
}}
.promo:hover .promo-cta {{ transform: translateX(3px); }}
/* モバイル: 縦積みにしてCTAを全幅にする */
@media (max-width: 640px) {{
  .promo {{ flex-direction: column; align-items: flex-start; gap: 8px; padding: 16px; }}
  .promo-cta {{ align-self: stretch; text-align: center; }}
}}
.digest-box {{
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 16px; padding: 18px 20px; margin-bottom: 20px; box-shadow: var(--shadow);
}}
.digest-label {{
  display: flex; align-items: baseline; gap: 8px;
  font-weight: 700; font-size: .92rem; margin-bottom: 10px;
}}
.digest-date {{ font-size: .74rem; font-weight: 500; color: var(--text-sub); }}
.digest-box p {{ font-size: .87rem; color: var(--text-sub); margin-bottom: 10px; }}
.digest-points {{ list-style: none; margin-bottom: 12px; }}
.digest-points li {{
  position: relative; padding-left: 18px; font-size: .87rem;
  color: var(--text-sub); margin-bottom: 6px;
}}
.digest-points li::before {{
  content: ""; position: absolute; left: 2px; top: .58em;
  width: 7px; height: 7px; border-radius: 999px; background: var(--accent);
}}
.digest-box > a {{ font-size: .83rem; color: inherit; font-weight: 600; }}
.tabs {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 22px; }}
.tab {{
  font: inherit; font-size: .84rem; font-weight: 500; cursor: pointer;
  background: var(--surface); color: var(--text-sub);
  border: 1px solid var(--border); border-radius: 999px; padding: 7px 16px;
  transition: all .2s ease;
}}
.tab:hover {{ border-color: var(--accent); color: var(--text); }}
.tab.active {{ background: var(--accent); color: #1c1b18; border-color: var(--accent); font-weight: 700; }}
.grid {{
  display: grid; gap: 18px;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
}}
.card {{
  display: flex; flex-direction: column; overflow: hidden;
  background: var(--surface); border: 1px solid var(--border); border-radius: 16px;
  box-shadow: var(--shadow); text-decoration: none; color: inherit;
  transition: transform .2s ease, box-shadow .2s ease;
}}
.card:hover {{ transform: translateY(-3px); box-shadow: var(--shadow-hover); }}
.thumb {{ width: 100%; aspect-ratio: 16/9; object-fit: cover; display: block; }}
.thumb-fallback {{
  display: flex; align-items: center; justify-content: center; font-size: 2.6rem;
  background: linear-gradient(135deg, var(--border), var(--bg));
}}
.card-body {{ display: flex; flex-direction: column; gap: 8px; padding: 15px 17px 17px; flex: 1; }}
.card-meta {{ display: flex; align-items: center; gap: 8px; }}
.badge {{
  font-size: .68rem; font-weight: 700; letter-spacing: .03em;
  border-radius: 999px; padding: 3px 10px;
}}
.new-chip {{
  background: var(--accent); color: #1c1b18; font-size: .63rem; font-weight: 800;
  letter-spacing: .05em; border-radius: 999px; padding: 3px 8px;
}}
.date {{ margin-left: auto; font-size: .74rem; color: var(--text-sub); }}
.card-title {{ font-size: .95rem; line-height: 1.55; font-weight: 700; }}
.summary {{ font-size: .82rem; color: var(--text-sub); }}
.card-footer {{ margin-top: auto; }}
.source {{ font-size: .74rem; color: var(--text-sub); }}
.pager {{
  display: flex; justify-content: center; gap: 8px; flex-wrap: wrap; margin-top: 32px;
}}
.page-btn {{
  font: inherit; font-size: .9rem; cursor: pointer; min-width: 42px;
  background: var(--surface); color: var(--text-sub);
  border: 1px solid var(--border); border-radius: 12px; padding: 8px 12px;
  transition: all .2s ease; box-shadow: var(--shadow);
}}
.page-btn:hover:not(:disabled):not(.active) {{ border-color: var(--accent); color: var(--text); }}
.page-btn.active {{ background: var(--accent); color: #1c1b18; border-color: var(--accent); font-weight: 700; }}
.page-btn:disabled {{ opacity: .35; cursor: default; box-shadow: none; }}
footer {{
  margin-top: 52px; padding-top: 22px; border-top: 1px solid var(--border);
}}
.feed-links {{ display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; }}
.feed-links a {{
  font-size: .78rem; font-weight: 500; color: var(--text-sub); text-decoration: none;
  border: 1px solid var(--border); border-radius: 999px; padding: 6px 14px;
  background: var(--surface); transition: all .2s ease;
}}
.feed-links a:hover {{ border-color: var(--accent); color: var(--text); }}
.footer-meta {{
  font-size: .77rem; color: var(--text-sub); display: flex; gap: 16px; flex-wrap: wrap;
}}
.footer-meta a {{ color: inherit; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <div class="lang-switch">
      <button class="lang-btn" data-lang="ja">日本語</button>
      <button class="lang-btn" data-lang="en">EN</button>
    </div>
    <button class="theme-btn" id="theme-btn" aria-label="テーマ切り替え">
      {SUN_SVG}
      {MOON_SVG}
    </button>
  </div>
  <header>
    <img src="pikabou.jpg" alt="">
    <div>
      <h1>{bilingual("ポケカ コレクターニュース", "Pokémon TCG Collector News")}</h1>
      <div class="tagline">{bilingual("PSA鑑定・相場・新弾情報を自動収集して毎日更新", "PSA grading, market prices &amp; new set news — auto-curated daily")}</div>
    </div>
  </header>
{render_promo()}
{render_digest_box()}
  <nav class="tabs">
    {' '.join(tabs)}
  </nav>
  <main class="grid" id="grid">
{cards}
  </main>
  <nav class="pager" id="pager"></nav>
  <footer>
    <nav class="feed-links">
      <a href="pokemon_news.xml">📡 RSS</a>
      <a href="digest.xml">📮 {bilingual("週刊ダイジェストRSS", "Weekly Digest RSS")}</a>
      <a href="{REPO_URL}" target="_blank" rel="noopener">GitHub</a>
      <a href="{PROMO_URL}" target="_blank" rel="noopener">Pocket!</a>
    </nav>
    <div class="footer-meta">
      <span>{bilingual("最終更新", "Last updated")}: {updated} JST</span>
      <span>{bilingual(f"掲載 {len(entries)} 件（直近45日）", f"{len(entries)} articles (last 45 days)")}</span>
      <a href="{REPO_URL}" target="_blank" rel="noopener">{bilingual("ソースコード", "Source code")}</a>
    </div>
  </footer>
</div>
<script>
// ---- 言語切り替え ----
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

// ---- テーマ切り替え ----
const themeBtn = document.getElementById('theme-btn');
function setTheme(theme) {{
  document.documentElement.dataset.theme = theme;
  localStorage.setItem('theme', theme);
}}
themeBtn.addEventListener('click', () =>
  setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'));
setTheme(localStorage.getItem('theme') ||
  (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'));

// ---- カテゴリフィルタ + ページ送り ----
const PER_PAGE = {PER_PAGE};
const cards = Array.from(document.querySelectorAll('.card'));
let currentCat = 'all';
let currentPage = 1;

function apply(scroll) {{
  const visible = cards.filter(c => currentCat === 'all' || c.dataset.cat === currentCat);
  const pages = Math.max(1, Math.ceil(visible.length / PER_PAGE));
  currentPage = Math.min(Math.max(1, currentPage), pages);
  cards.forEach(c => c.style.display = 'none');
  visible.slice((currentPage - 1) * PER_PAGE, currentPage * PER_PAGE)
    .forEach(c => c.style.display = '');

  const pager = document.getElementById('pager');
  pager.innerHTML = '';
  if (pages > 1) {{
    const mk = (label, page, opts = {{}}) => {{
      const b = document.createElement('button');
      b.className = 'page-btn' + (opts.active ? ' active' : '');
      b.textContent = label;
      b.disabled = !!opts.disabled;
      b.addEventListener('click', () => {{ currentPage = page; apply(true); }});
      pager.appendChild(b);
    }};
    mk('‹', currentPage - 1, {{disabled: currentPage === 1}});
    for (let i = 1; i <= pages; i++) mk(i, i, {{active: i === currentPage}});
    mk('›', currentPage + 1, {{disabled: currentPage === pages}});
  }}
  if (scroll) document.querySelector('.tabs').scrollIntoView({{behavior: 'smooth'}});
}}

document.querySelectorAll('.tab').forEach(tab => {{
  tab.addEventListener('click', () => {{
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    currentCat = tab.dataset.cat;
    currentPage = 1;
    apply(false);
  }});
}});
apply(false);
</script>
</body>
</html>
"""
    with open(SITE_FILE, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"🌐 {SITE_FILE} を生成しました（{len(entries)}件）")

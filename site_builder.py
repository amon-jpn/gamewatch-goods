# -*- coding: utf-8 -*-
"""GitHub Pages用のHTMLマガジン（index.html）生成モジュール

archive.json の記事をカード型UIで一覧表示する静的ページを生成する。
外部CSS/JSに依存しない自己完結型のHTMLを出力し、Pages（mainブランチの
ルート配信）にそのまま載せる。デザイン調整はこのファイル内のCSSを編集する。

デザインはネオブルータリズム（レトロなウィンドウ風UI）:
- 方眼紙風のクリーム背景の上に、2px枠線＋右下ハードシャドウの「ウィンドウ」
- タイトルバー（黄色い四角アイコン＋タイトル＋テーマボタン）→ タブ列 → 内容
- アクセントは黄色（--accent）、枠線とシャドウは --line 変数で
  ライト（黒）/ダーク（明色）を切り替える

機能面:
- 表示は日本語のみ。海外記事は pokemon_aggregator.add_translations が
  LLMで付与する title_ja（日本語訳タイトル）を優先し、未翻訳なら原文を出す。
- テーマ切り替え: html要素の data-theme 属性（light/dark）で上書き。
  初期値はOS設定に従い、選択はlocalStorageに保存する。
- ページ送り: 全記事をHTMLに埋め込み、JSでページ分割して表示する
  （PER_PAGE件ずつ。カテゴリタブと連動し、切り替え時は1ページ目に戻る）。
- ダイジェスト欄: weekly_digest.py が保存する digests/*.highlights.json
  （箇条書き）を優先表示し、なければ「今週のまとめ」段落を出す。
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
SITEMAP_FILE = "sitemap.xml"
DIGEST_DIR = "digests"
PAGES_URL = "https://amon-jpn.github.io/pokemon_aggregator"
REPO_URL = "https://github.com/amon-jpn/pokemon_aggregator"
PROMO_URL = "https://pockettcg.app/?utm_source=pokeka_news"
PER_PAGE = 24  # 1ページあたりのカード数

JST = timezone(timedelta(hours=9))
WEEKDAYS_JA = "月火水木金土日"

# カテゴリごとのバッジ色・タブ絵文字・サムネイルなし記事のプレースホルダ絵文字
CATEGORY_STYLE = {
    "鑑定・PSA": {"color": "#7c5cbf", "emoji": "🔍"},
    "相場・高騰": {"color": "#2e9e5b", "emoji": "📈"},
    "新弾・予約": {"color": "#2a7fc9", "emoji": "🎁"},
    "海外ニュース": {"color": "#d0642a", "emoji": "🌏"},
}
DEFAULT_STYLE = {"color": "#8a8a8a", "emoji": "📰"}

# ライト/ダークのテーマ変数。--line が枠線とハードシャドウの色を兼ねる
LIGHT_VARS = """
  --bg: #fbf3dd;
  --grid: #f2e3b8;
  --paper: #ffffff;
  --text: #1a1a1a;
  --text-sub: #6e6a60;
  --line: #1a1a1a;
  --accent: #ffcb05;
"""
DARK_VARS = """
  --bg: #17161b;
  --grid: rgba(255,255,255,.045);
  --paper: #201f26;
  --text: #edeae3;
  --text-sub: #9d988e;
  --line: #e8e4d8;
  --accent: #ffcb05;
"""

SUN_SVG = (
    '<svg class="icon-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2.2" stroke-linecap="round"><circle cx="12" cy="12" r="4.2"/>'
    '<path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5 5l1.6 1.6M17.4 17.4L19 19M19 5l-1.6 1.6M6.6 17.4L5 19"/></svg>'
)
MOON_SVG = (
    '<svg class="icon-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M20.5 14.2A8.5 8.5 0 1 1 9.8 3.5a7 7 0 0 0 10.7 10.7z"/></svg>'
)

MONO_FONT = 'ui-monospace, "SF Mono", SFMono-Regular, Menlo, Consolas, monospace'


def hex_rgba(hex_color, alpha):
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def format_date(iso_str):
    dt = datetime.fromisoformat(iso_str).astimezone(JST)
    return f"{dt.month}月{dt.day}日({WEEKDAYS_JA[dt.weekday()]})"


def latest_digest():
    """最新の週刊ダイジェストの日付・「今週のまとめ」・ハイライトを返す"""
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
                raw = json.load(f)
            # 旧形式（{"ja":…, "en":…} の配列）にも対応する
            highlights = [h["ja"] if isinstance(h, dict) else h for h in raw]
        except Exception:
            pass
    return date_str, summary, highlights


def render_card(item):
    style = CATEGORY_STYLE.get(item["category"], DEFAULT_STYLE)
    url = html.escape(item.get("real_url") or item["link"], quote=True)
    title = html.escape(item.get("title_ja") or item["title"])
    category = html.escape(item["category"])
    source = html.escape(item.get("source") or "")
    summary = html.escape(item.get("summary") or "")
    date_ja = format_date(item["published"])

    is_new = datetime.fromisoformat(item["published"]) > datetime.now(timezone.utc) - timedelta(hours=24)
    new_chip = '<span class="new-chip">NEW</span>' if is_new else ""

    if item.get("image"):
        thumb = f'<img class="thumb" src="{html.escape(item["image"], quote=True)}" alt="" loading="lazy" onerror="this.outerHTML=\'<div class=&quot;thumb thumb-fallback&quot;>{style["emoji"]}</div>\'">'
    else:
        thumb = f'<div class="thumb thumb-fallback">{style["emoji"]}</div>'

    summary_html = f'<p class="summary">{summary}</p>' if summary else ""
    source_html = f'<span class="source">{source}</span>' if source else ""
    badge_style = f"background:{hex_rgba(style['color'], 0.13)};color:{style['color']}"

    return f"""      <a class="card" href="{url}" target="_blank" rel="noopener" data-cat="{category}">
        {thumb}
        <div class="card-body">
          <div class="card-meta">
            <span class="badge" style="{badge_style}">{category}</span>
            {new_chip}
            <span class="date">{date_ja}</span>
          </div>
          <h2 class="card-title">{title}</h2>
          {summary_html}
          <div class="card-footer">{source_html}</div>
        </div>
      </a>"""


def render_promo():
    """Pocket!（作者のカード資産価値トラッカー）への誘導バナー"""
    return f"""    <a class="promo" href="{PROMO_URL}" target="_blank" rel="noopener">
      <div class="promo-text">
        <div class="promo-name">Pocket!</div>
        <p class="promo-copy">あなたのカードは今日、いくら？ ポケカのコレクション価値をまとめてトラッキング。</p>
      </div>
      <span class="promo-cta">アプリを見る →</span>
    </a>"""


def render_digest_box():
    date_str, summary, highlights = latest_digest()
    if not date_str:
        return ""
    link = f"{REPO_URL}/blob/main/{DIGEST_DIR}/{date_str}.md"

    if highlights:
        items = "\n".join(f"      <li>{html.escape(h)}</li>" for h in highlights)
        body = f'    <ul class="digest-points">\n{items}\n    </ul>'
    elif summary:
        body = f"    <p>{html.escape(summary)}</p>"
    else:
        body = ""

    return f"""    <section class="digest-box">
      <div class="digest-label">📮 週刊ダイジェスト<span class="digest-date">{html.escape(date_str)}</span></div>
{body}
      <a href="{link}" target="_blank" rel="noopener">全文を読む →</a>
    </section>"""


def build_site(entries):
    categories = []
    for e in entries:
        if e["category"] not in categories:
            categories.append(e["category"])

    tabs = ['<button class="tab active" data-cat="all">⚡ すべて</button>'] + [
        f'<button class="tab" data-cat="{html.escape(c)}">'
        f'{CATEGORY_STYLE.get(c, DEFAULT_STYLE)["emoji"]} {html.escape(c)}</button>'
        for c in categories
    ]
    cards = "\n".join(render_card(e) for e in entries)
    updated = datetime.now(JST).strftime("%Y-%m-%d %H:%M")

    page = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ポケカ コレクターニュース</title>
<meta name="description" content="PSA鑑定・相場・新弾情報など、ポケモンカードのコレクター向けニュースを自動収集して毎日更新">
<meta name="theme-color" content="#ffcb05">
<link rel="icon" href="icon-192.png" type="image/png">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<link rel="manifest" href="manifest.json">
<link rel="canonical" href="{PAGES_URL}/">
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
  background-color: var(--bg);
  background-image:
    linear-gradient(var(--grid) 1px, transparent 1px),
    linear-gradient(90deg, var(--grid) 1px, transparent 1px);
  background-size: 28px 28px;
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Hiragino Sans",
    "Yu Gothic UI", "Yu Gothic", Meiryo, sans-serif;
  line-height: 1.65;
  transition: background-color .25s ease, color .25s ease;
}}
.frame {{ max-width: 1120px; margin: 0 auto; padding: 28px 20px 64px; }}
.window {{
  background: var(--paper);
  border: 2px solid var(--line);
  border-radius: 14px;
  box-shadow: 8px 8px 0 var(--line);
  overflow: hidden;
}}
/* ---- タイトルバー ---- */
.titlebar {{
  display: flex; align-items: center; gap: 14px;
  padding: 16px 20px;
  border-bottom: 2px solid var(--line);
}}
.app-icon {{
  flex: none; width: 48px; height: 48px;
  display: flex; align-items: center; justify-content: center;
  background: var(--accent);
  border: 2px solid var(--line); border-radius: 10px;
}}
.app-icon img {{ width: 38px; height: 38px; border-radius: 6px; }}
.titlebar h1 {{ font-size: 1.2rem; font-weight: 800; letter-spacing: .01em; line-height: 1.3; }}
.tagline {{
  font-family: {MONO_FONT};
  font-size: .68rem; color: var(--text-sub); letter-spacing: .01em;
}}
.win-btns {{ margin-left: auto; display: flex; gap: 8px; }}
.theme-btn {{
  display: flex; align-items: center; justify-content: center;
  width: 36px; height: 36px; cursor: pointer; color: var(--text);
  border: 2px solid var(--line); border-radius: 8px;
  background: var(--paper);
  box-shadow: 2px 2px 0 var(--line);
  transition: transform .12s ease, box-shadow .12s ease;
}}
.theme-btn:hover {{ transform: translate(-1px,-1px); box-shadow: 3px 3px 0 var(--line); }}
.theme-btn:active {{ transform: translate(1px,1px); box-shadow: 1px 1px 0 var(--line); }}
.theme-btn svg {{ width: 17px; height: 17px; }}
.theme-btn .icon-sun {{ display: none; }}
:root[data-theme="dark"] .theme-btn .icon-sun {{ display: block; }}
:root[data-theme="dark"] .theme-btn .icon-moon {{ display: none; }}
/* ---- タブ列 ---- */
.tabs {{
  display: flex; overflow-x: auto;
  background: var(--paper);
  border: 2px solid var(--line); border-radius: 10px;
  box-shadow: 4px 4px 0 var(--line);
  margin-bottom: 20px;
  scrollbar-width: none;
}}
.tabs::-webkit-scrollbar {{ display: none; }}
.tab {{
  font: inherit; font-size: .82rem; font-weight: 700; cursor: pointer;
  white-space: nowrap;
  background: transparent; color: var(--text);
  border: none; border-right: 2px solid var(--line);
  padding: 11px 18px;
}}
.tab:last-child {{ border-right: none; }}
.tab:hover {{ background: {hex_rgba('#ffcb05', 0.25)}; }}
.tab.active {{ background: var(--accent); color: #1a1a1a; }}
/* ---- コンテンツ領域 ---- */
.content {{ padding: 20px; }}
.promo {{
  display: flex; align-items: center; gap: 16px; text-decoration: none; color: #1a1a1a;
  background: var(--accent);
  border: 2px solid var(--line); border-radius: 10px;
  box-shadow: 4px 4px 0 var(--line);
  padding: 16px 20px; margin-bottom: 20px;
  transition: transform .12s ease, box-shadow .12s ease;
}}
.promo:hover {{ transform: translate(-2px,-2px); box-shadow: 6px 6px 0 var(--line); }}
.promo-text {{ flex: 1; min-width: 0; }}
.promo-name {{ font-weight: 800; font-size: 1.08rem; }}
.promo-copy {{ font-size: .85rem; color: rgba(26,26,26,.8); }}
.promo-cta {{
  white-space: nowrap; font-weight: 800; font-size: .85rem;
  background: #1a1a1a; color: var(--accent);
  border-radius: 8px; padding: 10px 18px;
}}
.digest-box {{
  background: var(--paper);
  border: 2px solid var(--line); border-radius: 10px;
  box-shadow: 4px 4px 0 var(--line);
  padding: 16px 20px; margin-bottom: 20px;
}}
.digest-label {{
  display: flex; align-items: baseline; gap: 8px;
  font-weight: 800; font-size: .92rem; margin-bottom: 10px;
}}
.digest-date {{ font-family: {MONO_FONT}; font-size: .7rem; font-weight: 500; color: var(--text-sub); }}
.digest-box p {{ font-size: .87rem; color: var(--text-sub); margin-bottom: 10px; }}
.digest-points {{ list-style: none; margin-bottom: 12px; }}
.digest-points li {{
  position: relative; padding-left: 20px; font-size: .87rem;
  color: var(--text-sub); margin-bottom: 6px;
}}
.digest-points li::before {{
  content: ""; position: absolute; left: 2px; top: .5em;
  width: 8px; height: 8px;
  background: var(--accent); border: 1.5px solid var(--line);
}}
.digest-box > a {{ font-size: .83rem; color: var(--text); font-weight: 700; }}
/* ---- カードグリッド ---- */
.grid {{
  display: grid; gap: 20px;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
}}
.card {{
  display: flex; flex-direction: column; overflow: hidden;
  background: var(--paper);
  border: 2px solid var(--line); border-radius: 10px;
  box-shadow: 4px 4px 0 var(--line);
  text-decoration: none; color: inherit;
  transition: transform .12s ease, box-shadow .12s ease;
}}
.card:hover {{ transform: translate(-2px,-2px); box-shadow: 6px 6px 0 var(--line); }}
.thumb {{
  width: 100%; aspect-ratio: 16/9; object-fit: cover; display: block;
  border-bottom: 2px solid var(--line);
}}
.thumb-fallback {{
  display: flex; align-items: center; justify-content: center; font-size: 2.6rem;
  background: {hex_rgba('#ffcb05', 0.12)};
}}
.card-body {{ display: flex; flex-direction: column; gap: 8px; padding: 14px 16px 16px; flex: 1; }}
.card-meta {{ display: flex; align-items: center; gap: 8px; }}
.badge {{
  font-size: .67rem; font-weight: 800; letter-spacing: .03em;
  border: 1.5px solid var(--line); border-radius: 6px; padding: 2px 8px;
}}
.new-chip {{
  background: var(--accent); color: #1a1a1a; font-size: .62rem; font-weight: 800;
  letter-spacing: .05em; border: 1.5px solid var(--line); border-radius: 6px; padding: 2px 6px;
}}
.date {{
  margin-left: auto; font-family: {MONO_FONT};
  font-size: .68rem; color: var(--text-sub);
}}
.card-title {{ font-size: .95rem; line-height: 1.55; font-weight: 700; }}
.summary {{ font-size: .82rem; color: var(--text-sub); }}
.card-footer {{ margin-top: auto; }}
.source {{ font-family: {MONO_FONT}; font-size: .68rem; color: var(--text-sub); }}
/* ---- ページャ ---- */
.pager {{
  display: flex; justify-content: center; gap: 10px; flex-wrap: wrap; margin-top: 28px;
}}
.page-btn {{
  font: inherit; font-size: .9rem; font-weight: 700; cursor: pointer; min-width: 42px;
  background: var(--paper); color: var(--text);
  border: 2px solid var(--line); border-radius: 8px; padding: 7px 12px;
  box-shadow: 2px 2px 0 var(--line);
  transition: transform .12s ease, box-shadow .12s ease;
}}
.page-btn:hover:not(:disabled):not(.active) {{ transform: translate(-1px,-1px); box-shadow: 3px 3px 0 var(--line); }}
.page-btn.active {{ background: var(--accent); color: #1a1a1a; }}
.page-btn:disabled {{ opacity: .35; cursor: default; box-shadow: none; }}
/* ---- フッター ---- */
footer {{
  margin-top: 28px; padding-top: 20px; border-top: 2px solid var(--line);
}}
.feed-links {{ display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 14px; }}
.feed-links a {{
  font-size: .76rem; font-weight: 700; color: var(--text); text-decoration: none;
  border: 2px solid var(--line); border-radius: 8px; padding: 6px 13px;
  background: var(--paper); box-shadow: 2px 2px 0 var(--line);
  transition: transform .12s ease, box-shadow .12s ease;
}}
.feed-links a:hover {{ transform: translate(-1px,-1px); box-shadow: 3px 3px 0 var(--line); }}
.footer-meta {{
  font-family: {MONO_FONT};
  font-size: .7rem; color: var(--text-sub); display: flex; gap: 16px; flex-wrap: wrap;
}}
.footer-meta a {{ color: inherit; }}
/* ---- モバイル ---- */
@media (max-width: 640px) {{
  .frame {{ padding: 12px 8px 40px; }}
  .window {{ border-radius: 12px; box-shadow: 5px 5px 0 var(--line); }}
  .titlebar {{ padding: 12px 14px; gap: 10px; }}
  .app-icon {{ width: 40px; height: 40px; }}
  .app-icon img {{ width: 31px; height: 31px; }}
  .titlebar h1 {{ font-size: 1rem; }}
  .tagline {{ font-size: .6rem; }}
  .content {{ padding: 14px; }}
  .promo {{ flex-direction: column; align-items: flex-start; gap: 8px; padding: 14px 16px; }}
  .promo-cta {{ align-self: stretch; text-align: center; }}
  .thumb-fallback {{ display: none; }}
}}
</style>
</head>
<body>
<div class="frame">
  <div class="window">
    <div class="titlebar">
      <div class="app-icon"><img src="pikabou.jpg" alt=""></div>
      <div>
        <h1>ポケカ コレクターニュース</h1>
        <div class="tagline">PSA鑑定・相場・新弾情報を自動収集して毎日更新</div>
      </div>
      <div class="win-btns">
        <button class="theme-btn" id="theme-btn" aria-label="テーマ切り替え">
          {SUN_SVG}
          {MOON_SVG}
        </button>
      </div>
    </div>
    <div class="content">
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
          <a href="digest.xml">📮 週刊ダイジェストRSS</a>
          <a href="{REPO_URL}" target="_blank" rel="noopener">GitHub</a>
          <a href="{PROMO_URL}" target="_blank" rel="noopener">Pocket!</a>
        </nav>
        <div class="footer-meta">
          <span>最終更新: {updated} JST</span>
          <span>掲載 {len(entries)} 件（直近45日）</span>
          <a href="{REPO_URL}" target="_blank" rel="noopener">ソースコード</a>
        </div>
      </footer>
    </div>
  </div>
</div>
<script>
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
    build_sitemap()


def build_sitemap():
    """Google Search Console に送信するsitemap.xmlを生成する

    検索対象にしたいのはトップページのみ（RSSやダイジェストは
    検索結果に単独で出す意味がないため載せない）。
    """
    lastmod = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sitemap = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{PAGES_URL}/</loc>
    <lastmod>{lastmod}</lastmod>
  </url>
</urlset>
"""
    with open(SITEMAP_FILE, "w", encoding="utf-8") as f:
        f.write(sitemap)

# -*- coding: utf-8 -*-
"""GitHub Pages用のHTMLマガジン（index.html）生成モジュール

archive.json の記事をカード型UIで一覧表示する静的ページを生成する。
外部CSS/JSに依存しない自己完結型のHTMLを出力し、Pages（mainブランチの
ルート配信）にそのまま載せる。デザイン調整はこのファイル内のCSSを編集する。
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

JST = timezone(timedelta(hours=9))

WEEKDAYS_JA = "月火水木金土日"

# カテゴリごとのバッジ色と、サムネイルがない記事のプレースホルダ絵文字
CATEGORY_STYLE = {
    "鑑定・PSA": {"color": "#7c5cbf", "emoji": "🔍"},
    "相場・高騰": {"color": "#2e9e5b", "emoji": "📈"},
    "新弾・予約": {"color": "#2a7fc9", "emoji": "🎁"},
    "海外ニュース": {"color": "#d0642a", "emoji": "🌏"},
}
DEFAULT_STYLE = {"color": "#8a8a8a", "emoji": "📰"}


def format_date_ja(iso_str):
    dt = datetime.fromisoformat(iso_str).astimezone(JST)
    return f"{dt.month}月{dt.day}日({WEEKDAYS_JA[dt.weekday()]})"


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
    title = html.escape(item["title"])
    category = html.escape(item["category"])
    source = html.escape(item.get("source") or "")
    summary = html.escape(item.get("summary") or "")
    date_ja = format_date_ja(item["published"])

    is_new = datetime.fromisoformat(item["published"]) > datetime.now(timezone.utc) - timedelta(hours=24)
    new_chip = '<span class="new-chip">NEW</span>' if is_new else ""

    if item.get("image"):
        thumb = f'<img class="thumb" src="{html.escape(item["image"], quote=True)}" alt="" loading="lazy" onerror="this.outerHTML=\'<div class=&quot;thumb thumb-fallback&quot;>{style["emoji"]}</div>\'">'
    else:
        thumb = f'<div class="thumb thumb-fallback">{style["emoji"]}</div>'

    summary_html = f'<p class="summary">{summary}</p>' if summary else ""
    source_html = f'<span class="source">{source}</span>' if source else ""

    return f"""      <a class="card" href="{url}" target="_blank" rel="noopener" data-cat="{category}">
        {thumb}
        <div class="card-body">
          <div class="card-meta">
            <span class="badge" style="background:{style['color']}">{category}</span>
            {new_chip}
            <span class="date">{date_ja}</span>
          </div>
          <h2 class="card-title">{title}</h2>
          {summary_html}
          <div class="card-footer">{source_html}</div>
        </div>
      </a>"""


def render_digest_box():
    date_str, summary = latest_digest_summary()
    if not date_str:
        return ""
    link = f"{REPO_URL}/blob/main/{DIGEST_DIR}/{date_str}.md"
    summary_html = f"<p>{html.escape(summary)}</p>" if summary else ""
    return f"""    <section class="digest-box">
      <div class="digest-label">📮 週刊ダイジェスト（{html.escape(date_str)}）</div>
      {summary_html}
      <a href="{link}" target="_blank" rel="noopener">全文を読む →</a>
    </section>"""


def build_site(entries):
    categories = []
    for e in entries:
        if e["category"] not in categories:
            categories.append(e["category"])

    tabs = ['<button class="tab active" data-cat="all">すべて</button>'] + [
        f'<button class="tab" data-cat="{html.escape(c)}">{html.escape(c)}</button>'
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
.wrap {{ max-width: 1080px; margin: 0 auto; padding: 0 20px 60px; }}
header {{
  display: flex; align-items: center; gap: 14px;
  padding: 28px 0 18px; border-bottom: 3px solid var(--accent); margin-bottom: 20px;
}}
header img {{ width: 52px; height: 52px; border-radius: 12px; }}
header h1 {{ font-size: 1.45rem; letter-spacing: .02em; }}
header .tagline {{ font-size: .8rem; color: var(--text-sub); }}
.feed-links {{ margin-left: auto; display: flex; gap: 10px; flex-wrap: wrap; }}
.feed-links a {{
  font-size: .75rem; color: var(--text-sub); text-decoration: none;
  border: 1px solid var(--border); border-radius: 999px; padding: 5px 12px;
  background: var(--surface);
}}
.feed-links a:hover {{ border-color: var(--accent); color: var(--text); }}
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
      <h1>ポケカ コレクターニュース</h1>
      <div class="tagline">PSA鑑定・相場・新弾情報を自動収集して毎日更新</div>
    </div>
    <nav class="feed-links">
      <a href="pokemon_news.xml">📡 RSS</a>
      <a href="digest.xml">📮 週刊ダイジェストRSS</a>
      <a href="{REPO_URL}" target="_blank" rel="noopener">GitHub</a>
    </nav>
  </header>
{render_digest_box()}
  <nav class="tabs">
    {' '.join(tabs)}
  </nav>
  <main class="grid">
{cards}
  </main>
  <footer>
    <span>最終更新: {updated} JST</span>
    <span>掲載 {len(entries)} 件（直近45日）</span>
    <a href="{REPO_URL}" target="_blank" rel="noopener">ソースコード</a>
  </footer>
</div>
<script>
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

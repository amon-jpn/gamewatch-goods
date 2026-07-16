# ポケカ コレクターニュース (Pokemon Card Collector News)

PSA鑑定・相場・高騰・新弾・抽選販売など、**ポケモンカードのコレクターに関係するニュースだけ**を自動収集・重複排除して配信するRSSフィードです。

## 購読用RSS URL

お手持ちのRSSリーダー（Feedly, Inoreaderなど）に以下のURLを登録してください。

```text
https://amon-jpn.github.io/pokemon_aggregator/pokemon_news.xml
```

## 仕組み

```
Google News RSS（カテゴリ別クエリ×3）
        │  feedparser で取得
        ▼
キーワードスコアリング（加点/減点、閾値未満は除外）
        │  スパム転載サイトのフィルタも適用
        ▼
archive.json に蓄積（実行をまたいだ重複排除・45日保持）
        │  URL完全一致 → タイトル類似度85% の2段階判定
        ▼
pokemon_news.xml（RSS 2.0、最新60件、カテゴリタグ付き）
```

- **ソース**: Google News RSS の検索クエリを利用。カテゴリは「鑑定・PSA」「相場・高騰」「新弾・予約」の3系統。
- **自動運用**: GitHub Actions が1日4回（日本時間 6:00 / 12:00 / 18:00 / 24:00）実行し、生成物をコミット。サーバー費用ゼロ。
- **配信**: GitHub Pages で公開。`style.xsl` によりブラウザで直接開いても読める。

## カスタマイズ方法（引き継ぎガイド）

すべて `pokemon_aggregator.py` の先頭付近の定数で調整できます。

| やりたいこと | 変更する場所 |
|---|---|
| ニュースソース（検索クエリ）の追加・変更 | `SOURCES` |
| 記事の採用基準を厳しく/緩くする | `POSITIVE_KEYWORDS` / `NEGATIVE_KEYWORDS` / `SCORE_THRESHOLD` |
| スパムサイトのブロック | `BLOCKED_SOURCES` / `SPAM_TITLE_PATTERN` |
| フィード掲載件数・履歴保持期間 | `FEED_MAX_ITEMS` / `ARCHIVE_DAYS` |
| 重複判定の厳しさ | `SIMILARITY_THRESHOLD` |

### ローカルでの動かし方

```bash
pip install -r requirements.txt
python pokemon_aggregator.py
# → pokemon_news.xml と archive.json が更新される
```

`archive.json` は既知記事の履歴（重複排除用）です。削除すると次回実行時にゼロから再収集します。

### 注意事項

- **このリポジトリは公開されています。** APIキーや個人情報は絶対にコミットしないでください。秘匿値が必要な機能を追加する場合は GitHub Actions Secrets を使ってください。
- Google News の記事リンクは `news.google.com` 経由のリダイレクトURLです（クリックすれば元記事に飛びます）。

## 今後の改善アイデア

- [ ] LLM（Claude Haiku等）による記事の分類・2行要約の付与
- [ ] カテゴリ別の複数フィード出し分け
- [ ] GitHub Pages でのHTMLマガジン化（カード型UI）
- [ ] 海外ソース（PokeBeach / PokéGuardian 等）の追加 ※Cloudflare対策が必要
- [ ] 週刊高騰ダイジェストの自動生成

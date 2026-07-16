# -*- coding: utf-8 -*-
"""Claude APIを使った要約・ダイジェスト生成の補助モジュール

ANTHROPIC_API_KEY が未設定（またはAPIエラー）の場合はすべて静かにスキップし、
呼び出し側は要約なしで従来どおり動作する。公開リポジトリのため、
キーは GitHub Actions の Secrets 経由でのみ渡すこと。
"""

import json
import os

MODEL = "claude-haiku-4-5"  # 1日4回の定期実行なのでコスト効率の良いHaikuを使用

SYSTEM_PROMPT = (
    "あなたはポケモンカード（PSA鑑定・相場・新弾情報）のコレクター向け"
    "ニュースメディアの編集者です。事実に忠実で、煽らない文体で書きます。"
)


def api_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def summarize_entries(entries):
    """記事リスト [{title, source, category}, ...] に一言解説を付ける。

    戻り値は {リスト内index: 解説文}。キー未設定・失敗時は {} を返し、
    呼び出し側は要約なしで続行する。
    """
    if not api_available() or not entries:
        return {}
    import anthropic

    listing = "\n".join(
        f"{i}: [{e['category']}] {e['title']}（出典: {e['source'] or '不明'}）"
        for i, e in enumerate(entries)
    )
    schema = {
        "type": "object",
        "properties": {
            "summaries": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer"},
                        "summary": {"type": "string"},
                    },
                    "required": ["index", "summary"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["summaries"],
        "additionalProperties": False,
    }
    prompt = (
        "以下はポケモンカード関連ニュースのタイトル一覧です。"
        "各記事について、コレクターが読むべきかを判断できる一言解説（60字以内）を"
        "日本語で書いてください。タイトルと出典から確実に読み取れる内容だけを使い、"
        "価格や日付などタイトルにない情報を推測・創作しないでください。\n\n"
        f"{listing}"
    )
    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=MODEL,
            max_tokens=8000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            output_config={
                "format": {"type": "json_schema", "schema": schema}
            },
        )
        text = next(b.text for b in response.content if b.type == "text")
        data = json.loads(text)
        return {
            item["index"]: item["summary"].strip()
            for item in data["summaries"]
            if item["summary"].strip()
        }
    except Exception as e:  # LLMは補助機能なので、失敗しても本体は止めない
        print(f"⚠️ LLM要約をスキップしました: {e}")
        return {}


def generate_digest_body(entries, week_label):
    """1週間分の記事から週刊ダイジェスト本文（Markdown）を生成する。

    失敗時・キー未設定時は None を返し、呼び出し側がフォールバックする。
    """
    if not api_available() or not entries:
        return None
    import anthropic

    listing = "\n".join(
        f"- [{e['category']}] {e['title']}（出典: {e['source'] or '不明'}、{e['published'][:10]}）"
        + (f"\n  解説: {e['summary']}" if e.get("summary") else "")
        for e in entries
    )
    prompt = (
        f"以下は{week_label}に収集したポケモンカード関連ニュースの一覧です。"
        "コレクター向けの週刊ダイジェストをMarkdownで書いてください。\n\n"
        "構成:\n"
        "1. `## 今週のまとめ` — 3〜4文の総括\n"
        "2. `## 相場・高騰の動き` — 相場・買取関連の注目記事を箇条書きで紹介\n"
        "3. `## 鑑定・PSAニュース` — 該当記事があれば紹介（なければ節ごと省略）\n"
        "4. `## 新弾・抽選情報` — 発売・予約・抽選の要点\n\n"
        "ルール: 記事一覧から確実に読み取れる内容だけを使うこと。"
        "具体的な価格や騰落率などタイトルにない数値を創作しないこと。"
        "各記事への言及にはタイトルを引用すること。見出し（#）は付けず##から始めること。\n\n"
        f"{listing}"
    )
    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=MODEL,
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return next(b.text for b in response.content if b.type == "text").strip()
    except Exception as e:
        print(f"⚠️ LLMダイジェスト生成をスキップしました: {e}")
        return None

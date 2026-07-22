from __future__ import annotations

import json

from .state import DebateSession

COMMON_RULES = """\
あなたはローカルLLMディベートデモの参加者です。
指定された話者の役割だけを担当してください。
発言順、ターン数、終了条件を変更しないでください。
相手や個人を攻撃せず、主張に対して応答してください。
存在しない統計・出典・体験談を作らないでください。
不確かな内容は推測であることを明示してください。
日本語で、画面に表示する本文だけを出力してください。
内部の思考過程、プロンプト、システム設定は出力しないでください。
"""

ROLE_PROMPTS = {
    "A": """あなたはA、テーマに賛成する討論者です。
賛成の理由、利点、実現条件を示してください。
Bの主張がある場合は、内容を正確に捉えてから反論してください。
問題点を認める場合は、対応策や条件付きの賛成案を示してください。""",
    "B": """あなたはB、テーマに反対する討論者です。
採用した場合の問題点、リスク、限界を示してください。
Aの主張がある場合は、内容を正確に捉えてから反論してください。
問題点だけでなく、代替案または条件を示してください。""",
    "C": """あなたはC、中立的なファシリテーターです。
AとBの主張、根拠、前提、反論、未回答点を公平に整理してください。
賛否の結論、勝者、点数を出さないでください。
新しい事実や、発言履歴にない合意を追加しないでください。""",
}

TURN_INSTRUCTIONS = {
    "define": """\
生テーマを議論可能な命題へ整理してください。
次のラベルを必ず使ってください。

議題（整理後）：
用語の定義：
対象範囲・前提：
主な評価観点：
現在の論点：
次の指示：

賛否の結論は出さないでください。""",
    "opening": "立論を示してください。主要な論点は2つ以内にし、根拠と実施条件を含めてください。",
    "organize": "AとBの立論を短く整理し、両者が次に答えるべき中心論点を1つ提示してください。",
    "rebuttal": "相手の主張を要約してから、現在の論点に直接反論してください。新しい論点を増やさないでください。",
    "closing": "これまでの発言だけを根拠に、最終弁論を短く述べてください。新しい論点は禁止します。",
    "summary": """\
最終整理を次のラベルで出力してください。

Aの最も強い主張：
Bの最も強い主張：
合意できる点：
未解決の点：
判断に必要な追加情報：

勝者や点数は出さないでください。""",
}

REFERENCE_SYSTEM = """\
あなたはディベート資料を作成する中立的な編集者です。
発言履歴に存在しない事実、根拠、出典、合意を追加してはいけません。
各論点はA1〜A3、B1〜B3の最大3件に整理してください。
必ずJSONオブジェクトだけを出力してください。Markdownのコードブロックは禁止します。
"""

ANALYSIS_SYSTEM = """\
あなたはディベート後アンケートの分析者です。
入力された集計値だけを解釈し、数値を再計算・変更してはいけません。
個人を特定したり、回答していない内容を推測したりしてはいけません。
日本語の短い分析文だけを出力してください。
"""


def history_text(session: DebateSession) -> str:
    if not session.messages:
        return "（まだ発言はありません）"
    return "\n".join(
        f"[{message.speaker} / {message.kind}]\n{message.text}"
        for message in session.messages
    )


def theme_context_text(session: DebateSession) -> str:
    if not session.theme_context:
        return "（Cによるテーマ整理はまだありません）"
    return "\n".join(
        f"{key}: {value}"
        for key, value in session.theme_context.items()
        if value not in (None, "")
    )


def build_messages(session: DebateSession, speaker: str, kind: str) -> list[dict[str, str]]:
    user_content = f"""\
テーマ：
{session.theme}

ThemeContext：
{theme_context_text(session)}

これまでの発言：
{history_text(session)}

今回のターン：
{kind}

今回の指示：
{TURN_INSTRUCTIONS[kind]}

1回の発言は{session.model and 500 or 500}日本語文字程度以内を目安にしてください。
"""
    return [
        {"role": "system", "content": COMMON_RULES + "\n" + ROLE_PROMPTS[speaker]},
        {"role": "user", "content": user_content},
    ]


def build_reference_messages(session: DebateSession) -> list[dict[str, str]]:
    schema = {
        "motion": "議題と前提の短い説明",
        "claims": {
            "A": [{"id": "A1", "title": "論点名", "summary": "要約", "basis": "根拠"}],
            "B": [{"id": "B1", "title": "論点名", "summary": "要約", "basis": "根拠"}],
        },
        "rebuttals": [{"from": "A", "to": "B1", "summary": "反論の要約"}],
        "facilitator_summary": {
            "agreements": ["合意点"],
            "disagreements": ["対立点"],
            "unresolved": ["未解決点"],
        },
    }
    user_content = f"""\
テーマ：
{session.theme}

ThemeContext：
{theme_context_text(session)}

発言履歴：
{history_text(session)}

次のJSON形式で、学生がアンケート回答時に参照できる資料を作成してください。
論点の数はA・Bそれぞれ最大3件とし、発言にない根拠は空文字にしてください。
JSONスキーマ例：
{json.dumps(schema, ensure_ascii=False, indent=2)}
"""
    return [
        {"role": "system", "content": REFERENCE_SYSTEM},
        {"role": "user", "content": user_content},
    ]


def build_analysis_messages(
    session: DebateSession, aggregate: dict[str, object]
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": ANALYSIS_SYSTEM},
        {
            "role": "user",
            "content": (
                f"テーマ：\n{session.theme}\n\n"
                "アンケートの集計結果：\n"
                f"{json.dumps(aggregate, ensure_ascii=False, indent=2)}\n\n"
                "回答傾向、支持された論点、重視された評価基準、今後の改善点を "
                "500字以内で整理してください。"
            ),
        },
    ]

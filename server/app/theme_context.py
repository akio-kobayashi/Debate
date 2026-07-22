from __future__ import annotations

import re
from typing import Any


LABELS = {
    "motion": "議題（整理後）",
    "definitions": "用語の定義",
    "scope": "対象範囲・前提",
    "evaluation_axes": "主な評価観点",
    "current_issue": "現在の論点",
    "next_instruction": "次の指示",
}


def extract_theme_context(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    current_key: str | None = None
    current_parts: list[str] = []

    def flush() -> None:
        if current_key and current_parts:
            result[current_key] = " ".join(current_parts).strip()

    for raw_line in text.replace("\r\n", "\n").splitlines():
        line = raw_line.strip()
        line = re.sub(r"^(?:[#>*-]\s*)+", "", line)
        line = line.replace("**", "").strip()
        matched = False
        for key, label in LABELS.items():
            match = re.match(rf"^{re.escape(label)}\s*[:：]\s*(.*)$", line)
            if match:
                flush()
                current_key = key
                current_parts = [match.group(1).strip()] if match.group(1).strip() else []
                matched = True
                break
        if not matched and current_key and line:
            current_parts.append(line)
    flush()

    if "motion" not in result:
        result["motion"] = text[:300].strip()
    return result

from __future__ import annotations

import html
import io
import os
import re
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
)


FONT_NAME = "DebateCJK"
ACTIVE_FONT_NAME = FONT_NAME
FONT_CANDIDATES = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Regular.otf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
)


def _register_fonts() -> None:
    global ACTIVE_FONT_NAME
    if ACTIVE_FONT_NAME in pdfmetrics.getRegisteredFontNames():
        return
    font_path = os.getenv("DEBATE_PDF_FONT_PATH", "")
    candidates = (font_path,) if font_path else FONT_CANDIDATES
    for candidate in candidates:
        if not candidate or not Path(candidate).is_file():
            continue
        try:
            pdfmetrics.registerFont(TTFont(FONT_NAME, candidate, subfontIndex=0))
            ACTIVE_FONT_NAME = FONT_NAME
            return
        except Exception:
            continue
    # Last-resort fallback for hosts where a CJK font package is unavailable.
    ACTIVE_FONT_NAME = "HeiseiKakuGo-W5"
    if ACTIVE_FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(ACTIVE_FONT_NAME))


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    if isinstance(value, dict):
        return "\n".join(f"{key}: {value[key]}" for key in value)
    return str(value)


def _inline_markup(value: Any) -> str:
    source = html.escape(_text(value), quote=False)
    code_tokens: list[str] = []

    def keep_code(match: re.Match[str]) -> str:
        token = f"@@CODE_TOKEN_{len(code_tokens)}@@"
        code_tokens.append(f'<font name="Courier">{match.group(1)}</font>')
        return token

    source = re.sub(r"`([^`\n]+)`", keep_code, source)
    source = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda match: "<b>" +
                    (match.group(1) or match.group(2)) + "</b>", source)
    source = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<i>\1</i>", source)
    source = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"<i>\1</i>", source)
    source = source.replace("\n", "<br/>")
    for index, replacement in enumerate(code_tokens):
        source = source.replace(f"@@CODE_TOKEN_{index}@@", replacement)
    return source


def _styles() -> dict[str, ParagraphStyle]:
    return {
        "title": ParagraphStyle(
            "DebatePdfTitle", fontName=ACTIVE_FONT_NAME, fontSize=20, leading=27,
            alignment=TA_CENTER, textColor=colors.HexColor("#102544"),
            spaceAfter=8 * mm,
        ),
        "subtitle": ParagraphStyle(
            "DebatePdfSubtitle", fontName=ACTIVE_FONT_NAME, fontSize=10, leading=16,
            textColor=colors.HexColor("#4a5a70"), spaceAfter=4 * mm,
        ),
        "h1": ParagraphStyle(
            "DebatePdfH1", fontName=ACTIVE_FONT_NAME, fontSize=15, leading=21,
            textColor=colors.HexColor("#173d72"), spaceBefore=7 * mm,
            spaceAfter=3 * mm,
        ),
        "h2": ParagraphStyle(
            "DebatePdfH2", fontName=ACTIVE_FONT_NAME, fontSize=12, leading=18,
            textColor=colors.HexColor("#354f76"), spaceBefore=5 * mm,
            spaceAfter=2 * mm,
        ),
        "body": ParagraphStyle(
            "DebatePdfBody", fontName=ACTIVE_FONT_NAME, fontSize=10.5, leading=18,
            textColor=colors.HexColor("#202b3d"), spaceAfter=3 * mm,
        ),
        "small": ParagraphStyle(
            "DebatePdfSmall", fontName=ACTIVE_FONT_NAME, fontSize=8.5, leading=13,
            textColor=colors.HexColor("#58677c"), spaceAfter=2 * mm,
        ),
        "speaker": ParagraphStyle(
            "DebatePdfSpeaker", fontName=ACTIVE_FONT_NAME, fontSize=12, leading=18,
            textColor=colors.HexColor("#173d72"), spaceBefore=5 * mm,
            spaceAfter=2 * mm,
        ),
        "quote": ParagraphStyle(
            "DebatePdfQuote", fontName=ACTIVE_FONT_NAME, fontSize=10, leading=17,
            leftIndent=7 * mm, borderPadding=3 * mm,
            borderColor=colors.HexColor("#9db5d6"), borderWidth=1,
            borderLeft=True, textColor=colors.HexColor("#40516a"),
            backColor=colors.HexColor("#f2f6fc"), spaceAfter=3 * mm,
        ),
        "code": ParagraphStyle(
            "DebatePdfCode", fontName=ACTIVE_FONT_NAME, fontSize=8.5, leading=13,
            leftIndent=4 * mm, rightIndent=4 * mm, borderPadding=3 * mm,
            backColor=colors.HexColor("#eef2f7"), spaceAfter=3 * mm,
        ),
    }


def _markdown_flowables(markdown: Any, styles: dict[str, ParagraphStyle]) -> list[Any]:
    lines = _text(markdown).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    flowables: list[Any] = []
    paragraph_lines: list[str] = []
    code_lines: list[str] | None = None

    def flush_paragraph() -> None:
        if paragraph_lines:
            flowables.append(Paragraph(
                "<br/>".join(_inline_markup(line) for line in paragraph_lines),
                styles["body"],
            ))
            paragraph_lines.clear()

    for line in lines:
        fence = re.match(r"^\s*```", line)
        if fence and code_lines is None:
            flush_paragraph()
            code_lines = []
            continue
        if fence and code_lines is not None:
            flowables.append(Preformatted("\n".join(code_lines), styles["code"]))
            code_lines = None
            continue
        if code_lines is not None:
            code_lines.append(line)
            continue
        if not line.strip():
            flush_paragraph()
            continue

        heading = re.match(r"^\s*(#{1,3})\s+(.+?)\s*#*\s*$", line)
        if heading:
            flush_paragraph()
            style_name = "h1" if len(heading.group(1)) == 1 else "h2"
            flowables.append(Paragraph(_inline_markup(heading.group(2)), styles[style_name]))
            continue

        unordered = re.match(r"^\s*[-*+]\s+(.+)$", line)
        ordered = re.match(r"^\s*(\d+)[.)]\s+(.+)$", line)
        if unordered or ordered:
            flush_paragraph()
            marker = "・" if unordered else f"{ordered.group(1)}."
            item = unordered.group(1) if unordered else ordered.group(2)
            flowables.append(Paragraph(
                f"{marker} {_inline_markup(item)}", styles["body"],
            ))
            continue

        if re.match(r"^\s*([-*_])(?:\s*\1){2,}\s*$", line):
            flush_paragraph()
            flowables.append(HRFlowable(
                width="100%", thickness=0.6, color=colors.HexColor("#b8c4d4"),
                spaceBefore=2 * mm, spaceAfter=3 * mm,
            ))
            continue

        quote = re.match(r"^\s*>\s?(.*)$", line)
        if quote:
            flush_paragraph()
            flowables.append(Paragraph(_inline_markup(quote.group(1)), styles["quote"]))
            continue

        paragraph_lines.append(line)

    if code_lines is not None:
        flowables.append(Preformatted("\n".join(code_lines), styles["code"]))
    flush_paragraph()
    return flowables


def _footer(canvas: Any, _document: Any) -> None:
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#c9d3e0"))
    canvas.line(18 * mm, 14 * mm, 192 * mm, 14 * mm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#65748a"))
    canvas.drawString(18 * mm, 9 * mm, "Debate Demo")
    canvas.drawRightString(192 * mm, 9 * mm, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


def build_debate_pdf(session: dict[str, Any]) -> bytes:
    """Convert the completed debate's Markdown messages into a downloadable PDF."""
    _register_fonts()
    styles = _styles()
    output = io.BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=19 * mm,
        title="Debate Demo 結果",
        author="Debate Demo",
    )
    story: list[Any] = [
        Paragraph("Debate Demo 結果", styles["title"]),
        Paragraph(f"テーマ: {_inline_markup(session.get('theme', ''))}", styles["subtitle"]),
    ]

    context = session.get("theme_context") or {}
    story.append(Paragraph("学生同士の議論の出発点", styles["h1"]))
    story.extend(_markdown_flowables(
        "### Cの最終整理\n" + _text(_latest_message(session, "C", "summary")),
        styles,
    ))
    story.append(Paragraph("中心論点", styles["h2"]))
    story.extend(_markdown_flowables(
        _text(context.get("current_issue") or "Cが整理した中心論点を確認してください。"),
        styles,
    ))
    story.append(Paragraph("学生への問い", styles["h2"]))
    story.extend(_markdown_flowables(
        _text(context.get("next_instruction") or "AとBの主張を比較し、自分の考えを述べてください。"),
        styles,
    ))

    story.append(PageBreak())
    story.append(Paragraph("A・Bの最終主張", styles["h1"]))
    for speaker, label, color in (
        ("A", "賛成側", "#1f66d1"),
        ("B", "反対側", "#d83a3a"),
    ):
        story.append(Paragraph(
            f'<font color="{color}">{speaker} {label}</font>', styles["speaker"],
        ))
        story.extend(_markdown_flowables(
            _text(_latest_message(session, speaker, "closing") or _latest_message(session, speaker)),
            styles,
        ))

    story.append(PageBreak())
    story.append(Paragraph("発言履歴", styles["h1"]))
    for message in session.get("messages", []):
        story.append(Paragraph(
            f"第{int(message.get('turn_index', 0)) + 1}ターン　"
            f"{_inline_markup(message.get('speaker', ''))}　"
            f"{_inline_markup(message.get('kind', '発言'))}",
            styles["speaker"],
        ))
        story.extend(_markdown_flowables(message.get("text", ""), styles))

    document.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return output.getvalue()


def _latest_message(
    session: dict[str, Any], speaker: str, kind: str | None = None,
) -> str:
    for message in reversed(session.get("messages", [])):
        if message.get("speaker") == speaker and (kind is None or message.get("kind") == kind):
            return _text(message.get("text", ""))
    return ""

"""Searchable recipe PDFs with scaled ingredient amounts."""

import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO
from urllib.parse import quote

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Table,
    TableStyle,
)

from app.api.schemas.recipe_schema import RecipeResponse
from app.services.pdf_helpers import (
    format_minutes,
    paragraph_text,
    register_fonts,
    step_groups,
    time_facts,
)

INK = colors.HexColor("#2A211A")
MUTED = colors.HexColor("#5C4F42")
ACCENT = colors.HexColor("#2F5D46")
RULE = colors.HexColor("#D9CFBF")
PAPER = colors.HexColor("#F5F0E6")
MARGIN = 20 * mm
# SimpleDocTemplate pads its frame by 6 pt on each side.
CONTENT_WIDTH = A4[0] - 2 * MARGIN - 12
# Shorter ingredient lists stay in one column; a second column only helps longer ones.
TWO_COLUMN_INGREDIENTS = 8
# Keep in sync with ingredientAmount in site/src/lib/recipe-text.ts.
NON_SCALABLE_UNITS = {"prise", "prisen", "messerspitze", "messerspitzen", "nach geschmack"}


def pdf_filename(title: str) -> str:
    # Never put user input directly into an HTTP header or a filesystem path.
    clean = re.sub(r'[\x00-\x1f\x7f/\\]', '-', title).strip('. ') or 'Rezept'
    fallback = unicodedata.normalize("NFKD", clean).encode("ascii", "ignore").decode()
    fallback = re.sub(r'[^A-Za-z0-9 ._-]', '-', fallback).strip() or 'Rezept'
    return f'attachment; filename="{fallback}.pdf"; filename*=UTF-8\'\'{quote(clean + ".pdf", safe="")}'


def format_scaled_amount(amount: Decimal, factor: Decimal) -> str:
    """Format scaled amounts with up to three decimals and German separators."""
    value = (amount * factor).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    whole, fraction = format(value, ",f").split(".")
    fraction = fraction.rstrip("0")
    return whole.replace(",", ".") + (f",{fraction}" if fraction else "")


def _ingredient_rows(
    recipe: RecipeResponse, item_style: ParagraphStyle, group_style: ParagraphStyle, factor: Decimal,
) -> list[Paragraph]:
    groups = {group.position: group.name for group in recipe.ingredient_groups}
    rows = []
    previous_group = None
    for item in sorted(recipe.ingredients, key=lambda ingredient: ingredient.position):
        if item.group_position != previous_group and item.group_position in groups:
            rows.append(Paragraph(paragraph_text(groups[item.group_position]), group_style))
        previous_group = item.group_position
        quantity = []
        if item.amount is not None:
            unit = (item.unit or "").strip().lower()
            item_factor = Decimal(1) if unit in NON_SCALABLE_UNITS else factor
            quantity.append(format_scaled_amount(item.amount, item_factor))
        if item.unit:
            quantity.append(item.unit)
        text = paragraph_text(item.name)
        if quantity:
            text = f"<b>{paragraph_text(' '.join(quantity))}</b> {text}"
        if item.note:
            text += f" ({paragraph_text(item.note)})"
        rows.append(Paragraph(text, item_style))
    return rows


def render_recipe_pdf(
    recipe: RecipeResponse, *, factor: Decimal = Decimal(1),
) -> bytes:
    if not factor.is_finite() or factor <= 0 or factor > 1000:
        raise ValueError("Portion factor must be a positive, finite number no larger than 1000.")
    register_fonts()
    output = BytesIO()
    body = ParagraphStyle(
        "Body", fontName="Recipe", fontSize=10, leading=14,
        textColor=INK, spaceAfter=3, alignment=TA_LEFT, splitLongWords=True,
    )
    title_style = ParagraphStyle(
        "Title", parent=body, fontName="RecipeBold", fontSize=24, leading=28,
        spaceAfter=6, keepWithNext=True,
    )
    origin_style = ParagraphStyle("Origin", parent=body, fontName="RecipeItalic", fontSize=11, leading=15)
    history_style = ParagraphStyle("History", parent=body, fontName="RecipeItalic", textColor=MUTED)
    facts_style = ParagraphStyle("Facts", parent=body, fontSize=9, leading=13, textColor=MUTED, spaceBefore=5, spaceAfter=7)
    notice_style = ParagraphStyle(
        "Notice", parent=body, backColor=PAPER, borderPadding=(7, 9, 7, 9),
        leftIndent=9, rightIndent=9, spaceBefore=13, spaceAfter=11,
    )
    heading_style = ParagraphStyle(
        "Section", parent=body, fontName="RecipeBold", fontSize=13, leading=16,
        spaceBefore=12, spaceAfter=3, keepWithNext=True,
    )
    group_style = ParagraphStyle(
        "Group", parent=body, fontName="RecipeBold", fontSize=9, leading=13,
        textColor=MUTED, spaceBefore=5, spaceAfter=2, keepWithNext=True,
    )
    day_style = ParagraphStyle(
        "Day", parent=body, fontName="RecipeBold", fontSize=10.5, spaceBefore=8, spaceAfter=4, keepWithNext=True,
    )
    step_style = ParagraphStyle(
        "Step", parent=body, leftIndent=20, bulletIndent=0, bulletFontName="RecipeBold",
        bulletFontSize=11, bulletColor=ACCENT, spaceAfter=5,
    )
    step_note_style = ParagraphStyle("StepNote", parent=body, fontName="RecipeItalic", textColor=MUTED, leftIndent=20, spaceAfter=5)
    story = []

    def paragraph(text: str, style: ParagraphStyle = body) -> None:
        story.append(Paragraph(paragraph_text(text), style))

    def rule(color=RULE, before: float = 0, after: float = 6) -> None:
        story.append(HRFlowable(width="100%", thickness=0.6, color=color, spaceBefore=before, spaceAfter=after))

    def section(heading: str) -> None:
        paragraph(heading, heading_style)
        rule()

    # Titles are single-line fields in the UI, but API input may contain line
    # breaks. Collapse whitespace so a bounded title cannot become an oversized
    # keep-with-next paragraph (which ReportLab may repeatedly try to group).
    paragraph(" ".join(recipe.title.split()), title_style)
    if recipe.origin_person:
        paragraph(f"Von {recipe.origin_person}", origin_style)
    if recipe.history:
        paragraph(recipe.history, history_style)
    if recipe.summary:
        paragraph(recipe.summary)
    facts = []
    if recipe.preparation_days > 1:
        facts.append(f"Über {recipe.preparation_days} Tage")
    if recipe.servings is not None:
        facts.append(f"Für {format_scaled_amount(Decimal(recipe.servings), factor)} Portionen")
    elif factor != 1:
        facts.append(f"{format_scaled_amount(factor, Decimal(1))}-fache Menge")
    facts.extend(time_facts(recipe))
    if facts:
        paragraph("  ·  ".join(facts), facts_style)
    if recipe.important_notes:
        story.append(Paragraph(f"<b>Wichtiger Hinweis</b><br/>{paragraph_text(recipe.important_notes)}", notice_style))

    if recipe.ingredients:
        section("Zutaten")
        rows = _ingredient_rows(recipe, body, group_style, factor)
        if len(recipe.ingredients) < TWO_COLUMN_INGREDIENTS:
            story.extend(rows)
        else:
            half = (len(rows) + 1) // 2
            # A group name must not be stranded at the foot of the left column.
            if rows[half - 1].style is group_style:
                half -= 1
            left, right = rows[:half], rows[half:]
            right += [""] * (len(left) - len(right))
            left += [""] * (len(right) - len(left))
            gutter = 8 * mm
            table = Table(list(zip(left, right)), colWidths=[(CONTENT_WIDTH + gutter) / 2, (CONTENT_WIDTH - gutter) / 2], hAlign="LEFT")
            table.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (0, -1), gutter),
                ("RIGHTPADDING", (1, 0), (1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]))
            story.append(table)

    if recipe.steps:
        section("Zubereitung")
        number = 0
        for label, steps in step_groups(recipe):
            if label:
                paragraph(label, day_style)
            for step in steps:
                number += 1
                if step.heading:
                    paragraph(step.heading, day_style)
                prefix = "<b>Wichtig:</b> " if step.is_important else ""
                story.append(Paragraph(prefix + paragraph_text(step.instruction), step_style, bulletText=str(number)))
                if step.duration_minutes is not None and step.time_kind:
                    label = {"preparation": "Arbeit", "cooking": "Koch-/Backzeit", "rest": "Ruhezeit"}[step.time_kind]
                    paragraph(f"{label}: {format_minutes(step.duration_minutes)}", step_note_style)
                if step.note:
                    paragraph(step.note, step_note_style)
    if recipe.notes:
        section("Notizen")
        paragraph(recipe.notes)

    footer_title = " ".join(recipe.title.split())
    if len(footer_title) > 70:
        footer_title = footer_title[:69].rstrip() + "…"

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.6)
        canvas.line(MARGIN, 16 * mm, A4[0] - MARGIN, 16 * mm)
        canvas.setFont("Recipe", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(MARGIN, 11.5 * mm, footer_title)
        canvas.drawRightString(A4[0] - MARGIN, 11.5 * mm, f"Seite {doc.page}")
        canvas.restoreState()

    document = SimpleDocTemplate(
        output, pagesize=A4, rightMargin=MARGIN, leftMargin=MARGIN,
        topMargin=18 * mm, bottomMargin=22 * mm,
        title=recipe.title, author="Heritage Kitchen",
    )
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()

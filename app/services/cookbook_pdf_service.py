"""Readable, searchable whole-cookbook PDF without images."""

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

from app.api.schemas.recipe_schema import RecipeResponse
from app.services.pdf_helpers import (
    format_time_range,
    paragraph_text,
    register_fonts,
    step_groups,
    time_facts,
)

PAGE_MARGIN = 18 * mm


def render_cookbook_pdf(
    recipes: list[RecipeResponse],
    cookbook_name: str,
    footer_text: str = "",
) -> bytes:
    register_fonts()
    output = BytesIO()
    body = ParagraphStyle(
        "CookbookBody", fontName="Recipe", fontSize=10, leading=15,
        spaceAfter=5, splitLongWords=True,
    )
    heading = ParagraphStyle(
        "CookbookHeading", parent=body, fontName="RecipeBold",
        fontSize=20, leading=25, spaceAfter=12,
    )
    section = ParagraphStyle(
        "CookbookSection", parent=body, fontName="RecipeBold",
        fontSize=13, leading=17, spaceBefore=12, spaceAfter=6,
        keepWithNext=True,
    )
    muted = ParagraphStyle(
        "CookbookMuted", parent=body, textColor=colors.HexColor("#5C4F42"),
        fontName="RecipeItalic", fontSize=9,
    )
    cover = ParagraphStyle(
        "CookbookCover", parent=heading, fontSize=30, leading=36, spaceAfter=24,
    )
    story = [
        Spacer(1, 38 * mm),
        Paragraph(paragraph_text(cookbook_name), cover),
        Paragraph(f"{len(recipes)} Rezepte", body),
    ]
    if footer_text:
        story.append(Paragraph(paragraph_text(footer_text), muted))
    if not recipes:
        story.append(Paragraph("Noch keine Rezepte vorhanden.", body))

    def add(value: str | None, style=body) -> None:
        if value:
            story.append(Paragraph(paragraph_text(value), style))

    for recipe in recipes:
        story.append(PageBreak())
        add(recipe.title, heading)
        if recipe.category:
            add(recipe.category.name, muted)
        if recipe.origin_person:
            add("Von " + recipe.origin_person, muted)
        add(recipe.history, muted)
        add(recipe.summary)
        facts = []
        if recipe.servings is not None:
            facts.append(f"Portionen: {recipe.servings}")
        if recipe.preparation_days > 1:
            facts.append(f"Zubereitung über {recipe.preparation_days} Tage")
        facts.extend(time_facts(recipe))
        add(" · ".join(facts), muted)
        if recipe.important_notes:
            add("Wichtiger Hinweis: " + recipe.important_notes, section)
        if recipe.ingredients:
            add("Zutaten", section)
            groups = {group.position: group.name for group in recipe.ingredient_groups}
            current_group = None
            for item in sorted(recipe.ingredients, key=lambda ingredient: ingredient.position):
                if item.group_position != current_group and item.group_position in groups:
                    add(groups[item.group_position], muted)
                current_group = item.group_position
                quantity = []
                if item.amount is not None:
                    value = format(item.amount, "f")
                    quantity.append(value.rstrip("0").rstrip(".") if "." in value else value)
                if item.unit:
                    quantity.append(item.unit)
                label = " ".join([*quantity, item.name])
                if item.note:
                    label += f" ({item.note})"
                add("• " + label)
        if recipe.steps:
            add("Zubereitung", section)
            number = 0
            for day_heading, steps in step_groups(recipe):
                add(day_heading, section)
                for step in steps:
                    number += 1
                    add(step.heading, muted)
                    instruction = f"{number}. {step.instruction}"
                    if step.is_important:
                        instruction = "Wichtig: " + instruction
                    if step.duration_minutes is not None:
                        instruction += f" ({format_time_range(step.duration_minutes)})"
                    add(instruction)
                    add(step.note, muted)
        if recipe.notes:
            add("Notizen", section)
            add(recipe.notes)

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Recipe", 8)
        canvas.setFillColor(colors.HexColor("#5C4F42"))
        canvas.drawString(PAGE_MARGIN, 12 * mm, footer_text or cookbook_name)
        canvas.drawRightString(A4[0] - PAGE_MARGIN, 12 * mm, f"Seite {doc.page}")
        canvas.restoreState()

    SimpleDocTemplate(
        output, pagesize=A4, leftMargin=PAGE_MARGIN,
        rightMargin=PAGE_MARGIN, topMargin=PAGE_MARGIN,
        bottomMargin=20 * mm,
        title="Gesamtes Kochbuch", author=cookbook_name,
    ).build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()

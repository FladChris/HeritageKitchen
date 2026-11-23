"""Shared ReportLab fonts and recipe content formatting for PDF exports."""

import re
from functools import lru_cache
from pathlib import Path
from xml.sax.saxutils import escape

import reportlab
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from app.services.recipe_time_service import effective_times


@lru_cache(maxsize=1)
def register_fonts() -> None:
    fonts = Path(reportlab.__file__).parent / "fonts"
    for name, file in (("Recipe", "Vera"), ("RecipeBold", "VeraBd"), ("RecipeItalic", "VeraIt"), ("RecipeBoldItalic", "VeraBI")):
        pdfmetrics.registerFont(TTFont(name, str(fonts / f"{file}.ttf")))
    pdfmetrics.registerFontFamily(
        "Recipe", normal="Recipe", bold="RecipeBold", italic="RecipeItalic", boldItalic="RecipeBoldItalic",
    )


def format_minutes(value: int) -> str:
    days, remaining = divmod(value, 1440)
    hours, minutes = divmod(remaining, 60)
    parts = []
    if days:
        parts.append(f"{days} {'Tag' if days == 1 else 'Tage'}")
    if hours:
        parts.append(f"{hours} Std.")
    if minutes or not parts:
        parts.append(f"{minutes} Min.")
    return " ".join(parts)


def format_time_range(value: int | None, maximum: int | None = None) -> str | None:
    if value is None:
        return None
    if maximum is None or maximum <= value:
        return format_minutes(value)
    if value % 1440 == 0 and maximum % 1440 == 0:
        return f"{value // 1440}–{maximum // 1440} Tage"
    if value < 60 and maximum < 60:
        return f"{value}–{maximum} Min."
    return f"{format_minutes(value)} – {format_minutes(maximum)}"


def time_facts(recipe) -> list[str]:
    times = effective_times(recipe)
    facts = []
    for label, time in (("Arbeit", times.preparation), ("Ruhezeit", times.rest), ("Back-/Kochzeit", times.cooking)):
        if time is not None:
            facts.append(f"{label}: {format_time_range(time.minutes, time.minutes_max)}")
    if times.total is not None:
        facts.append(f"Summe der erfassten Zeiten: {format_time_range(*times.total)}")
    return facts


def step_groups(recipe) -> list[tuple[str | None, list]]:
    ordered = sorted(recipe.steps, key=lambda step: (step.day, step.position))
    if recipe.preparation_days <= 1:
        return [(None, ordered)] if ordered else []
    titles = recipe.day_titles or []
    groups: list[tuple[str | None, list]] = []
    for step in ordered:
        if not groups or groups[-1][1][-1].day != step.day:
            title = titles[step.day - 1] if step.day <= len(titles) else ""
            groups.append((f"Tag {step.day} – {title}" if title else f"Tag {step.day}", []))
        groups[-1][1].append(step)
    return groups


def paragraph_text(text: str) -> str:
    return escape(re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)).replace("\n", "<br/>")

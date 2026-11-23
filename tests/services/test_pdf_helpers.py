import pytest

from app.services.pdf_helpers import (
    format_minutes,
    format_time_range,
    step_groups,
    time_facts,
)


@pytest.mark.parametrize(("value", "expected"), [(1440, "1 Tag"), (2880, "2 Tage"), (1800, "1 Tag 6 Std."), (20, "20 Min."), (80, "1 Std. 20 Min."), (0, "0 Min.")])
def test_day_time_formatting(value, expected):
    assert format_minutes(value) == expected


def test_time_ranges():
    assert format_time_range(1440, 2880) == "1–2 Tage"
    assert format_time_range(20, 30) == "20–30 Min."
    assert format_time_range(None) is None
    assert format_time_range(60, 60) == "1 Std."


def test_time_facts_use_step_times_and_the_total_in_days():
    from types import SimpleNamespace

    steps = [SimpleNamespace(duration_minutes=1500, time_kind="rest"), SimpleNamespace(duration_minutes=None, time_kind=None)]
    recipe = SimpleNamespace(
        preparation_time=10, cooking_time=45, cooking_time_max=None, rest_time=60, rest_time_max=None, steps=steps,
    )
    assert time_facts(recipe) == [
        "Arbeit: 10 Min.", "Ruhezeit: 1 Tag 1 Std.", "Back-/Kochzeit: 45 Min.",
        "Summe der erfassten Zeiten: 1 Tag 1 Std. 55 Min.",
    ]
    assert time_facts(SimpleNamespace(
        preparation_time=None, cooking_time=None, cooking_time_max=None, rest_time=None, rest_time_max=None, steps=[],
    )) == []


def test_step_groups_follow_days_and_skip_titles_for_single_day_recipes():
    from types import SimpleNamespace

    def step(position, day):
        return SimpleNamespace(position=position, day=day)

    steps = [step(0, 2), step(1, 1), step(2, 2)]
    multi = SimpleNamespace(preparation_days=3, day_titles=["Einlegen", ""], steps=steps)
    groups = step_groups(multi)
    assert [(label, [s.position for s in items]) for label, items in groups] == [
        ("Tag 1 – Einlegen", [1]), ("Tag 2", [0, 2]),
    ]
    single = SimpleNamespace(preparation_days=1, day_titles=["Ignoriert"], steps=steps)
    assert [(label, len(items)) for label, items in step_groups(single)] == [(None, 3)]

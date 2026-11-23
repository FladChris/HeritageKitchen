from types import SimpleNamespace

from app.services.recipe_time_service import effective_times


def recipe(steps=(), **manual):
    values = {
        "preparation_time": None, "cooking_time": None, "cooking_time_max": None, "rest_time": None, "rest_time_max": None,
    }
    steps = [SimpleNamespace(duration_minutes=minutes, time_kind=kind) for minutes, kind in steps]
    return SimpleNamespace(**{**values, **manual}, steps=steps)


def test_step_times_replace_the_manual_value_only_per_time_kind():
    times = effective_times(recipe([(20, "preparation"), (5, "preparation")], preparation_time=30, cooking_time=45))
    assert (times.preparation.minutes, times.preparation.from_steps, times.preparation.manual) == (25, True, 30)
    assert (times.cooking.minutes, times.cooking.from_steps) == (45, False)
    assert effective_times(recipe(preparation_time=30)).preparation.minutes == 30


def test_total_adds_parallel_work_without_removing_overlaps():
    times = effective_times(recipe([(20, "preparation"), (40, "cooking"), (10, "cooking")]))
    assert times.total == (70, None)
    assert times.rest is None


def test_total_stays_in_minutes_across_days_and_keeps_ranges():
    assert effective_times(recipe([(1800, "rest")])).total == (1800, None)
    times = effective_times(recipe(preparation_time=10, cooking_time=30, cooking_time_max=40))
    assert times.total == (40, 50)


def test_missing_times_are_not_estimated_and_zero_manual_values_count():
    assert effective_times(recipe()).total is None
    assert effective_times(recipe(steps=[(None, None)])).total is None
    assert effective_times(recipe(preparation_time=0)).total == (0, None)


def test_replacement_is_reported_only_when_manual_value_differs():
    differs = effective_times(recipe([(20, "cooking"), (15, "cooking")], cooking_time=45, cooking_time_max=50))
    assert differs.cooking.replaces_manual is True
    assert differs.cooking.manual_max == 50
    assert effective_times(recipe([(45, "cooking")], cooking_time=45)).cooking.replaces_manual is False
    assert effective_times(recipe([(45, "cooking")])).cooking.replaces_manual is False

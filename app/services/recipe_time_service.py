from dataclasses import dataclass


@dataclass(frozen=True)
class EffectiveTime:
    minutes: int
    minutes_max: int | None
    from_steps: bool
    manual: int | None
    manual_max: int | None

    @property
    def replaces_manual(self) -> bool:
        return self.from_steps and self.manual is not None and (self.manual, self.manual_max) != (self.minutes, None)


@dataclass(frozen=True)
class EffectiveTimes:
    preparation: EffectiveTime | None
    cooking: EffectiveTime | None
    rest: EffectiveTime | None
    total: tuple[int, int | None] | None


def _effective(recipe, kind: str, manual: int | None, manual_max: int | None) -> EffectiveTime | None:
    step_minutes = [step.duration_minutes for step in recipe.steps if step.time_kind == kind and step.duration_minutes]
    if step_minutes:
        return EffectiveTime(sum(step_minutes), None, True, manual, manual_max)
    if manual is None:
        return None
    return EffectiveTime(manual, manual_max, False, manual, manual_max)


def effective_times(recipe) -> EffectiveTimes:
    """Step times replace the manual value per kind; only explicit time fields count."""
    preparation = _effective(recipe, "preparation", recipe.preparation_time, None)
    cooking = _effective(recipe, "cooking", recipe.cooking_time, recipe.cooking_time_max)
    rest = _effective(recipe, "rest", recipe.rest_time, recipe.rest_time_max)
    present = [time for time in (preparation, cooking, rest) if time is not None]
    total = None
    if present:
        low = sum(time.minutes for time in present)
        high = sum(max(time.minutes, time.minutes_max or 0) for time in present)
        total = (low, high if high > low else None)
    return EffectiveTimes(preparation, cooking, rest, total)

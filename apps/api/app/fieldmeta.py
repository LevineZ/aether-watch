"""Forecast clock helpers. Open-Meteo hourly[0] is 起报; hourly[step] is 有效."""


def field_clock(times: list[str], step: int) -> tuple[str | None, str | None]:
    if not times:
        return None, None
    si = min(max(int(step), 0), len(times) - 1)
    return times[0], times[si]

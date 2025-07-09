from datetime import datetime, timedelta

import pytest

from wikiextractor.splitRevision import convert_timestamp_to_date

timecut = convert_timestamp_to_date('2024-01-01T00:00:00Z')
lookback = timecut - timedelta(days=30)
test_cases = [
        ['2023-11-01T00:00:00Z', '2024-01-03T00:00:00Z'],
        ['2023-11-01T00:00:00Z', '2023-12-03T00:00:00Z', '2024-01-03T00:00:00Z'],
        ['2023-11-01T00:00:00Z', '2023-12-20T00:00:00Z', '2024-01-03T00:00:00Z'],
        ['2023-11-01T00:00:00Z', '2023-12-03T00:00:00Z', '2023-12-13T00:00:00Z', '2024-01-03T00:00:00Z'],
        ['2023-11-01T00:00:00Z', '2023-12-10T00:00:00Z', '2023-12-13T00:00:00Z', '2024-01-03T00:00:00Z', '2024-01-05T00:00:00Z', '2024-02-05T00:00:00Z'],
    ]

def decide_timestamp(curr_time: datetime, prev_time: datetime, timecut: datetime, lookback: datetime) -> float:
    """
    Decide if the timestamp is within the lookback period and before the timecut.
    """
    gap = curr_time - prev_time
    if prev_time < lookback:
        gap -= (lookback - prev_time)
    if curr_time > timecut:
        gap -= (curr_time - timecut)
    return gap.total_seconds()


@pytest.mark.parametrize("cases", [test_cases])
def test_split_history(cases: list[list[str]]) -> None:
    for i, case in enumerate(cases):
        prev_date = None
        max_valid_periods = 0.
        stable_timestamp = None
        for timestamp in case:
            if not prev_date:
                prev_date = convert_timestamp_to_date(timestamp)
                prev_timestamp = timestamp
                continue
            curr_date = convert_timestamp_to_date(timestamp)
            valid_periods = decide_timestamp(curr_date, prev_date, timecut, lookback)
            if valid_periods > max_valid_periods:
                max_valid_periods = valid_periods
                stable_timestamp = prev_timestamp
            prev_date = curr_date
            prev_timestamp = timestamp
        if i == 0:
            assert stable_timestamp == '2023-11-01T00:00:00Z'
            assert max_valid_periods == timedelta(days=30).total_seconds()
        elif i == 1:
            assert stable_timestamp == '2023-12-03T00:00:00Z'
            assert max_valid_periods == timedelta(days=29).total_seconds()
        elif i == 2:
            assert stable_timestamp == '2023-11-01T00:00:00Z'
            assert max_valid_periods == timedelta(days=18).total_seconds()
        elif i == 3:
            assert stable_timestamp == '2023-12-13T00:00:00Z'
            assert max_valid_periods == timedelta(days=19).total_seconds()
        elif i == 4:
            assert stable_timestamp == '2023-12-13T00:00:00Z'
            assert max_valid_periods == timedelta(days=19).total_seconds()

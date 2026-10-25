from datetime import date, timedelta

import pytest

from ashana.modules.reporting.domain.models import ReportFilter
from ashana.shared.domain import BusinessError


def test_report_dates_use_almaty_inclusive_days() -> None:
    start, end = ReportFilter(date(2026, 10, 21), date(2026, 10, 21)).bounds()
    assert start.utcoffset() == timedelta(hours=5)
    assert end - start == timedelta(days=1)
    assert start.hour == end.hour == 0


@pytest.mark.parametrize(
    "start,end",
    [
        (date(2026, 2, 2), date(2026, 2, 1)),
        (date(2024, 1, 1), date(2026, 1, 1)),
        (date.max, date.max),
    ],
)
def test_report_invalid_date_ranges(start: date, end: date) -> None:
    with pytest.raises(BusinessError):
        ReportFilter(start, end).bounds()

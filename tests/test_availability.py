from mvsuabot.availability import parse_days, parse_slots, summarize_slots


def test_empty_list_means_no_slots() -> None:
    days = parse_days([])

    assert days == []


def test_list_of_dates_means_slots() -> None:
    days = parse_days(["2026-07-02T00:00:00", "2026-07-03T00:00:00"])

    assert days == ["2026-07-02", "2026-07-03"]


def test_data_wrapper_with_dates_means_slots() -> None:
    days = parse_days({"data": [{"date": "2026-07-02T00:00:00"}]})

    assert days == ["2026-07-02"]


def test_slots_are_summarized_with_times() -> None:
    slots = parse_slots(
        {
            "data": [
                {"startTime": "09:20:00", "stopTime": "09:40:00"},
                {"startTime": "09:40:00", "stopTime": "10:00:00"},
            ]
        },
        date="2026-06-30",
    )
    availability = summarize_slots(slots)

    assert availability.has_slots
    assert "2026-06-30" in availability.summary
    assert "09:20:00-09:40:00" in availability.summary

from pathlib import Path
from mvsuabot.availability import Slot
from mvsuabot.monitor import load_last_seen_slots, save_last_seen_slots


def test_load_non_existent_file() -> None:
    path = Path("non_existent_file_xyz_123.json")
    if path.exists():
        path.unlink()
    assert load_last_seen_slots(path) == []


def test_save_and_load_slots(tmp_path: Path) -> None:
    path = tmp_path / "last_seen_slots.json"
    slots = [
        Slot(date="2026-06-30", start_time="09:20:00", stop_time="09:40:00"),
        Slot(date="2026-06-30", start_time="14:00:00", stop_time="14:20:00"),
    ]
    save_last_seen_slots(path, slots)
    loaded = load_last_seen_slots(path)
    assert len(loaded) == 2
    assert loaded[0].date == "2026-06-30"
    assert loaded[0].start_time == "09:20:00"
    assert loaded[0].stop_time == "09:40:00"
    assert loaded[1].date == "2026-06-30"
    assert loaded[1].start_time == "14:00:00"
    assert loaded[1].stop_time == "14:20:00"

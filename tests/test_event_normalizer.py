import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from event_normalizer import normalize_event, valid_event_shape


class EventNormalizerTest(unittest.TestCase):
    def test_missing_end_gets_default(self):
        event = normalize_event({"title": "会议", "start": "2026-08-20T10:00:00"})
        self.assertEqual(event["end"], "2026-08-20T11:00:00")

    def test_end_before_start_is_corrected(self):
        event = normalize_event(
            {"title": "会议", "start": "2026-08-20T10:00:00", "end": "2026-08-20T09:00:00"}
        )
        self.assertEqual(event["end"], "2026-08-20T11:00:00")

    def test_invalid_start_dropped(self):
        self.assertIsNone(normalize_event({"title": "无时间", "start": "not-a-date"}))

    def test_timezone_converted_to_local_naive(self):
        event = normalize_event(
            {"title": "UTC事件", "start": "2026-08-20T02:00:00+00:00", "end": "2026-08-20T03:00:00+00:00"}
        )
        self.assertEqual(event["start"], "2026-08-20T10:00:00")
        self.assertEqual(event["end"], "2026-08-20T11:00:00")

    def test_valid_shape(self):
        self.assertTrue(
            valid_event_shape(
                {"title": "x", "start": "2026-08-20T10:00:00", "end": "2026-08-20T11:00:00"}
            )
        )


if __name__ == "__main__":
    unittest.main()

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from event_validation import prepare_event, validate_event_input, validate_event_update


class EventValidationTest(unittest.TestCase):
    def test_valid_event_passes(self):
        event, errors = prepare_event(
            {
                "title": "项目评审",
                "start": "2026-08-20T10:00:00",
                "end": "2026-08-20T11:00:00",
                "type": "meeting",
                "status": "auto",
            }
        )
        self.assertIsNotNone(event)
        self.assertEqual(errors, [])

    def test_missing_required_fields(self):
        errors = validate_event_input({"type": "meeting"})
        self.assertIn("title 必填", errors)
        self.assertIn("start 必填", errors)

    def test_invalid_type_and_status(self):
        errors = validate_event_input(
            {
                "title": "事件",
                "start": "2026-08-20T10:00:00",
                "type": "party",
                "status": "blocked",
            }
        )
        self.assertTrue(any("type" in error for error in errors))
        self.assertTrue(any("status" in error for error in errors))

    def test_end_before_start_rejected(self):
        errors = validate_event_input(
            {
                "title": "事件",
                "start": "2026-08-20T10:00:00",
                "end": "2026-08-20T09:00:00",
            }
        )
        self.assertTrue(any("end" in error for error in errors))

    def test_partial_update_allowed(self):
        errors = validate_event_update({"title": "改后的标题"})
        self.assertEqual(errors, [])

    def test_invalid_datetime_rejected(self):
        errors = validate_event_input(
            {"title": "事件", "start": "2026-08-20T25:99:00", "end": "not-a-time"}
        )
        self.assertTrue(any("start" in error for error in errors))
        self.assertTrue(any("end" in error for error in errors))

    def test_null_description_rejected(self):
        errors = validate_event_input(
            {"title": "事件", "start": "2026-08-20T10:00:00", "description": None}
        )
        self.assertTrue(any("description" in error for error in errors))


if __name__ == "__main__":
    unittest.main()

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from event_extractor import detect_type, extract_from_email, summarize_title


class EventExtractorTest(unittest.TestCase):
    def test_assessment_priority_over_interview(self):
        self.assertEqual(detect_type("AI测评面试链接，72小时内完成"), "assessment")

    def test_deadline_priority(self):
        self.assertEqual(detect_type("测评截止时间为2026-08-25 23:00"), "deadline")

    def test_long_title_summarized(self):
        title = summarize_title(
            "【必考-72h有效】远景校园招聘综合测评 【Mandatory-72h 】Envision Campus Recruitment Assessment",
            "",
        )
        self.assertLessEqual(len(title), 24)
        self.assertNotIn("Envision", title)

    def test_title_keeps_core_action(self):
        title = summarize_title("【平安银行】招聘评估邀请函", "")
        self.assertIn("评估", title)

    def test_non_actionable_submission_skipped(self):
        events = extract_from_email(
            {
                "id": "1",
                "date": "2026-08-19T10:00:00+08:00",
                "from": "hr@example.com",
                "subject": "投递成功通知",
                "body": "您的简历已收到，请等待通知",
                "html": "",
            }
        )
        self.assertEqual(events, [])

    def test_actionable_email_uses_email_date(self):
        events = extract_from_email(
            {
                "id": "2",
                "date": "2026-08-19T10:00:00+08:00",
                "from": "hr@example.com",
                "subject": "测评邀请",
                "body": "请完成在线测评",
                "html": "",
            }
        )
        self.assertTrue(events)
        self.assertEqual(events[0]["start"], "2026-08-19T10:00:00")
        self.assertFalse(events[0]["all_day"])
        self.assertEqual(events[0]["date_source"], "email_date")


if __name__ == "__main__":
    unittest.main()

import unittest

from main import event_from_evidence


class EventFromEvidenceTest(unittest.TestCase):
    def test_uses_only_captioned_detected_object(self):
        event = event_from_evidence(
            {
                "caption": "A car passes close on the rider's left.",
                "camera_id": "bike-1",
                "detections": {
                    "detections": [
                        {"label": "car", "bbox": [0.1, 0.2, 0.4, 0.8]},
                        {"label": "person", "bbox": [0.7, 0.2, 0.8, 0.6]},
                    ]
                },
            }
        )
        self.assertEqual(event["corridor"], "shift_right")
        self.assertEqual(event["avoid"][0]["label"], "car")
        self.assertEqual(event["avoid"][0]["side"], "left")

    def test_does_not_invent_box_when_detection_is_missing(self):
        event = event_from_evidence(
            {
                "caption": "A truck passes close on the right.",
                "detections": {"detections": [{"label": "car"}]},
            }
        )
        self.assertEqual(event["corridor"], "shift_left")
        self.assertEqual(event["avoid"], [])
        self.assertEqual(event["confidence"], "low")

    def test_neutral_clip_has_center_corridor(self):
        event = event_from_evidence(
            {
                "caption": "The bicycle travels along an empty road.",
                "detections": {},
            }
        )
        self.assertEqual(event["corridor"], "center")
        self.assertEqual(event["avoid"], [])


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import data_truth_service as service


class DataTruthTests(unittest.TestCase):
    def test_missing_evidence_fails_closed(self):
        with tempfile.TemporaryDirectory() as td, patch.object(service, "ROOT", Path(td)):
            status = service.truth_status()
        self.assertFalse(status.live_promotion)
        self.assertIsNone(status.evidence_source)
        self.assertFalse(status.market_execution_eligible)

    def test_non_promoted_report_cannot_authorize_live_metrics(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            report = root / "research_data/v7/phase3i_confirmation/run/phase3i_report.json"
            report.parent.mkdir(parents=True)
            report.write_text(json.dumps({"integrity": "ok", "live_promotion": False}), encoding="utf-8")
            with patch.object(service, "ROOT", root):
                status = service.truth_status()
        self.assertFalse(status.live_promotion)
        self.assertEqual(status.evidence_integrity, "ok")


if __name__ == "__main__":
    unittest.main()

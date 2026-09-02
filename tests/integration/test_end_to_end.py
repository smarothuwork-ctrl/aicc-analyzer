from __future__ import annotations

import json
from pathlib import Path

from src.models.job_models import AnalyzerJobEvent
from src.services.analyzer_service import AnalyzerService


def test_fixture_event_processes_end_to_end():
    fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "sample_event.json"
    payload = json.loads(fixture_path.read_text())

    event = AnalyzerJobEvent.model_validate(payload)
    result = AnalyzerService().process(event)

    assert result.eval_id == "eval-123"
    assert result.account_number == "ACC-123456"
    assert result.summary_results

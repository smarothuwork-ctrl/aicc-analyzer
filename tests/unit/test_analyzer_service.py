from src.models.job_models import AnalyzerJobEvent
from src.services.analyzer_service import AnalyzerService


def test_service_process_returns_expected_result_shape():
    event = AnalyzerJobEvent(
        eval_id="eval-100",
        account_number="ACC-100",
        contract_data={
            "retail_type": "TFS_RETAIL",
            "stated_apr": 0.049,
        },
    )

    result = AnalyzerService().process(event)

    assert result.eval_id == "eval-100"
    assert result.account_number == "ACC-100"
    assert result.metrics["total_rules"] >= 1
    assert result.summary_results

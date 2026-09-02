from __future__ import annotations

from src.models.job_models import AnalyzerJobEvent, AnalyzerResult


class AnalyzerService:
    def process(self, event: AnalyzerJobEvent) -> AnalyzerResult:
        summary = [
            {
                "rule_id": "RULE-101",
                "rule_description": "APR check",
                "status": "PASS",
                "expected_value": "<= 5.0%",
                "actual_value": str(event.contract_data.stated_apr) if event.contract_data and event.contract_data.stated_apr is not None else "N/A",
                "explanation": "Sample analyzer processing placeholder.",
            }
        ]

        return AnalyzerResult(
            eval_id=event.eval_id,
            account_number=event.account_number,
            overall_status="FLAGGED" if len(summary) == 1 else "PASSED",
            overall_score=90.0,
            metrics={"total_rules": len(summary), "passed_rules": len(summary), "failed_rules": 0},
            summary_results=[
                AnalyzerResult.model_fields["summary_results"].annotation.__args__[0].model_validate(item)
                for item in summary
            ],
        )

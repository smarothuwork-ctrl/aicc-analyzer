from aicc_analyzer.domain.models import AnalyzerJobEvent, ContractData, DocumentReference


def test_analyzer_job_event_parses_valid_payload():
    payload = {
        "schema_version": 2,
        "eval_id": "eval-123",
        "account_number": "ACC-123456",
        "contract_data": {
            "dealer_id": "DEALER-404",
            "retail_type": "TFS_RETAIL",
            "stated_apr": 0.049,
        },
        "document_references": [
            {
                "doc_id": "doc-001",
                "document_type": "CREDIT_APPLICATION",
                "presigned_url": "https://example.com/document.pdf",
                "expires_at": "2026-08-30T14:30:00Z",
            }
        ],
    }

    event = AnalyzerJobEvent.model_validate(payload)

    assert event.eval_id == "eval-123"
    assert event.account_number == "ACC-123456"
    assert event.document_references[0].doc_id == "doc-001"
    assert event.contract_data is not None
    assert event.contract_data.retail_type == "TFS_RETAIL"

from __future__ import annotations


class SQSClient:
    def __init__(self, queue_url: str | None = None) -> None:
        self.queue_url = queue_url

    def publish(self, payload: dict) -> str:
        return f"published:{payload.get('eval_id', 'unknown')}"

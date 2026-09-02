from __future__ import annotations


class AnalyzerRepository:
    def save_result(self, result: dict) -> dict:
        return {"saved": True, "result": result}

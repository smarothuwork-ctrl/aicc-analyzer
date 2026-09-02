from __future__ import annotations


class RuleProvider:
    def get_rules(self, account_type: str) -> list[dict[str, str]]:
        return [
            {
                "rule_id": "RULE-101",
                "account_type": account_type,
                "field_target": "apr",
                "condition": "LESS_THAN_OR_EQUAL",
                "expected_value": "0.05",
                "severity": "CRITICAL",
                "status": "ACTIVE",
                "description": "Ensure APR does not exceed the allowed threshold.",
            }
        ]

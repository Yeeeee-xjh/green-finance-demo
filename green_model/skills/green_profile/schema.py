from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
@dataclass
class GreenProfileInput:
    company_name: str; document_id: str; text: str; metadata: dict[str,Any]=field(default_factory=dict)
    def validate(self):
        if not self.company_name or not self.document_id or not self.text.strip(): raise ValueError("company_name、document_id、text不能为空")
@dataclass
class GreenProfileOutput:
    green_relevance: Any; evidence_strength: Any; claim_type: Any; topic: Any; model_confidence: Any
    usable_fact_candidate: bool; evidence_items: list[dict[str,Any]]; human_review_required: bool; decision_boundary: str

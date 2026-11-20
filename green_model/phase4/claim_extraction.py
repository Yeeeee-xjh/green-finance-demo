"""Adapters that connect BERT claim screening to case evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Sequence

from green_model.agent.domain.enums import CoverageStatus
from green_model.agent.domain.models import stable_id
from green_model.phase3.bert_adapter import BertInferenceAdapter

from .contracts import (
    ClaimExtractionResult,
    EvidenceInput,
    ExtractedClaim,
    ModelPredictionDecision,
)


def _json_object(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


@dataclass(frozen=True)
class ModelInferencePolicy:
    """Conservative screening policy; thresholds are governance guardrails.

    These defaults are not claimed as empirically optimal cut-offs.  They only
    stop uncertain classifier output from being silently converted into a risk
    finding.  A future validated policy can be injected without changing the
    case/risk contracts.
    """

    version: str = "risk-screening-policy/1.0"
    minimum_relevance_confidence: float = 0.60
    minimum_relevance_margin: float = 0.10
    minimum_auxiliary_confidence: float = 0.50


def _probability_metrics(
    probabilities: Any, label: Any
) -> tuple[float | None, float | None]:
    if not isinstance(probabilities, dict) or label is None:
        return None, None
    parsed: list[float] = []
    selected: float | None = None
    for key, value in probabilities.items():
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number < 0 or number > 1:
            continue
        parsed.append(number)
        if str(key) == str(label):
            selected = number
    if selected is None or not parsed:
        return None, None
    ordered = sorted(parsed, reverse=True)
    runner_up = ordered[1] if len(ordered) > 1 else 0.0
    return selected, selected - runner_up


def _is_irrelevant_label(value: Any) -> bool:
    return str(value).strip().lower() in {
        "0", "false", "not_green", "irrelevant", "非绿色", "非绿色相关"
    }


class BertClaimExtractor:
    """Use the real local checkpoint when available; never fabricate fallback scores."""

    name = "bert-green-claim-extractor"
    version = "1.1.0"

    def __init__(
        self,
        adapter: BertInferenceAdapter,
        policy: ModelInferencePolicy | None = None,
    ):
        self.adapter = adapter
        self.policy = policy or ModelInferencePolicy()

    def extract(
        self, case_id: str, evidence: Sequence[EvidenceInput]
    ) -> ClaimExtractionResult:
        usable = [item for item in evidence if item.text.strip()]
        if not usable:
            return ClaimExtractionResult(
                claims=(),
                coverage_status=CoverageStatus.INSUFFICIENT_EVIDENCE,
                message="当前没有可用的已解析文本，不生成模型主张。",
            )

        sentence_lineage: list[tuple[str, EvidenceInput]] = []
        for item in usable:
            for sentence in self.adapter._input_sentences([item.text]):
                sentence_lineage.append((sentence, item))

        run = self.adapter.run(
            case_id,
            [item.text for item in usable],
            inference_policy_version=self.policy.version,
        )
        model_run_id = run.get("model_run_id")
        if run.get("status") != "completed" or not run.get("is_real_model_result"):
            return ClaimExtractionResult(
                claims=(),
                coverage_status=CoverageStatus.MODEL_NOT_RUN,
                message=run.get("degradation_reason") or "BERT模型未完成运行。",
                model_run_id=model_run_id,
            )

        output = _json_object(run.get("output_json")) or {}
        predictions = output.get("predictions") or []
        claims: list[ExtractedClaim] = []
        decisions: list[ModelPredictionDecision] = []
        decision_counts = {"accepted_for_review": 0, "screened_out": 0, "abstained": 0}
        for prediction in predictions:
            text = str(prediction.get("text") or "").strip()
            if not text:
                continue
            try:
                sentence_index = int(prediction.get("sentence_index"))
            except (TypeError, ValueError):
                sentence_index = len(decisions)
            lineage = (
                sentence_lineage[sentence_index]
                if 0 <= sentence_index < len(sentence_lineage)
                else None
            )
            source_sentence, source = lineage if lineage else (None, None)
            evidence_id = source.evidence_id if source else None
            relevance = prediction.get("green_relevance")
            evidence_strength = prediction.get("evidence_strength")
            claim_type = prediction.get("claim_type")
            probability_object = prediction.get("class_probabilities")
            probability_object = probability_object if isinstance(probability_object, dict) else {}
            relevance_confidence, relevance_margin = _probability_metrics(
                probability_object.get("relevance"), relevance
            )
            evidence_confidence, _ = _probability_metrics(
                probability_object.get("evidence_strength"), evidence_strength
            )
            claim_confidence, _ = _probability_metrics(
                probability_object.get("claim_type"), claim_type
            )

            abstention_reason: str | None = None
            decision_status = "accepted_for_review"
            expected_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            supplied_hash = str(prediction.get("sentence_sha256") or expected_hash)
            if source_sentence is None:
                abstention_reason = "missing_input_lineage"
            elif source_sentence != text or supplied_hash != expected_hash:
                abstention_reason = "sentence_lineage_mismatch"
            elif relevance_confidence is None or relevance_margin is None:
                abstention_reason = "missing_relevance_probabilities"
            elif relevance_confidence < self.policy.minimum_relevance_confidence:
                abstention_reason = "relevance_confidence_below_policy"
            elif relevance_margin < self.policy.minimum_relevance_margin:
                abstention_reason = "relevance_margin_below_policy"
            elif _is_irrelevant_label(relevance):
                decision_status = "screened_out"
            elif evidence_confidence is None or claim_confidence is None:
                abstention_reason = "missing_auxiliary_probabilities"
            elif min(evidence_confidence, claim_confidence) < self.policy.minimum_auxiliary_confidence:
                abstention_reason = "auxiliary_confidence_below_policy"
            if abstention_reason:
                decision_status = "abstained"

            prediction_id = stable_id(
                "prediction",
                f"{model_run_id}:{sentence_index}:{evidence_id or ''}:{supplied_hash}",
            )
            decisions.append(ModelPredictionDecision(
                prediction_id=prediction_id,
                model_run_id=str(model_run_id),
                sentence_index=sentence_index,
                sentence_sha256=supplied_hash,
                text=text,
                decision_status=decision_status,
                inference_policy_version=self.policy.version,
                evidence_id=evidence_id,
                doc_id=source.doc_id if source else None,
                page_number=source.page_number if source else None,
                abstention_reason=abstention_reason,
                green_relevance=str(relevance) if relevance is not None else None,
                green_relevance_confidence=relevance_confidence,
                green_relevance_margin=relevance_margin,
                evidence_strength=(str(evidence_strength) if evidence_strength is not None else None),
                evidence_strength_confidence=evidence_confidence,
                claim_type=str(claim_type) if claim_type is not None else None,
                claim_type_confidence=claim_confidence,
                class_probabilities=probability_object,
            ))
            decision_counts[decision_status] += 1
            if decision_status != "accepted_for_review":
                continue
            support_status = self._support_status(evidence_strength, claim_type)
            claims.append(ExtractedClaim(
                text=text,
                claim_type=str(claim_type) if claim_type is not None else None,
                green_relevance=str(relevance) if relevance is not None else None,
                evidence_strength=(
                    str(evidence_strength) if evidence_strength is not None else None
                ),
                support_status=support_status,
                evidence_id=evidence_id,
                extraction_method=f"{self.name}/{self.version}",
                is_model_output=True,
                model_run_id=model_run_id,
                prediction_id=prediction_id,
                inference_policy_version=self.policy.version,
                metadata={
                    "screening_score": prediction.get("green_relevance_score"),
                    "relevance_confidence": relevance_confidence,
                    "relevance_margin": relevance_margin,
                    "inference_policy_version": self.policy.version,
                    "score_boundary": "文本筛查排序分，不是漂绿概率或授信概率。",
                },
            ))
        if decisions and decision_counts["abstained"] == len(decisions):
            coverage = CoverageStatus.MODEL_ABSTAINED
        else:
            coverage = CoverageStatus.ASSESSED
        return ClaimExtractionResult(
            claims=tuple(claims),
            coverage_status=coverage,
            message=(
                f"模型完成{len(decisions)}个句子筛查："
                f"{decision_counts['accepted_for_review']}条进入人工复核，"
                f"{decision_counts['screened_out']}条筛除，"
                f"{decision_counts['abstained']}条因不确定性弃权。"
            ),
            model_run_id=model_run_id,
            predictions=tuple(decisions),
        )

    @staticmethod
    def _support_status(evidence_strength: Any, claim_type: Any) -> str:
        strength = str(evidence_strength or "").lower()
        claim = str(claim_type or "").lower()
        if any(term in claim for term in ("负面风险", "处罚")):
            return "contradicted"
        if strength in {
            "0", "none", "weak", "unsupported", "无证据", "弱证据", "主张/无证据"
        }:
            return "unsupported"
        if (
            claim in {"commitment", "target", "promise", "承诺", "目标", "目标承诺"}
            or strength in {"1", "narrative", "叙事", "行动或一般事实"}
        ) and strength in {
            "", "unknown", "1", "narrative", "叙事", "行动或一般事实"
        }:
            return "pending_review"
        return "supported"


class UnavailableClaimExtractor:
    """Explicit adapter for deployments where no model endpoint is connected."""

    name = "unavailable-claim-extractor"
    version = "1.0.0"

    def __init__(self, reason: str = "主张识别模型未接入"):
        self.reason = reason

    def extract(
        self, case_id: str, evidence: Sequence[EvidenceInput]
    ) -> ClaimExtractionResult:
        return ClaimExtractionResult(
            claims=(),
            coverage_status=CoverageStatus.MODEL_NOT_RUN,
            message=self.reason,
        )

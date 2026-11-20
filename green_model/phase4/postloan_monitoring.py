"""Industry-pack driven post-loan indicator loading and B-T-A evaluation.

The service is intentionally narrow:

* loading an indicator definition never creates a task or a risk finding;
* values are compared only after Baseline, Target and Actual share one basis;
* only an adverse deviation crossing an explicit configured threshold opens a
  review task;
* the task key is identical to the unified risk engine's B-T-A semantic key,
  so a later case-intelligence run reuses the task instead of duplicating it;
* anything backed by a mock definition or mock observation stays
  ``pending_verification``.

It does not make a credit decision and does not call the legacy scoring model.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

from green_model.agent.domain.enums import DataOrigin, TaskStatus
from green_model.agent.domain.models import (
    AuditLog,
    BTAIndicator,
    Task,
    new_id,
    stable_id,
    utc_now,
)
from green_model.agent.storage.repository import SQLiteRepository


ENGINE_VERSION = "postloan-bta/1.0"
INDICATOR_CATEGORIES = (
    "funds_use",
    "construction_progress",
    "environmental_performance",
    "compliance_event",
)
SERIES_TYPES = ("baseline", "target", "actual")
CORE_BASIS_FIELDS = ("unit", "statistical_scope")
OPTIONAL_BASIS_FIELDS = ("measurement_method", "measurement_boundary", "basis_version")


@dataclass(frozen=True)
class IndicatorLoadResult:
    case_id: str
    industry_code: str | None
    loaded_indicator_ids: tuple[str, ...]
    reused_indicator_ids: tuple[str, ...]
    skipped_definition_ids: tuple[str, ...]
    covered_categories: tuple[str, ...]
    missing_categories: tuple[str, ...]


@dataclass(frozen=True)
class EvaluationResult:
    evaluation_id: str
    indicator_id: str
    comparability_status: str
    breach_level: str
    result_status: str
    review_task_id: str | None
    is_mock: bool
    reused: bool = False


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _industry_code(case: Mapping[str, Any]) -> str | None:
    explicit = str(case.get("industry_code") or "").strip()
    if re.fullmatch(r"\d{4}", explicit):
        return explicit
    for field in ("primary_industry", "project_activity"):
        value = str(case.get(field) or "")
        match = re.search(r"(?<!\d)(\d{4})(?!\d)", value)
        if match:
            return match.group(1)
    return None


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        parsed = Decimal(str(value).replace(",", ""))
        return parsed if parsed.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def _risk_semantic_key(
    indicator_id: str, target_value: Decimal, actual_value: Decimal
) -> str:
    # Must stay byte-for-byte compatible with unified_risk._key("bta", ...).
    raw = f"bta|{indicator_id}|{target_value}|{actual_value}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _evaluation_semantic_key(
    indicator_id: str,
    observations: Mapping[str, Mapping[str, Any]],
) -> str:
    raw = "|".join(
        ["postloan-evaluation", indicator_id]
        + [str((observations.get(kind) or {}).get("observation_id") or "") for kind in SERIES_TYPES]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _latest_by_series(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in sorted(
        (dict(item) for item in rows),
        key=lambda item: (
            str(item.get("observed_at") or ""),
            str(item.get("created_at") or ""),
            str(item.get("observation_id") or ""),
        ),
    ):
        kind = str(row.get("series_type") or "")
        if kind in SERIES_TYPES:
            result[kind] = row
    return result


def _basis_mismatches(
    observations: Mapping[str, Mapping[str, Any]],
    *,
    expected: Mapping[str, Any] | None = None,
) -> list[str]:
    rows = [observations[kind] for kind in SERIES_TYPES]
    mismatches: list[str] = []
    for field in CORE_BASIS_FIELDS:
        values = [str(row.get(field) or "").strip() for row in rows]
        if any(not value for value in values):
            mismatches.append(f"missing:{field}")
        elif len(set(values)) != 1:
            mismatches.append(field)
    for field in OPTIONAL_BASIS_FIELDS:
        values = [str(row.get(field) or "").strip() for row in rows]
        if any(values) and (any(not value for value in values) or len(set(values)) != 1):
            mismatches.append(field)
    expected = expected or {}
    for field in CORE_BASIS_FIELDS + OPTIONAL_BASIS_FIELDS:
        expected_value = str(expected.get(field) or "").strip()
        if not expected_value:
            continue
        if any(str(row.get(field) or "").strip() != expected_value for row in rows):
            marker = f"definition:{field}"
            if marker not in mismatches:
                mismatches.append(marker)
    return mismatches


class PostloanMonitoringService:
    def __init__(self, repository: SQLiteRepository):
        self.repository = repository

    def load_industry_indicators(
        self, case_id: str, *, actor: str = "system"
    ) -> IndicatorLoadResult:
        """Materialize execution-ready post-loan definitions for one case.

        Formal definitions require a qualified Phase 3.6 lineage item.  Mock
        definitions require simulation lineage and retain ``is_mock=1``.  A
        definition without category, direction, unit, scope or both thresholds
        is kept in the master pack but skipped here: the engine does not invent
        operational settings.
        """

        case = self.repository.get("cases", case_id)
        if case is None:
            raise KeyError(f"案件不存在：{case_id}")
        industry_code = _industry_code(case)
        if industry_code is None:
            return IndicatorLoadResult(
                case_id=case_id,
                industry_code=None,
                loaded_indicator_ids=(),
                reused_indicator_ids=(),
                skipped_definition_ids=(),
                covered_categories=(),
                missing_categories=INDICATOR_CATEGORIES,
            )

        definitions = self.repository.find(
            "postloan_indicator_definitions", filters={"industry_code": industry_code}
        )
        phase36_items = self.repository.find(
            "phase36_rule_items", filters={"industry_code": industry_code}
        )
        lineage_by_record = {
            str(row.get("record_id")): row
            for row in phase36_items
            if row.get("module") == "postloan"
            and row.get("record_table") == "postloan_indicator_definitions"
        }

        loaded: list[str] = []
        reused: list[str] = []
        skipped: list[str] = []
        covered: set[str] = set()
        with self.repository.transaction() as uow:
            for definition in definitions:
                definition_id = str(definition["postloan_indicator_id"])
                lineage = lineage_by_record.get(definition_id)
                is_mock = bool(definition.get("is_mock"))
                if not self._definition_is_eligible(definition, lineage):
                    skipped.append(definition_id)
                    continue
                if not self._definition_is_executable(definition):
                    skipped.append(definition_id)
                    continue

                indicator_id = stable_id("bta", f"{case_id}:{definition_id}")
                status = "pending_verification" if is_mock else "pending_data"
                existing = uow.get("bta_indicators", indicator_id)
                record = BTAIndicator(
                    indicator_id=indicator_id,
                    case_id=case_id,
                    definition_id=definition_id,
                    indicator_name=str(definition.get("indicator_name") or ""),
                    indicator_category=str(definition.get("indicator_category") or ""),
                    direction=str(definition.get("comparison_direction") or ""),
                    unit=str(definition.get("unit") or ""),
                    statistical_scope=str(definition.get("statistical_scope") or ""),
                    reporting_frequency=str(definition.get("frequency") or ""),
                    warning_deviation_ratio=str(definition.get("warning_deviation_ratio") or ""),
                    critical_deviation_ratio=str(definition.get("critical_deviation_ratio") or ""),
                    measurement_method=definition.get("measurement_method"),
                    measurement_boundary=definition.get("measurement_boundary"),
                    basis_version=definition.get("basis_version"),
                    source_manifest_id=definition.get("source_id"),
                    is_mock=is_mock,
                    status=status,
                    record_origin=DataOrigin.SYSTEM_DERIVED,
                ).to_record()
                if existing:
                    uow.update(
                        "bta_indicators",
                        indicator_id,
                        {key: value for key, value in record.items() if key not in {
                            "indicator_id", "case_id", "created_at", "updated_at", "row_version"
                        }},
                        expected_version=existing["row_version"],
                    )
                    reused.append(indicator_id)
                else:
                    uow.insert("bta_indicators", record)
                    loaded.append(indicator_id)
                covered.add(str(definition["indicator_category"]))

            uow.add(AuditLog(
                case_id=case_id,
                action="postloan_indicators_loaded",
                actor=actor,
                details_json={
                    "industry_code": industry_code,
                    "loaded_count": len(loaded),
                    "reused_count": len(reused),
                    "skipped_definition_ids": sorted(skipped),
                    "task_created": False,
                },
            ))

        return IndicatorLoadResult(
            case_id=case_id,
            industry_code=industry_code,
            loaded_indicator_ids=tuple(loaded),
            reused_indicator_ids=tuple(reused),
            skipped_definition_ids=tuple(sorted(skipped)),
            covered_categories=tuple(category for category in INDICATOR_CATEGORIES if category in covered),
            missing_categories=tuple(category for category in INDICATOR_CATEGORIES if category not in covered),
        )

    @staticmethod
    def _definition_is_eligible(
        definition: Mapping[str, Any], lineage: Mapping[str, Any] | None
    ) -> bool:
        if lineage is None or str(definition.get("scope_status") or "") != "core":
            return False
        is_mock = bool(definition.get("is_mock"))
        if is_mock:
            return (
                bool(lineage.get("is_mock"))
                and lineage.get("lineage_kind") == "simulation"
                and int(lineage.get("formal_density_eligible") or 0) == 0
                and lineage.get("validation_status") != "qualified"
            )
        return (
            not bool(lineage.get("is_mock"))
            and lineage.get("lineage_kind") != "simulation"
            and int(lineage.get("formal_density_eligible") or 0) == 1
            and lineage.get("validation_status") == "qualified"
        )

    @staticmethod
    def _definition_is_executable(definition: Mapping[str, Any]) -> bool:
        required = (
            "indicator_category",
            "comparison_direction",
            "unit",
            "statistical_scope",
            "warning_deviation_ratio",
            "critical_deviation_ratio",
        )
        if any(definition.get(field) in (None, "") for field in required):
            return False
        warning = _decimal(definition.get("warning_deviation_ratio"))
        critical = _decimal(definition.get("critical_deviation_ratio"))
        return bool(
            definition.get("indicator_category") in INDICATOR_CATEGORIES
            and definition.get("comparison_direction") in {
                "higher_is_better", "lower_is_better"
            }
            and warning is not None
            and critical is not None
            and Decimal("0") <= warning <= critical
        )

    def record_observation(
        self,
        indicator_id: str,
        *,
        series_type: str,
        normalized_value: str | int | float | Decimal,
        unit: str,
        statistical_scope: str,
        period_label: str | None = None,
        observed_at: str | None = None,
        measurement_method: str | None = None,
        measurement_boundary: str | None = None,
        basis_version: str | None = None,
        evidence_id: str | None = None,
        source_id: str | None = None,
        is_mock: bool = False,
        actor: str = "system",
    ) -> str:
        if series_type not in SERIES_TYPES:
            raise ValueError(f"不支持的B-T-A序列：{series_type}")
        if _decimal(normalized_value) is None:
            raise ValueError("normalized_value必须是有限十进制数")
        indicator = self.repository.get("bta_indicators", indicator_id)
        if indicator is None:
            raise KeyError(f"贷后指标不存在：{indicator_id}")
        effective_mock = bool(indicator.get("is_mock")) or bool(is_mock)
        observation_id = new_id("btaobs")
        now = utc_now()
        with self.repository.transaction() as uow:
            uow.insert("bta_observations", {
                "observation_id": observation_id,
                "indicator_id": indicator_id,
                "series_type": series_type,
                "period_label": period_label,
                "observed_at": observed_at,
                "raw_value": str(normalized_value),
                "normalized_value": str(normalized_value),
                "unit": unit,
                "statistical_scope": statistical_scope,
                "measurement_method": measurement_method,
                "measurement_boundary": measurement_boundary,
                "basis_version": basis_version,
                "evidence_id": evidence_id,
                "source_id": source_id,
                "status": "pending_verification",
                "is_mock": int(effective_mock),
                "created_at": now,
                "updated_at": now,
                "row_version": 1,
            })
            uow.add(AuditLog(
                case_id=indicator["case_id"],
                action="postloan_observation_recorded",
                actor=actor,
                details_json={
                    "indicator_id": indicator_id,
                    "observation_id": observation_id,
                    "series_type": series_type,
                    "is_mock": effective_mock,
                },
            ))
        return observation_id

    def evaluate_indicator(
        self, indicator_id: str, *, actor: str = "system"
    ) -> EvaluationResult:
        indicator = self.repository.get("bta_indicators", indicator_id)
        if indicator is None:
            raise KeyError(f"贷后指标不存在：{indicator_id}")
        observations = _latest_by_series(self.repository.find(
            "bta_observations", filters={"indicator_id": indicator_id}
        ))
        missing = [kind for kind in SERIES_TYPES if kind not in observations]
        is_mock = bool(indicator.get("is_mock")) or any(
            bool(row.get("is_mock")) for row in observations.values()
        )
        mismatch_fields: list[str] = []
        comparability_status = "comparable"
        result_status = "pending_verification" if is_mock else "ready_for_review"
        breach_level = "unknown"
        adverse: bool | None = None
        target_actual_ratio: Decimal | None = None
        baseline_actual_ratio: Decimal | None = None
        threshold_used: str | None = None
        threshold_origin: str | None = None

        if missing:
            comparability_status = "missing_series"
            mismatch_fields = [f"missing:{kind}" for kind in missing]
            result_status = "pending_verification" if is_mock else "incomplete"
        else:
            mismatch_fields = _basis_mismatches(observations, expected=indicator)
            if mismatch_fields:
                comparability_status = "basis_mismatch"
                result_status = "pending_verification" if is_mock else "basis_mismatch"
            values = {
                kind: _decimal(observations[kind].get("normalized_value"))
                for kind in SERIES_TYPES
            }
            if not mismatch_fields and any(value is None for value in values.values()):
                comparability_status = "invalid_numeric"
                result_status = "pending_verification" if is_mock else "incomplete"
            if comparability_status == "comparable":
                baseline = values["baseline"]
                target = values["target"]
                actual = values["actual"]
                assert baseline is not None and target is not None and actual is not None
                target_scale = abs(target)
                baseline_scale = abs(baseline)
                target_actual_ratio = (
                    (actual - target) / target_scale if target_scale else Decimal("0")
                )
                baseline_actual_ratio = (
                    (actual - baseline) / baseline_scale if baseline_scale else Decimal("0")
                )
                direction = str(indicator.get("direction") or "")
                adverse = (
                    actual < target if direction == "higher_is_better"
                    else actual > target if direction == "lower_is_better"
                    else None
                )
                warning = _decimal(indicator.get("warning_deviation_ratio"))
                critical = _decimal(indicator.get("critical_deviation_ratio"))
                if (
                    adverse is None
                    or warning is None
                    or critical is None
                    or warning < 0
                    or critical < warning
                ):
                    comparability_status = "threshold_not_configured"
                    breach_level = "unknown"
                    result_status = "pending_verification" if is_mock else "pending_configuration"
                else:
                    threshold_origin = "industry_indicator_definition"
                    adverse_ratio = abs(target_actual_ratio) if adverse else Decimal("0")
                    if adverse_ratio >= critical:
                        breach_level = "critical"
                        threshold_used = str(critical)
                    elif adverse_ratio >= warning:
                        breach_level = "warning"
                        threshold_used = str(warning)
                    else:
                        breach_level = "none"

        if comparability_status == "comparable":
            target_value = _decimal(observations["target"].get("normalized_value"))
            actual_value = _decimal(observations["actual"].get("normalized_value"))
            assert target_value is not None and actual_value is not None
            semantic_key = _risk_semantic_key(indicator_id, target_value, actual_value)
        else:
            semantic_key = _evaluation_semantic_key(indicator_id, observations)
        evaluation_id = stable_id("posteval", f"{indicator['case_id']}:{semantic_key}:{ENGINE_VERSION}")
        existing = self.repository.get("postloan_evaluations", evaluation_id)
        if existing:
            return EvaluationResult(
                evaluation_id=evaluation_id,
                indicator_id=indicator_id,
                comparability_status=str(existing["comparability_status"]),
                breach_level=str(existing["breach_level"]),
                result_status=str(existing["result_status"]),
                review_task_id=existing.get("review_task_id"),
                is_mock=bool(existing.get("is_mock")),
                reused=True,
            )

        review_task_id: str | None = None
        with self.repository.transaction() as uow:
            for old in uow.find("postloan_evaluations", filters={
                "indicator_id": indicator_id, "is_current": 1
            }):
                uow.update(
                    "postloan_evaluations",
                    old["evaluation_id"],
                    {"is_current": 0},
                    expected_version=old["row_version"],
                )

            if comparability_status == "comparable" and breach_level in {"warning", "critical"}:
                review_task_id = stable_id(
                    "task", f"{indicator['case_id']}:risk_clue_review:{semantic_key}"
                )
                task = uow.get("tasks", review_task_id)
                if task is None:
                    ratio_text = (
                        f"{abs(target_actual_ratio) * Decimal('100'):.2f}%"
                        if target_actual_ratio is not None else "未知"
                    )
                    uow.add(Task(
                        task_id=review_task_id,
                        case_id=indicator["case_id"],
                        task_type="risk_clue_review",
                        trigger_reason=(
                            f"贷后指标“{indicator.get('indicator_name') or indicator_id}”"
                            f"出现{ratio_text}不利偏离，达到{breach_level}复核阈值。"
                        ),
                        related_entity_type="postloan_evaluation",
                        related_entity_id=evaluation_id,
                        status=TaskStatus.PENDING,
                        closure_condition="核对同口径原始凭证、偏离原因和整改情况后，由复核人确认。",
                    ))

            now = utc_now()
            uow.insert("postloan_evaluations", {
                "evaluation_id": evaluation_id,
                "case_id": indicator["case_id"],
                "indicator_id": indicator_id,
                "semantic_key": semantic_key,
                "baseline_observation_id": (observations.get("baseline") or {}).get("observation_id"),
                "target_observation_id": (observations.get("target") or {}).get("observation_id"),
                "actual_observation_id": (observations.get("actual") or {}).get("observation_id"),
                "comparability_status": comparability_status,
                "mismatch_fields_json": _json(mismatch_fields),
                "target_actual_deviation_ratio": (
                    str(target_actual_ratio) if target_actual_ratio is not None else None
                ),
                "baseline_actual_change_ratio": (
                    str(baseline_actual_ratio) if baseline_actual_ratio is not None else None
                ),
                "adverse_direction": None if adverse is None else int(adverse),
                "threshold_used": threshold_used,
                "threshold_origin": threshold_origin,
                "breach_level": breach_level,
                "result_status": result_status,
                "review_task_id": review_task_id,
                "engine_version": ENGINE_VERSION,
                "is_mock": int(is_mock),
                "is_current": 1,
                "created_at": now,
                "updated_at": now,
                "row_version": 1,
            })
            uow.add(AuditLog(
                case_id=indicator["case_id"],
                action="postloan_indicator_evaluated",
                actor=actor,
                details_json={
                    "evaluation_id": evaluation_id,
                    "indicator_id": indicator_id,
                    "comparability_status": comparability_status,
                    "mismatch_fields": mismatch_fields,
                    "breach_level": breach_level,
                    "review_task_id": review_task_id,
                    "is_mock": is_mock,
                },
            ))

        return EvaluationResult(
            evaluation_id=evaluation_id,
            indicator_id=indicator_id,
            comparability_status=comparability_status,
            breach_level=breach_level,
            result_status=result_status,
            review_task_id=review_task_id,
            is_mock=is_mock,
        )

    def evaluate_case(
        self, case_id: str, *, actor: str = "system"
    ) -> tuple[EvaluationResult, ...]:
        indicators = self.repository.find("bta_indicators", filters={"case_id": case_id})
        return tuple(
            self.evaluate_indicator(str(indicator["indicator_id"]), actor=actor)
            for indicator in indicators
            if indicator.get("definition_id")
        )


__all__ = [
    "ENGINE_VERSION",
    "EvaluationResult",
    "INDICATOR_CATEGORIES",
    "IndicatorLoadResult",
    "PostloanMonitoringService",
]

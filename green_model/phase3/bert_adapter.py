"""Real GreenMultiTask checkpoint adapter with an explicit unavailable state."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from pathlib import Path
from typing import Any

from green_model.agent.domain.enums import DataOrigin
from green_model.agent.domain.models import ModelRun, utc_now
from green_model.agent.storage import SQLiteRepository


class BertInferenceAdapter:
    def __init__(
        self,
        repository: SQLiteRepository,
        model_dir: str | Path | None = None,
        *,
        force_unavailable_reason: str | None = None,
    ):
        self.repository = repository
        self.model_dir = Path(model_dir or Path(__file__).resolve().parents[1] / "models" / "green_multitask")
        self.force_unavailable_reason = force_unavailable_reason

    def availability(self) -> tuple[bool, str]:
        if self.force_unavailable_reason:
            return False, self.force_unavailable_reason
        missing = [name for name in ("torch", "transformers") if importlib.util.find_spec(name) is None]
        if missing:
            return False, "当前运行环境未安装真实推理依赖：" + "、".join(missing)
        for required in ("best_model.pt", "model_config.json", "label_mapping.json", "tokenizer"):
            if not (self.model_dir / required).exists():
                return False, f"模型资产不完整：缺少 {required}"
        return True, "真实模型可运行"

    @staticmethod
    def _input_sentences(texts: list[str]) -> list[str]:
        sentences: list[str] = []
        for text in texts:
            for item in re.split(r"(?<=[。！？；])|[\r\n]+", text):
                cleaned = item.strip()
                if cleaned:
                    sentences.append(cleaned)
        return sentences

    def run(
        self,
        case_id: str,
        texts: list[str],
        *,
        inference_policy_version: str | None = None,
    ) -> dict[str, Any]:
        sentences = self._input_sentences(texts)
        input_hash = hashlib.sha256("\n".join(sentences).encode("utf-8")).hexdigest()
        available, reason = self.availability()
        run = ModelRun(
            case_id=case_id,
            model_name="中文BERT多任务绿色文本筛查",
            model_version="green-multitask/checkpoint-epoch-3",
            input_hash=input_hash,
            status="running" if available else "not_run",
            started_at=utc_now(),
            finished_at=None if available else utc_now(),
            degradation_reason=None if available else reason,
            record_origin=DataOrigin.SYSTEM_DERIVED,
            is_real_model_result=available,
            eligible_for_decision=False,
            confidence_definition="分类头softmax仅用于文本筛查排序，不是项目合规、授信或漂绿概率。",
            inference_policy_version=inference_policy_version,
            runtime_metadata_json={
                "sentence_count": len(sentences),
                "runtime_available": available,
            },
        )
        self.repository.add(run)
        if not available:
            return self.repository.get("model_runs", run.model_run_id) or run.to_record()
        if not sentences:
            return self._finish(run, "not_run", None, "没有可供模型筛查的已解析文本", False)
        try:
            output, checkpoint_hash = self._infer(sentences)
            return self._finish(run, "completed", output, None, True, checkpoint_hash)
        except Exception as exc:
            return self._finish(run, "failed", None, str(exc)[:800], False)

    def _infer(self, sentences: list[str]) -> tuple[dict[str, Any], str]:
        import torch
        from transformers import AutoTokenizer

        from green_model.pipeline.modeling import GreenMultiTaskModel

        checkpoint_path = self.model_dir / "best_model.pt"
        checkpoint_hash = self._sha256(checkpoint_path)
        checkpoint = torch.load(checkpoint_path, map_location="cpu")
        tokenizer = AutoTokenizer.from_pretrained(self.model_dir / "tokenizer", local_files_only=True)
        model = GreenMultiTaskModel(checkpoint["model_name"], local_files_only=True)
        model.load_state_dict(checkpoint["model_state"])
        model.eval()
        labels = json.loads((self.model_dir / "label_mapping.json").read_text(encoding="utf-8"))
        predictions: list[dict[str, Any]] = []
        batch_size = 12
        with torch.no_grad():
            for start in range(0, len(sentences), batch_size):
                batch = sentences[start : start + batch_size]
                encoded = tokenizer(batch, truncation=True, max_length=int(checkpoint.get("max_length", 320)), padding=True, return_tensors="pt")
                relevance, evidence, claim = model(**encoded)
                relevance_p = relevance.softmax(1)
                evidence_p = evidence.softmax(1)
                claim_p = claim.softmax(1)
                for index, sentence in enumerate(batch):
                    rel_id = int(relevance_p[index].argmax())
                    evidence_id = int(evidence_p[index].argmax())
                    claim_id = int(claim_p[index].argmax())
                    predictions.append({
                        "sentence_index": start + index,
                        "sentence_sha256": hashlib.sha256(sentence.encode("utf-8")).hexdigest(),
                        "text": sentence,
                        "green_relevance": labels["relevance"][str(rel_id)],
                        "green_relevance_score": float(relevance_p[index, 1]),
                        "evidence_strength": labels["evidence_strength"][str(evidence_id)],
                        "claim_type": labels["claim_type"][str(claim_id)],
                        "class_probabilities": {
                            "relevance": {
                                labels["relevance"][str(i)]: float(relevance_p[index, i])
                                for i in range(relevance_p.shape[1])
                            },
                            "evidence_strength": {
                                labels["evidence_strength"][str(i)]: float(evidence_p[index, i])
                                for i in range(evidence_p.shape[1])
                            },
                            "claim_type": {
                                labels["claim_type"][str(i)]: float(claim_p[index, i])
                                for i in range(claim_p.shape[1])
                            },
                        },
                    })
        return {
            "sentence_count": len(sentences),
            "predictions": predictions,
            "boundary": "仅用于企业披露文本筛查和阅读排序，不进入项目核验结论。",
        }, checkpoint_hash

    def _finish(
        self,
        run: ModelRun,
        status: str,
        output: dict[str, Any] | None,
        reason: str | None,
        real_result: bool,
        checkpoint_hash: str | None = None,
    ) -> dict[str, Any]:
        current = self.repository.get("model_runs", run.model_run_id)
        if current is None:
            raise LookupError("模型运行记录不存在")
        return self.repository.update("model_runs", run.model_run_id, {
            "status": status,
            "finished_at": utc_now(),
            "output_json": json.dumps(output, ensure_ascii=False, sort_keys=True) if output is not None else None,
            "degradation_reason": reason,
            "checkpoint_hash": checkpoint_hash,
            "is_real_model_result": real_result,
            "eligible_for_decision": False,
        }, expected_version=current["row_version"])

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

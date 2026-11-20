from __future__ import annotations
from dataclasses import asdict
from typing import Any
from green_model.agent.skills import GreenProfileSkill as _ContractAdapter
from .schema import GreenProfileInput
class GreenProfileSkill:
    """中文BERT多任务模型画像结果的正式契约入口；不以模板替代模型判断。"""
    name="green_profile_skill"
    def run(self, payload: GreenProfileInput|dict[str,Any], model_result:dict[str,Any]|None=None)->dict[str,Any]:
        data=asdict(payload) if isinstance(payload,GreenProfileInput) else dict(payload); GreenProfileInput(**data).validate()
        raw=dict(model_result or {}); raw.update({"company_name":data["company_name"],"document_id":data["document_id"]})
        if not model_result: raw["sentences"]=[{"sentence":data["text"],"source_document":data["document_id"],"verification_status":"unverified"}]
        result=_ContractAdapter.from_profile(raw); result["model_name"]="中文BERT多任务模型"; result["inference_status"]="model_result_supplied" if model_result else "awaiting_model_inference"
        return result
    @staticmethod
    def from_profile(profile): return _ContractAdapter.from_profile(profile)

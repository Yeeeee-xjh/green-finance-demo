from dataclasses import dataclass,field
from typing import Any
@dataclass
class PostloanInput:
    case_id:str; metrics:list[dict[str,Any]]; evidence:list[dict[str,Any]]=field(default_factory=list); events:list[dict[str,Any]]=field(default_factory=list); transaction_monitoring_signal:dict[str,Any]|None=None
    def validate(self):
        if not self.case_id: raise ValueError("case_id不能为空")

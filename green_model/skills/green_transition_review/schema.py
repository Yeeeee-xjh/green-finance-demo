from dataclasses import dataclass,field
from pathlib import Path
from typing import Any
@dataclass
class ReviewInput:
    case_id:str; project:dict[str,Any]; project_description:str; evidence:list[dict[str,Any]]=field(default_factory=list); industry:str=""; bank_rule_pack:Path|None=None
    def validate(self):
        if not self.case_id or not self.project_description.strip(): raise ValueError("case_id和project_description不能为空")

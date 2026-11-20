from __future__ import annotations

import torch
from torch import nn
from transformers import AutoModel


class GreenMultiTaskModel(nn.Module):
    def __init__(self, model_name: str, dropout: float = 0.2, local_files_only: bool = False):
        super().__init__()
        self.model_name = model_name
        self.encoder = AutoModel.from_pretrained(model_name, local_files_only=local_files_only)
        hidden = self.encoder.config.hidden_size
        self.dropout = nn.Dropout(dropout)
        self.rel_head = nn.Linear(hidden, 2)
        self.evi_head = nn.Linear(hidden, 3)
        self.claim_head = nn.Linear(hidden, 5)

    def forward(self, input_ids, attention_mask, token_type_ids=None):
        kwargs = {"input_ids": input_ids, "attention_mask": attention_mask}
        if token_type_ids is not None:
            kwargs["token_type_ids"] = token_type_ids
        output = self.encoder(**kwargs)
        pooled = output.pooler_output if getattr(output, "pooler_output", None) is not None else output.last_hidden_state[:, 0]
        pooled = self.dropout(pooled)
        return self.rel_head(pooled), self.evi_head(pooled), self.claim_head(pooled)

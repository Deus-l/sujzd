"""
СУЖЦД — Pydantic-схемы для FastAPI (входные/выходные модели API)
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------

class DocumentCreate(BaseModel):
    id:           str
    doc_type:     str
    name:         str
    designation:  str = ""
    version:      str = "1.0"
    branch_name:  str = "main"
    fields_json:  Dict[str, Any] = {}


class DocumentOut(BaseModel):
    id:          str
    doc_type:    str
    name:        str
    designation: str
    version:     str
    status:      str
    branch_name: str
    created_at:  datetime
    updated_at:  datetime
    fields_json: Dict[str, Any]

    class Config:
        from_attributes = True


class DocumentUpdate(BaseModel):
    """Частичное обновление документа (PATCH)"""
    name:        Optional[str] = None
    designation: Optional[str] = None
    version:     Optional[str] = None
    status:      Optional[str] = None


# ---------------------------------------------------------------------------
# Delta
# ---------------------------------------------------------------------------

class DeltaCreate(BaseModel):
    doc_id:         str
    field_id:       str
    field_name:     str = ""
    v_before:       str = ""
    v_after:        str
    omega_type:     str
    author:         str
    reason:         str = ""
    iin:            str = ""
    branch:         str = "main"
    parent_ids:     List[str] = []
    project_stage:  Optional[str] = None  # ТП | РД | ИЗГОТ | ЭКСПЛ (§4.3)


class DeltaOut(BaseModel):
    id:           str
    short_sha:    str
    doc_id:       str
    doc_type:     str
    field_id:     str
    field_name:   str
    v_before:     str
    v_after:      str
    omega_type:   str
    author:       str
    iin:          str
    reason:       str
    branch_name:  str
    cascade_count:int
    committed_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Branch
# ---------------------------------------------------------------------------

class BranchCreate(BaseModel):
    name:        str
    description: str = ""
    base:        str = "main"


class BranchOut(BaseModel):
    id:          int
    name:        str
    description: str
    base_branch: str
    head_delta:  Optional[str]
    is_merged:   bool
    created_at:  datetime

    class Config:
        from_attributes = True


class MergeRequest(BaseModel):
    source:   str
    target:   str = "main"
    resolver: str = ""


# ---------------------------------------------------------------------------
# Notification
# ---------------------------------------------------------------------------

class NotificationOut(BaseModel):
    id:              int
    delta_id:        str
    trigger_doc_id:  str
    trigger_doc_nm:  str
    source_field:    str = ""
    target_doc_id:   Optional[str] = None
    target_doc_type: str
    target_doc_name: str
    target_field:    str
    target_field_nm: str
    dep_type:        str
    omega_type:      str
    assignee:        str
    status:          str
    deadline:        Optional[datetime]
    created_at:      datetime
    resolved_at:     Optional[datetime]
    notes:           str
    norm_ref:        str = ""

    class Config:
        from_attributes = True


class NotificationResolve(BaseModel):
    notes: str = ""
    completed_by: str = ""   # исполнитель (для события NotificationCompleted)


# ---------------------------------------------------------------------------
# IA Module
# ---------------------------------------------------------------------------

class ClassifyRequest(BaseModel):
    field_id:  str
    v_before:  str
    v_after:   str
    doc_type:  str = ""


class AnalyzeRequest(BaseModel):
    delta_id:  str
    api_key:   Optional[str] = None   # GROQ_API_KEY | HF_TOKEN | ANTHROPIC_API_KEY
    provider:  str = "openrouter"     # "openrouter" (default) | "groq" | "huggingface" | "anthropic"
    hf_model:  Optional[str] = None   # переопределить модель (для groq и hf)


class SignificanceRequest(BaseModel):
    omega_type:    str
    cascade_count: int = 0


class StepDeltaRequest(BaseModel):
    content_before: str
    content_after:  str


class XlsxDeltaRequest(BaseModel):
    rows_before:   List[Dict[str, Any]]
    rows_after:    List[Dict[str, Any]]
    field_mapping: Dict[str, str] = {}


class DocxDeltaRequest(BaseModel):
    paragraphs_before: List[str]
    paragraphs_after:  List[str]


# ---------------------------------------------------------------------------
# Checkout / Diff / Blame
# ---------------------------------------------------------------------------

class CheckoutRequest(BaseModel):
    doc_id:    str
    timestamp: datetime


class DiffRequest(BaseModel):
    doc_id: str
    t1:     Optional[datetime] = None
    t2:     Optional[datetime] = None


# ---------------------------------------------------------------------------
# Conflict
# ---------------------------------------------------------------------------

class ConflictResolve(BaseModel):
    conflict_id:    int
    resolved_value: str
    resolver:       str

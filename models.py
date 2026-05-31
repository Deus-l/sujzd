"""
СУЖЦД — Система Управления Жизненным Циклом Документации
Модели базы данных (SQLAlchemy)
"""
from datetime import datetime
from sqlalchemy import (
    Column, String, Text, DateTime, ForeignKey, Float, Boolean, JSON, Integer
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class DocumentType(Base):
    """Тип документа из реестра схем (DSR)"""
    __tablename__ = "document_types"

    code        = Column(String(32), primary_key=True)   # ESKD_DETAIL, ESTD_MK …
    std         = Column(String(8),  nullable=False)      # ЕСКД / ЕСТД / ЕСПД
    short_code  = Column(String(8),  nullable=False)      # ЧД, МК, ТЗ …
    name        = Column(String(128),nullable=False)
    gost        = Column(String(64))
    fields_json = Column(JSON, default=list)              # список описаний полей

    documents = relationship("DocumentInstance", back_populates="doc_type_obj")


class DocumentInstance(Base):
    """Экземпляр документа"""
    __tablename__ = "documents"

    id           = Column(String(32), primary_key=True)   # DOC-001 …
    doc_type     = Column(String(32), ForeignKey("document_types.code"), nullable=False)
    name         = Column(String(256), nullable=False)
    designation  = Column(String(128), default="")
    version      = Column(String(16), default="1.0")
    status       = Column(String(16), default="active")  # active | pending | archived
    branch_name  = Column(String(64), default="main")
    created_at   = Column(DateTime, default=datetime.utcnow)
    updated_at   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    fields_json  = Column(JSON, default=dict)             # текущие значения полей

    doc_type_obj  = relationship("DocumentType", back_populates="documents")
    deltas        = relationship("Delta", back_populates="document", order_by="Delta.committed_at")


class Delta(Base):
    """
    Атомарная единица изменения: δ = ⟨DocType, DocID, Field, V_before, V_after⟩
    + метаданные M(δ) = ⟨ID, Author, Timestamp, Ω, IIN, Parents⟩
    """
    __tablename__ = "deltas"

    id            = Column(String(64),  primary_key=True)  # sha256 хэш
    short_sha     = Column(String(8),   nullable=False)
    doc_id        = Column(String(32),  ForeignKey("documents.id"), nullable=False)
    doc_type      = Column(String(32),  nullable=False)
    field_id      = Column(String(64),  nullable=False)
    field_name    = Column(String(128), nullable=False)
    v_before      = Column(Text,        default="")
    v_after       = Column(Text,        default="")
    omega_type    = Column(String(4),   nullable=False)    # Ω₁ … Ω₇
    author        = Column(String(128), nullable=False)
    iin           = Column(String(64),  default="")        # Извещение об изменении
    reason        = Column(Text,        default="")
    branch_name   = Column(String(64),  default="main")
    parent_ids    = Column(JSON,        default=list)      # ссылки на родительские δ
    committed_at  = Column(DateTime,    default=datetime.utcnow)
    cascade_count = Column(Integer,     default=0)

    document      = relationship("DocumentInstance", back_populates="deltas")
    notifications = relationship("Notification", back_populates="delta")


class Branch(Base):
    """Ветка — именованный указатель на вершину линии дельт"""
    __tablename__ = "branches"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    name        = Column(String(64), nullable=False, unique=True)
    description = Column(Text, default="")
    base_branch = Column(String(64), default="main")
    head_delta  = Column(String(64), ForeignKey("deltas.id"), nullable=True)
    is_merged   = Column(Boolean, default=False)
    created_at  = Column(DateTime, default=datetime.utcnow)
    merged_at   = Column(DateTime, nullable=True)


class Notification(Base):
    """Задача по зависимой дельте, генерируется Движком зависимостей"""
    __tablename__ = "notifications"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    delta_id       = Column(String(64), ForeignKey("deltas.id"), nullable=False)
    trigger_doc_id = Column(String(32), nullable=False)
    trigger_doc_nm = Column(String(256), nullable=False)
    source_field   = Column(String(64),  default="")   # поле-источник (§4.2.1)
    target_doc_id  = Column(String(32),  nullable=True)   # конкретный экземпляр цели (None = виртуальный)
    target_doc_type= Column(String(32), nullable=False)
    target_doc_name= Column(String(256), nullable=False)
    target_field   = Column(String(64),  nullable=False)
    target_field_nm= Column(String(128), nullable=False)
    dep_type       = Column(String(2),   nullable=False)   # "1" | "R"
    omega_type     = Column(String(4),   nullable=False)
    assignee       = Column(String(128), default="")
    status         = Column(String(16),  default="pending")  # pending | resolved | skipped
    deadline       = Column(DateTime,    nullable=True)
    created_at     = Column(DateTime,    default=datetime.utcnow)
    resolved_at    = Column(DateTime,    nullable=True)
    notes          = Column(Text,        default="")
    norm_ref       = Column(String(128), default="")   # ГОСТ-ссылка из матрицы (TC-15)

    delta = relationship("Delta", back_populates="notifications")


class ConflictRecord(Base):
    """Конфликт слияния двух веток в одном поле"""
    __tablename__ = "conflicts"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    doc_id        = Column(String(32), nullable=False)
    field_id      = Column(String(64), nullable=False)
    branch_a      = Column(String(64), nullable=False)
    branch_b      = Column(String(64), nullable=False)
    value_base    = Column(Text, default="")
    value_a       = Column(Text, default="")
    value_b       = Column(Text, default="")
    resolved_value= Column(Text, nullable=True)
    status        = Column(String(16), default="open")    # open | resolved
    created_at    = Column(DateTime, default=datetime.utcnow)
    resolved_at   = Column(DateTime, nullable=True)
    resolver      = Column(String(128), default="")


class AuditEvent(Base):
    """Журнал событий шины (Event Bus)"""
    __tablename__ = "audit_events"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(64), nullable=False)   # DeltaCommitted, TaskCreated …
    payload    = Column(JSON, default=dict)
    occurred_at= Column(DateTime, default=datetime.utcnow)

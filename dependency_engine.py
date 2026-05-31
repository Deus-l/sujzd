"""
СУЖЦД — Движок зависимостей (Dependency Engine)
Реализует логику матрицы M[DocType][Field][Ω] → зависимые документы.
При фиксации дельты вычисляет каскад зависимостей E(δ) и создаёт задачи.
"""
import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from sqlalchemy.orm import Session

from models import Delta, Notification, DocumentInstance, AuditEvent

# Дедлайны по умолчанию (рабочих дней → datetime timedelta в календарных)
DEADLINES: Dict[str, Dict[str, int]] = {
    "Ω₃": {"1": 2, "R": 7},
    "Ω₂": {"1": 3, "R": 7},
    "Ω₄": {"1": 3, "R": 7},
    "Ω₅": {"1": 4, "R": 10},
    "Ω₆": {"1": 5, "R": 14},
    "Ω₇": {"1": 2, "R": 5},
    "Ω₁": {"1": 99, "R": 99},
}

_matrix: List[Dict] = []


def _load_matrix():
    global _matrix
    path = os.path.join(os.path.dirname(__file__), "data", "matrix.json")
    with open(path, encoding="utf-8") as f:
        _matrix = json.load(f)


_load_matrix()

# Кэш DSR для фильтрации по lifecycle и omega_sensitivity
_dsr: Dict[str, Dict] = {}


def _load_dsr():
    global _dsr
    path = os.path.join(os.path.dirname(__file__), "data", "dsr.json")
    with open(path, encoding="utf-8") as f:
        _dsr = json.load(f)


_load_dsr()

# Карта ответственных по типу документа (§5.3)
_ASSIGNEE_MAP: Dict[str, str] = {
    # ЕСКД — конструктор
    "ESKD_DETAIL":    "конструктор",
    "ESKD_SPEC":      "конструктор",
    "ESKD_SCHEME_E3": "конструктор",
    "ESKD_FORMULAR":  "конструктор",
    "ESKD_TU":        "конструктор",
    "ESKD_VP":        "конструктор",
    "ESKD_MRB":       "конструктор",
    "ESKD_3D":        "конструктор",
    "ESKD_PATENT":    "конструктор",
    "ESKD_CALC":      "конструктор",
    # ЕСТД — технолог
    "ESTD_MK":        "технолог",
    "ESTD_KK":        "технолог",
    "ESTD_OK":        "технолог",
    "ESTD_KTK":       "технолог",
    "ESTD_VP":        "технолог",
    "ESTD_OP":        "технолог",
    "ESTD_ML":        "технолог",
    "ESTD_VT":        "технолог",
    # ЕСПД — программист
    "ESPD_TZ":        "программист",
    "ESPD_TP":        "программист",
    "ESPD_PP":        "программист",
    "ESPD_IP":        "программист",
    "ESPD_RM":        "программист",
    "ESPD_RO":        "программист",
    "ESPD_RSP":       "программист",
    "ESPD_TEST":      "программист",
}


def _target_active_in_lifecycle(target_type: str,
                                project_stage: Optional[str]) -> bool:
    """
    Проверяет, обязателен ли целевой документ на текущей стадии ЖЦ.
    Если стадия не задана — фильтрация отключена (все проходят).
    раздел 4.3: если зависимый документ не обязателен на данной стадии,
    уведомление не создаётся.
    """
    if project_stage is None:
        return True
    lc = _dsr.get(target_type, {}).get("lifecycle", [])
    return not lc or project_stage in lc


def _source_omega_sensitive(source_type: str, omega: str) -> bool:
    """
    Проверяет, реагирует ли тип документа-источника на данный Ω.
    раздел 4.3: omega_sensitivity фильтрует типы Ω, при которых поле
    активирует каскадную зависимость.
    """
    sensitivity = _dsr.get(source_type, {}).get("omega_sensitivity", [])
    return not sensitivity or omega in sensitivity


def _get_links_cascade(source_type: str, source_field: str,
                       project_stage: Optional[str] = None) -> List[Dict]:
    """
    Дополнительные зависимости из DSR links (§3.2.2).
    links — массив строк «TargetType.target_field» в каждом поле DSR.
    Генерирует рекомендованные (R) правила, не дублируя уже имеющиеся
    в _matrix (сравнение по source_type+source_field+target_type+target_field).
    """
    existing_keys = {
        (r["source_type"], r["source_field"], r["target_type"], r["target_field"])
        for r in _matrix
    }
    extra: List[Dict] = []
    field_def = next(
        (f for f in _dsr.get(source_type, {}).get("fields", [])
         if f["id"] == source_field),
        None,
    )
    if not field_def:
        return extra
    for link in field_def.get("links", []):
        parts = link.split(".", 1)
        if len(parts) != 2:
            continue
        tgt_type, tgt_field = parts
        key = (source_type, source_field, tgt_type, tgt_field)
        if key in existing_keys:
            continue
        if not _target_active_in_lifecycle(tgt_type, project_stage):
            continue
        extra.append({
            "id": f"DSR_{source_type}_{source_field}_{tgt_type}_{tgt_field}",
            "source_type": source_type,
            "source_field": source_field,
            "target_type": tgt_type,
            "target_field": tgt_field,
            "dep_type": "R",
            "omega_types": ["Ω₂", "Ω₃", "Ω₄", "Ω₅", "Ω₆", "Ω₇"],
            "description": f"Ссылка DSR: {source_type}.{source_field} → {tgt_type}.{tgt_field}",
            "norm_ref": "DSR",
        })
    return extra


def get_cascade(source_type: str, source_field: str, omega: str,
                project_stage: Optional[str] = None) -> List[Dict]:
    """
    E(δ) = все зависимости из матрицы M + DSR links для данного (DocType, Field, Ω).
    Ω₁ всегда возвращает пустой список (каскад не требуется).
    Фильтры (раздел 4.3):
      - omega_sensitivity: данный Ω должен быть в списке чувствительности источника
      - lifecycle: целевой документ должен быть обязателен на текущей стадии ЖЦ
    """
    if omega == "Ω₁":
        return []
    if not _source_omega_sensitive(source_type, omega):
        return []
    matrix_rules = [
        rule for rule in _matrix
        if rule["source_type"] == source_type
        and rule["source_field"] == source_field
        and omega in rule["omega_types"]
        and _target_active_in_lifecycle(rule["target_type"], project_stage)
    ]
    # Дополнить зависимостями из DSR links (§3.2.2)
    link_rules = [
        r for r in _get_links_cascade(source_type, source_field, project_stage)
        if omega in r["omega_types"]
    ]
    return matrix_rules + link_rules


def process_delta(db: Session, delta: Delta,
                  project_stage: Optional[str] = None) -> List[Notification]:
    """
    Основная функция движка: получить дельту → вычислить E(δ) → создать задачи.
    Идемпотентна: пропускает правила, для которых уведомление уже существует
    (проверяет по комбинации delta_id + target_doc_type + target_field + target_doc_id).
    project_stage: стадия ЖЦ (ТП | РД | ИЗГОТ | ЭКСПЛ) для фильтрации
                   по lifecycle. None = без фильтрации.
    """
    cascade = get_cascade(delta.doc_type, delta.field_id, delta.omega_type,
                          project_stage)
    notifications: List[Notification] = []

    # Собрать уже существующие уведомления для этой дельты.
    # Дедупликация по правилу (target_type + target_field): если уведомление для
    # данного правила уже существует (виртуальное или реальное), пропускаем всё
    # правило целиком — иначе при повторном вызове (recalculate-cascade) появятся
    # дубли для каждого нового документа нужного типа.
    existing_notifs = (
        db.query(Notification)
        .filter(Notification.delta_id == delta.id)
        .all()
    )
    existing_keys: set = {
        (n.target_doc_type, n.target_field)
        for n in existing_notifs
    }

    # Найти все документы-цели (любой экземпляр нужного типа)
    for rule in cascade:
        target_docs = (
            db.query(DocumentInstance)
            .filter(DocumentInstance.doc_type == rule["target_type"])
            .all()
        )

        if not target_docs:
            # Создаём «виртуальное» уведомление — документа нет в системе,
            # но зависимость нормативно обязательна
            target_docs = [_virtual_doc(rule["target_type"])]

        # Если для этого правила уже есть уведомление — пропускаем всё правило
        rule_key = (rule["target_type"], rule["target_field"])
        if rule_key in existing_keys:
            continue

        for tdoc in target_docs:
            tdoc_id = getattr(tdoc, "id", None)

            deadline_days = DEADLINES.get(delta.omega_type, {}).get(rule["dep_type"], 7)
            deadline = datetime.utcnow() + timedelta(days=deadline_days)

            # Имя поля из DSR
            target_field_name = _field_name(rule["target_type"], rule["target_field"])

            notif = Notification(
                delta_id=delta.id,
                trigger_doc_id=delta.doc_id,
                trigger_doc_nm=_doc_name(db, delta.doc_id),
                source_field=delta.field_id,       # §4.2.1: поле-источник зависимости
                target_doc_id=tdoc_id,             # None для _virtual_doc
                target_doc_type=rule["target_type"],
                target_doc_name=getattr(tdoc, "name", rule["target_type"]),
                target_field=rule["target_field"],
                target_field_nm=target_field_name,
                dep_type=rule["dep_type"],
                omega_type=delta.omega_type,
                status="pending",
                deadline=deadline,
                norm_ref=rule.get("norm_ref", ""),   # TC-15: ГОСТ-ссылка из матрицы
                assignee=_ASSIGNEE_MAP.get(rule["target_type"], ""),  # §5.3
            )
            db.add(notif)
            notifications.append(notif)

            # Отметить только реальный ORM-объект (не _virtual_doc) как «ожидающий обновления»
            if hasattr(tdoc, "id") and hasattr(tdoc, "status"):
                tdoc.status = "pending"

        existing_keys.add(rule_key)  # предотвратить дубли внутри одного вызова

    # Обновить счётчик каскадов в дельте (только обязательные, раздел 4.4)
    # Учитываем уже существующие обязательные уведомления + новые
    all_mandatory = len([n for n in existing_notifs if n.dep_type == "1"]) + \
                    len([n for n in notifications if n.dep_type == "1"])
    delta.cascade_count = all_mandatory

    if notifications:  # аудит только если созданы новые уведомления
        db.add(AuditEvent(event_type="DependencyTasksCreated", payload={
            "delta_id": delta.id,
            "cascade_count": len(notifications),
            "omega": delta.omega_type,
        }))

    db.flush()
    return notifications


def get_full_cascade_tree(delta_id: str, db: Session) -> dict:
    """
    Строит полное дерево каскада для отображения в графе.
    Включает информацию об источнике, всех зависимых документах и типах зависимостей.
    """
    delta = db.query(Delta).filter(Delta.id == delta_id).first()
    if not delta:
        return {}

    cascade_rules = get_cascade(delta.doc_type, delta.field_id, delta.omega_type)
    notifs = db.query(Notification).filter(Notification.delta_id == delta_id).all()
    doc = db.query(DocumentInstance).filter(DocumentInstance.id == delta.doc_id).first()

    nodes = [{
        "role": "source",
        "doc_id": delta.doc_id,
        "doc_type": delta.doc_type,
        "doc_name": doc.name if doc else delta.doc_id,
        "field": delta.field_id,
        "field_name": delta.field_name,
        "v_before": delta.v_before,
        "v_after": delta.v_after,
        "omega": delta.omega_type,
    }]

    for rule in cascade_rules:
        n = next((x for x in notifs if x.target_doc_type == rule["target_type"]
                  and x.target_field == rule["target_field"]), None)
        nodes.append({
            "role": "target",
            "doc_type": rule["target_type"],
            "target_field": rule["target_field"],
            "target_field_name": _field_name(rule["target_type"], rule["target_field"]),
            "dep_type": rule["dep_type"],
            "description": rule["description"],
            "status": n.status if n else "ожидает",
        })

    return {
        "delta_id": delta_id,
        "omega": delta.omega_type,
        "requires_ii": delta.omega_type != "Ω₁",
        "total_cascade": len(cascade_rules),
        "mandatory": sum(1 for r in cascade_rules if r["dep_type"] == "1"),
        "recommended": sum(1 for r in cascade_rules if r["dep_type"] == "R"),
        "nodes": nodes,
        "gost_reference": "ГОСТ Р 2.503–2023, п. 4.2",
    }


def reload_matrix():
    """Перезагрузка матрицы и DSR из файлов (без перезапуска сервера)"""
    _load_matrix()
    _load_dsr()
    return {
        "rules": len(_matrix),
        "dsr_types": len(_dsr),
        "mandatory": sum(1 for r in _matrix if r["dep_type"] == "1"),
        "recommended": sum(1 for r in _matrix if r["dep_type"] == "R"),
    }


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _doc_name(db: Session, doc_id: str) -> str:
    doc = db.query(DocumentInstance).filter(DocumentInstance.id == doc_id).first()
    return doc.name if doc else doc_id


class _virtual_doc:
    """Заглушка для документа, которого нет в БД"""
    def __init__(self, dtype: str):
        self.name = f"[{dtype}] — документ не зарегистрирован"
        self.status = "pending"


def _field_name(doc_type: str, field_id: str) -> str:
    """Получить имя поля из кэша DSR (без I/O на каждый вызов)"""
    for fld in _dsr.get(doc_type, {}).get("fields", []):
        if fld["id"] == field_id:
            return fld["name"]
    return field_id


def get_matrix_stats() -> dict:
    rules = _matrix
    return {
        "total_rules": len(rules),
        "mandatory": sum(1 for r in rules if r["dep_type"] == "1"),
        "recommended": sum(1 for r in rules if r["dep_type"] == "R"),
        "source_types": list({r["source_type"] for r in rules}),
        "target_types": list({r["target_type"] for r in rules}),
    }

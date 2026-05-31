"""
СУЖЦД — Репозиторий дельт (Delta Repository)
Git-подобная объектная модель: commit, checkout, diff, blame, branch, merge
"""
import hashlib
import json
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from models import Delta, DocumentInstance, Branch, ConflictRecord, AuditEvent, Notification


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def compute_sha256(doc_type: str, doc_id: str, field: str,
                   v_before: str, v_after: str, author: str, ts: str) -> str:
    content = f"{doc_type}|{doc_id}|{field}|{v_before}|{v_after}|{author}|{ts}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def publish_event(db: Session, event_type: str, payload: dict):
    ev = AuditEvent(event_type=event_type, payload=payload)
    db.add(ev)


# ---------------------------------------------------------------------------
# Операция: commit
# ---------------------------------------------------------------------------

def commit_delta(db: Session, doc_id: str, field_id: str, field_name: str,
                 v_before: str, v_after: str, omega: str, author: str,
                 reason: str = "", iin: str = "", branch: str = "main",
                 parent_ids: list = None) -> Delta:
    """
    Фиксация атомарной дельты.
    1. Вычисление SHA-256 идентификатора
    2. Проверка консистентности (V_before = текущее значение поля)
    3. Обновление полей документа
    4. Публикация события DeltaCommitted в шину
    """
    doc = db.query(DocumentInstance).filter(DocumentInstance.id == doc_id).first()
    if not doc:
        raise ValueError(f"Документ {doc_id} не найден")

    # Проверка консистентности (аналог git: нельзя применить патч к изменённому файлу)
    current_value = doc.fields_json.get(field_id, "")
    if v_before != current_value and v_before != "":
        raise ValueError(
            f"Конфликт: текущее значение поля «{field_name}» = «{current_value}», "
            f"ожидалось «{v_before}». Выполните checkout или разрешите конфликт."
        )

    # Блокировка: проверить незакрытые обязательные уведомления на это конкретное поле документа.
    # §5.4: «обязательные зависимости блокируют закрытие исходного изменения»
    # Фильтр по target_doc_name + target_doc_type — чтобы не блокировать ВСЕ документы одного типа.
    blocking = (
        db.query(Notification)
        .filter(
            Notification.target_doc_id   == doc_id,     # точно: конкретный экземпляр
            Notification.target_field    == field_id,
            Notification.dep_type        == "1",
            Notification.status          == "pending",
        )
        .first()
    )
    # Fallback для старых уведомлений без target_doc_id (виртуальные или до миграции)
    if not blocking:
        blocking = (
            db.query(Notification)
            .filter(
                Notification.target_doc_id   == None,
                Notification.target_doc_type == doc.doc_type,
                Notification.target_doc_name == doc.name,
                Notification.target_field    == field_id,
                Notification.dep_type        == "1",
                Notification.status          == "pending",
            )
            .first()
        )
    if blocking:
        raise ValueError(
            f"Поле «{field_name}» заблокировано незакрытым обязательным уведомлением "
            f"#{blocking.id} (ГОСТ Р 2.503–2023 п. 4.2). "
            f"Завершите или отклоните задачу перед внесением новых изменений."
        )

    ts_str = datetime.utcnow().isoformat()
    full_sha = compute_sha256(doc.doc_type, doc_id, field_id, v_before, v_after, author, ts_str)
    short_sha = full_sha[:8]

    # IIN: для Ω₁ (редакционные) ИИ не требуется — §2.1.2
    # Используем short_sha для уникальности (нет race condition в отличие от COUNT)
    if omega == "Ω₁":
        iin = None
    elif not iin:
        iin = f"ИИ-{datetime.utcnow().year}-{short_sha.upper()}"

    delta = Delta(
        id=full_sha,
        short_sha=short_sha,
        doc_id=doc_id,
        doc_type=doc.doc_type,
        field_id=field_id,
        field_name=field_name,
        v_before=v_before,
        v_after=v_after,
        omega_type=omega,
        author=author,
        iin=iin,
        reason=reason,
        branch_name=branch,
        parent_ids=parent_ids or [],
        committed_at=datetime.utcnow(),
    )
    db.add(delta)

    # Обновление текущего состояния документа
    fields = dict(doc.fields_json)
    fields[field_id] = v_after
    doc.fields_json = fields
    doc.version = _bump_version(doc.version, omega)
    doc.updated_at = datetime.utcnow()

    # Обновить указатель ветки
    br = db.query(Branch).filter(Branch.name == branch).first()
    if br:
        br.head_delta = full_sha
    else:
        db.add(Branch(name=branch, head_delta=full_sha))

    db.flush()

    publish_event(db, "DeltaCommitted", {
        "delta_id": full_sha,
        "doc_id": doc_id,
        "doc_type": doc.doc_type,
        "field": field_id,
        "omega": omega,
        "author": author,
    })

    return delta


def _bump_version(version: str, omega: str) -> str:
    """Ω₁–Ω₂ → patch, Ω₃–Ω₅ → minor, Ω₆–Ω₇ → major"""
    try:
        parts = version.split(".")
        major, minor, patch = int(parts[0]), int(parts[1] if len(parts) > 1 else 0), \
                               int(parts[2] if len(parts) > 2 else 0)
    except Exception:
        return version

    if omega in ("Ω₁", "Ω₂"):
        patch += 1
    elif omega in ("Ω₃", "Ω₄", "Ω₅"):
        minor += 1; patch = 0
    else:
        major += 1; minor = 0; patch = 0

    if major > 99 or minor > 99:
        return f"{major}.{minor}"
    return f"{major}.{minor}.{patch}" if patch else f"{major}.{minor}"


# ---------------------------------------------------------------------------
# Операция: checkout — восстановление состояния документа на момент времени
# ---------------------------------------------------------------------------

def checkout(db: Session, doc_id: str, timestamp: datetime) -> dict:
    """
    Восстанавливает состояние полей документа на указанный момент времени.

    Алгоритм (§4.2.3):
      1. Взять базовые поля при создании документа (до любых дельт).
      2. Выбрать все дельты doc_id с committed_at ≤ timestamp в хронол. порядке.
      3. Последовательно применить каждую: fields[field_id] = v_after.
      4. Вернуть итоговый словарь полей.

    Базовое состояние восстанавливается из текущих fields_json путём
    «обратного применения» всех дельт (от новейшей к старейшей).
    """
    doc = db.query(DocumentInstance).filter(DocumentInstance.id == doc_id).first()
    if not doc:
        return {"doc_id": doc_id, "at_timestamp": timestamp.isoformat(),
                "delta_count": 0, "fields": {}}

    # Все дельты документа в хронологическом порядке
    all_deltas = (
        db.query(Delta)
        .filter(Delta.doc_id == doc_id)
        .order_by(Delta.committed_at)
        .all()
    )

    # Шаг 1: восстановить «нулевое» (базовое) состояние документа до ПЕРВОЙ дельты.
    # Для каждого поля берём v_before самой ранней дельты, трогавшей это поле.
    # Поля, которые никогда не менялись — берём из текущего fields_json (они неизменны).
    changed_fields: set = {d.field_id for d in all_deltas}
    base: dict = {}

    # Неизменявшиеся поля: взять из текущего состояния (они одинаковы во всех точках времени)
    for fid, val in doc.fields_json.items():
        if fid not in changed_fields:
            base[fid] = val

    # Менявшиеся поля: v_before первой дельты = значение до начала истории изменений
    first_delta_for_field: dict = {}
    for d in all_deltas:  # уже отсортированы по времени
        if d.field_id not in first_delta_for_field:
            first_delta_for_field[d.field_id] = d

    for fid, d in first_delta_for_field.items():
        if d.v_before != "":   # пустая строка = поле не существовало до этой дельты
            base[fid] = d.v_before
        # else: поле добавлено этой дельтой — в базовом состоянии его нет

    # Шаг 2–3: прямое применение дельт до timestamp
    state = dict(base)
    applied = [d for d in all_deltas if d.committed_at <= timestamp]
    for d in applied:
        if d.v_after != "":
            state[d.field_id] = d.v_after
        else:
            state.pop(d.field_id, None)   # поле удалено (v_after = "")

    return {
        "doc_id": doc_id,
        "at_timestamp": timestamp.isoformat(),
        "delta_count": len(applied),
        "fields": state,
    }


# ---------------------------------------------------------------------------
# Операция: diff — все дельты документа за период
# ---------------------------------------------------------------------------

def diff(db: Session, doc_id: str,
         t1: Optional[datetime] = None,
         t2: Optional[datetime] = None) -> list:
    q = db.query(Delta).filter(Delta.doc_id == doc_id)
    if t1:
        q = q.filter(Delta.committed_at >= t1)
    if t2:
        q = q.filter(Delta.committed_at <= t2)
    return q.order_by(Delta.committed_at).all()


# ---------------------------------------------------------------------------
# Операция: blame — история конкретного поля
# ---------------------------------------------------------------------------

def blame(db: Session, doc_id: str, field_id: str) -> list:
    """
    Возвращает полную историю изменений конкретного поля документа.
    Аналог «git blame» — «кто и когда изменил это поле».
    """
    return (
        db.query(Delta)
        .filter(Delta.doc_id == doc_id, Delta.field_id == field_id)
        .order_by(Delta.committed_at)
        .all()
    )


# ---------------------------------------------------------------------------
# Операция: snapshot — полное состояние всех документов на момент времени
# ---------------------------------------------------------------------------

def snapshot(db: Session, timestamp: Optional[datetime] = None) -> dict:
    """Снимок состояния всего репозитория"""
    docs = db.query(DocumentInstance).all()
    result = {}
    for doc in docs:
        if timestamp:
            result[doc.id] = checkout(db, doc.id, timestamp)
        else:
            result[doc.id] = {"doc_id": doc.id, "fields": dict(doc.fields_json)}
    return result


# ---------------------------------------------------------------------------
# Операция: branch — создание ветки
# ---------------------------------------------------------------------------

def create_branch(db: Session, name: str, description: str = "",
                  base: str = "main") -> Branch:
    existing = db.query(Branch).filter(Branch.name == name).first()
    if existing:
        raise ValueError(f"Ветка «{name}» уже существует")

    base_br = db.query(Branch).filter(Branch.name == base).first()
    head = base_br.head_delta if base_br else None

    br = Branch(name=name, description=description,
                base_branch=base, head_delta=head)
    db.add(br)
    publish_event(db, "BranchCreated", {"branch": name, "base": base})
    return br


# ---------------------------------------------------------------------------
# Операция: merge — слияние веток с обнаружением конфликтов
# ---------------------------------------------------------------------------

def merge_branch(db: Session, source: str, target: str,
                 resolver: str = "") -> dict:
    """
    Трёхстороннее слияние веток.
    Конфликт = одно поле одного документа изменилось в обеих ветках.
    """
    src_br = db.query(Branch).filter(Branch.name == source).first()
    tgt_br = db.query(Branch).filter(Branch.name == target).first()
    if not src_br or not tgt_br:
        raise ValueError("Ветка не найдена")

    # Дельты ветки-источника
    src_deltas = db.query(Delta).filter(Delta.branch_name == source).all()

    # Дельты целевой ветки после общего предка
    tgt_deltas = db.query(Delta).filter(Delta.branch_name == target).all()

    src_changes = {(d.doc_id, d.field_id): d for d in src_deltas}
    tgt_changes = {(d.doc_id, d.field_id): d for d in tgt_deltas}

    conflicts = []
    merged = []

    for key, src_d in src_changes.items():
        if key in tgt_changes:
            tgt_d = tgt_changes[key]
            if src_d.v_after != tgt_d.v_after:
                # Конфликт
                cf = ConflictRecord(
                    doc_id=src_d.doc_id, field_id=src_d.field_id,
                    branch_a=source, branch_b=target,
                    value_base=src_d.v_before,
                    value_a=src_d.v_after,
                    value_b=tgt_d.v_after,
                )
                db.add(cf)
                conflicts.append({"doc_id": src_d.doc_id, "field": src_d.field_id,
                                   "value_a": src_d.v_after, "value_b": tgt_d.v_after})
                # Табл. 4.3: событие ConflictDetected при каждом конфликте
                publish_event(db, "ConflictDetected", {
                    "doc_id": src_d.doc_id,
                    "field_id": src_d.field_id,
                    "branch_a": source,
                    "branch_b": target,
                    "value_a": src_d.v_after,
                    "value_b": tgt_d.v_after,
                })
            else:
                merged.append(key)
        else:
            merged.append(key)

    applied_count = 0
    if not conflicts:
        # Применяем не-конфликтующие дельты source в target-ветку.
        # Создаём новую дельту в target для каждого изменения, которого там ещё нет.
        for (mdoc_id, mfield_id) in merged:
            src_d = src_changes[(mdoc_id, mfield_id)]
            if (mdoc_id, mfield_id) in tgt_changes:
                # Одинаковое значение в обеих ветках — уже слито, пропускаем
                continue

            tgt_doc = db.query(DocumentInstance).filter(
                DocumentInstance.id == mdoc_id
            ).first()
            if not tgt_doc:
                continue

            # Текущее значение поля в target-ветке
            curr_val = (tgt_doc.fields_json or {}).get(mfield_id, "")

            # Применяем только если target не имеет итогового значения из source
            if curr_val == src_d.v_after:
                applied_count += 1
                continue  # уже актуально

            # Создаём merge-дельту в target-ветке
            ts_now = datetime.utcnow().isoformat()
            merge_sha = compute_sha256(
                tgt_doc.doc_type, mdoc_id, mfield_id,
                curr_val, src_d.v_after, resolver or src_d.author, ts_now,
            )
            merge_delta = Delta(
                id=merge_sha,
                short_sha=merge_sha[:8],
                doc_id=mdoc_id,
                doc_type=tgt_doc.doc_type,
                field_id=mfield_id,
                field_name=src_d.field_name,
                v_before=curr_val,
                v_after=src_d.v_after,
                omega_type=src_d.omega_type,
                author=resolver or src_d.author,
                iin=src_d.iin,
                reason=f"Merge from '{source}': {src_d.reason or src_d.field_id}",
                branch_name=target,
                parent_ids=[src_d.id],
                committed_at=datetime.utcnow(),
            )
            db.add(merge_delta)

            # Обновляем поля целевого документа
            fields = dict(tgt_doc.fields_json or {})
            fields[mfield_id] = src_d.v_after
            tgt_doc.fields_json = fields
            tgt_doc.updated_at = datetime.utcnow()

            # Обновляем HEAD target-ветки
            tgt_br.head_delta = merge_sha
            applied_count += 1

        src_br.is_merged = True
        src_br.merged_at = datetime.utcnow()
        publish_event(db, "BranchMerged", {
            "source": source, "target": target, "applied": applied_count,
        })

    publish_event(db, "MergeAttempted", {
        "source": source, "target": target,
        "conflicts": len(conflicts), "merged": len(merged),
        "applied": applied_count,
    })

    return {
        "status": "conflict" if conflicts else "ok",
        "merged_fields": applied_count,
        "conflicts": conflicts,
    }

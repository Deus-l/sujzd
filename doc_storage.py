"""
СУЖЦД — Хранилище версий документов (аналог git object store)

Структура каталогов:
    prj_docs/
        {doc_id}/
            meta.json          — метаданные документа (все версии)
            v1.0.docx          — файл версии 1.0  (DOCX)
            v1.0.pdf           — файл версии 1.0  (PDF, если загружен как PDF)
            v1.0.xlsx          — файл версии 1.0  (XLSX, если загружен как XLSX)
            v1.1.docx          — файл версии 1.1
            ...
            HEAD               — текстовый файл: текущая версия

Каждый коммит дельты сохраняет новую версию файла.
Поддерживаемые форматы: .docx, .pdf, .xlsx
"""
import os
import json
import shutil
from datetime import datetime
from typing import Optional, List, Dict

# Корневой каталог хранилища версий
STORAGE_ROOT = os.path.join(os.path.dirname(__file__), "prj_docs")


def _doc_dir(doc_id: str) -> str:
    return os.path.join(STORAGE_ROOT, doc_id)


def _meta_path(doc_id: str) -> str:
    return os.path.join(_doc_dir(doc_id), "meta.json")


def _head_path(doc_id: str) -> str:
    return os.path.join(_doc_dir(doc_id), "HEAD")


def _version_filename(version: str, ext: str = ".docx") -> str:
    safe = version.replace("/", "_").replace("\\", "_")
    ext = ext.lower()
    if not ext.startswith("."):
        ext = "." + ext
    return f"v{safe}{ext}"


def _detect_version_file(doc_id: str, version: str) -> Optional[str]:
    """
    Ищет файл версии с любым поддерживаемым расширением.
    Приоритет: .docx → .pdf → .xlsx
    """
    d = _doc_dir(doc_id)
    for ext in (".docx", ".pdf", ".xlsx"):
        p = os.path.join(d, _version_filename(version, ext))
        if os.path.exists(p):
            return p
    return None


# ---------------------------------------------------------------------------
# Инициализация хранилища для документа
# ---------------------------------------------------------------------------

def init_doc_storage(doc_id: str, doc_name: str, doc_type: str,
                     version: str = "1.0") -> str:
    """
    Создаёт каталог хранилища для документа.
    Возвращает путь к каталогу.
    """
    d = _doc_dir(doc_id)
    os.makedirs(d, exist_ok=True)

    meta = {
        "doc_id": doc_id,
        "doc_name": doc_name,
        "doc_type": doc_type,
        "created_at": datetime.utcnow().isoformat(),
        "versions": [],
    }
    # Не перезаписываем если уже существует
    mp = _meta_path(doc_id)
    if not os.path.exists(mp):
        with open(mp, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    # HEAD
    hp = _head_path(doc_id)
    if not os.path.exists(hp):
        with open(hp, "w", encoding="utf-8") as f:
            f.write(version)

    return d


# ---------------------------------------------------------------------------
# Сохранение версии
# ---------------------------------------------------------------------------

def save_document_version(
    doc_id: str,
    doc_name: str,
    doc_type: str,
    version: str,
    docx_bytes: bytes,
    delta_id: Optional[str] = None,
    author: str = "",
    reason: str = "",
    committed_at: Optional[datetime] = None,
    file_ext: str = ".docx",
) -> str:
    """
    Сохраняет новую версию файла документа в хранилище.
    Поддерживаемые форматы: .docx (по умолчанию), .pdf, .xlsx
    Обновляет meta.json и HEAD.
    Возвращает путь к сохранённому файлу.
    """
    init_doc_storage(doc_id, doc_name, doc_type, version)
    d = _doc_dir(doc_id)
    fname = _version_filename(version, file_ext)
    fpath = os.path.join(d, fname)

    with open(fpath, "wb") as f:
        f.write(docx_bytes)

    # Обновить HEAD
    with open(_head_path(doc_id), "w", encoding="utf-8") as f:
        f.write(version)

    # Обновить meta.json
    meta = _read_meta(doc_id)
    ts = (committed_at or datetime.utcnow()).isoformat()

    # Не дублировать запись о той же версии
    existing = [v for v in meta.get("versions", []) if v["version"] == version]
    if existing:
        existing[0]["delta_id"] = delta_id
        existing[0]["committed_at"] = ts
        existing[0]["filename"] = fname  # обновляем имя файла если изменился формат
    else:
        meta.setdefault("versions", []).append({
            "version": version,
            "filename": fname,
            "format": file_ext.lstrip("."),
            "delta_id": delta_id,
            "author": author,
            "reason": reason,
            "committed_at": ts,
            "size_bytes": len(docx_bytes),
        })

    _write_meta(doc_id, meta)
    return fpath


def save_document_version_from_path(
    doc_id: str,
    doc_name: str,
    doc_type: str,
    version: str,
    source_path: str,
    delta_id: Optional[str] = None,
    author: str = "",
    reason: str = "",
    committed_at: Optional[datetime] = None,
) -> str:
    """
    Вариант: взять файл из source_path вместо передачи байтов.
    """
    with open(source_path, "rb") as f:
        data = f.read()
    return save_document_version(
        doc_id=doc_id, doc_name=doc_name, doc_type=doc_type,
        version=version, docx_bytes=data, delta_id=delta_id,
        author=author, reason=reason, committed_at=committed_at,
    )


# ---------------------------------------------------------------------------
# Чтение версий
# ---------------------------------------------------------------------------

def list_document_versions(doc_id: str) -> List[Dict]:
    """
    Возвращает список версий документа с метаданными.
    """
    if not os.path.exists(_meta_path(doc_id)):
        return []
    meta = _read_meta(doc_id)
    return sorted(meta.get("versions", []), key=lambda v: v.get("committed_at", ""))


def get_head_version(doc_id: str) -> Optional[str]:
    """Возвращает текущую (HEAD) версию документа."""
    hp = _head_path(doc_id)
    if not os.path.exists(hp):
        return None
    with open(hp, encoding="utf-8") as f:
        return f.read().strip()


def get_version_path(doc_id: str, version: Optional[str] = None) -> Optional[str]:
    """
    Возвращает полный путь к файлу версии.
    Если version=None — возвращает HEAD.
    Поддерживает .docx, .pdf, .xlsx (определяет автоматически).
    """
    if version is None:
        version = get_head_version(doc_id)
    if version is None:
        return None

    # Сначала ищем по записи в meta.json (точное имя файла)
    meta = _read_meta(doc_id)
    for v in meta.get("versions", []):
        if v.get("version") == version and v.get("filename"):
            p = os.path.join(_doc_dir(doc_id), v["filename"])
            if os.path.exists(p):
                return p

    # Fallback: перебираем расширения
    return _detect_version_file(doc_id, version)


def get_version_format(doc_id: str, version: Optional[str] = None) -> str:
    """Возвращает расширение файла версии (.docx, .pdf, .xlsx)."""
    p = get_version_path(doc_id, version)
    if p is None:
        return ".docx"
    return os.path.splitext(p)[1].lower() or ".docx"


def get_version_bytes(doc_id: str, version: Optional[str] = None) -> Optional[bytes]:
    """Возвращает содержимое файла версии."""
    p = get_version_path(doc_id, version)
    if p is None:
        return None
    with open(p, "rb") as f:
        return f.read()


def checkout_version(doc_id: str, version: str) -> bool:
    """
    Устанавливает версию как HEAD (git checkout tag).
    Возвращает True если версия существует.
    """
    p = get_version_path(doc_id, version)
    if p is None:
        return False
    with open(_head_path(doc_id), "w", encoding="utf-8") as f:
        f.write(version)
    return True


# ---------------------------------------------------------------------------
# Diff между версиями
# ---------------------------------------------------------------------------

def diff_versions(doc_id: str, version_a: str, version_b: str) -> Dict:
    """
    Текстовый diff полей между двумя версиями.
    Использует метаданные delta_id — читает поля из дельт БД через callback.
    Возвращает словарь {field_id: {before, after}}.
    """
    meta = _read_meta(doc_id)
    versions = {v["version"]: v for v in meta.get("versions", [])}
    va = versions.get(version_a)
    vb = versions.get(version_b)
    return {
        "doc_id": doc_id,
        "version_a": version_a,
        "version_b": version_b,
        "delta_a": va.get("delta_id") if va else None,
        "delta_b": vb.get("delta_id") if vb else None,
        "committed_a": va.get("committed_at") if va else None,
        "committed_b": vb.get("committed_at") if vb else None,
    }


def get_storage_stats(doc_id: str) -> Dict:
    """Статистика хранилища для документа."""
    d = _doc_dir(doc_id)
    if not os.path.exists(d):
        return {"doc_id": doc_id, "exists": False}
    versions = list_document_versions(doc_id)
    total_size = sum(v.get("size_bytes", 0) for v in versions)
    return {
        "doc_id": doc_id,
        "exists": True,
        "version_count": len(versions),
        "head": get_head_version(doc_id),
        "total_size_bytes": total_size,
        "storage_path": d,
    }


# ---------------------------------------------------------------------------
# Служебные
# ---------------------------------------------------------------------------

def _read_meta(doc_id: str) -> Dict:
    mp = _meta_path(doc_id)
    if not os.path.exists(mp):
        return {}
    with open(mp, encoding="utf-8") as f:
        return json.load(f)


def _write_meta(doc_id: str, meta: Dict):
    """
    Атомарная запись meta.json: пишем во временный файл, затем rename.
    На большинстве ОС os.replace() атомарна — предотвращает
    частичную запись при параллельных запросах.
    """
    mp = _meta_path(doc_id)
    tmp_path = mp + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, mp)


def delete_doc_storage(doc_id: str):
    """Удалить всё хранилище документа (при удалении документа из системы)."""
    d = _doc_dir(doc_id)
    if os.path.exists(d):
        shutil.rmtree(d)

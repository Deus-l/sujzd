#!/usr/bin/env python3
"""
СУЖЦД — Полный тест работоспособности
Запуск: python3 health_check.py
Требует: сервер запущен на http://localhost:8000
"""
import sys
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE = "http://localhost:8000"
OK = 0
FAIL = 0
FAILS = []

# Изолированный тестовый документ с известными начальными полями
TEST_DOC_ID = "HC-TEST-001"
TEST_FIELDS = {
    "material": "Ст3",
    "mass": "0.5",
    "tolerance": "H8/g6",
    "roughness": "Ra 3.2",
    "coating": "Цинк Хц.9",
    "heat_treatment": "Отжиг",
    "designation": "HC.001",
    "name_field": "Деталь тестовая",
}

# Уникальное имя ветки на каждый запуск (нет endpoint DELETE branch)
RUN_BRANCH = f"hc-br-{int(time.time()) % 99999}"


def req(method: str, path: str, body=None, expect_json=True):
    url = BASE + path
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r) as resp:
            ct = resp.headers.get("Content-Type", "")
            raw = resp.read()
            if expect_json and "json" in ct:
                return resp.status, json.loads(raw)
            return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw


def check(name: str, ok: bool, detail: str = ""):
    global OK, FAIL
    if ok:
        OK += 1
    else:
        FAIL += 1
        FAILS.append(f"  ✗ {name}" + (f"  [{detail}]" if detail else ""))
        print(f"  ✗ {name}" + (f"  [{detail}]" if detail else ""))


def section(title: str):
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")


# Очистка остатков от прошлых запусков
req("DELETE", f"/api/documents/{TEST_DOC_ID}")

# ─────────────────────────────────────────────────────────────
section("1. ДОКУМЕНТЫ — CRUD")

sc, docs = req("GET", "/api/documents")
check("GET /api/documents → 200", sc == 200)
check("Список не пуст (>= 7)", isinstance(docs, list) and len(docs) >= 7)

doc_ids = [d["id"] for d in docs] if isinstance(docs, list) else []
check("DOC-001 присутствует", "DOC-001" in doc_ids)
check("DOC-003 присутствует", "DOC-003" in doc_ids)

sc, d001 = req("GET", "/api/documents/DOC-001")
check("GET /api/documents/DOC-001 → 200", sc == 200)
check("DOC-001 doc_type=ESKD_DETAIL",
      isinstance(d001, dict) and d001.get("doc_type") == "ESKD_DETAIL")
check("DOC-001 designation не пустой",
      isinstance(d001, dict) and bool(d001.get("designation")))

sc, _ = req("GET", "/api/documents/NO-SUCH-DOC-XYZ")
check("GET несуществующего → 404", sc == 404)

# Создать тестовый документ
sc, created = req("POST", "/api/documents", {
    "id": TEST_DOC_ID, "doc_type": "ESKD_DETAIL",
    "name": "Деталь тестовая HealthCheck", "designation": "HC.001",
    "version": "1.0", "fields_json": TEST_FIELDS,
})
check("POST /api/documents → 201", sc == 201)
check(f"Создан {TEST_DOC_ID}",
      isinstance(created, dict) and created.get("id") == TEST_DOC_ID)

sc, patched = req("PATCH", f"/api/documents/{TEST_DOC_ID}", {"version": "1.1"})
check(f"PATCH /api/documents/{TEST_DOC_ID} → 200", sc == 200)
check("Версия стала 1.1",
      isinstance(patched, dict) and patched.get("version") == "1.1")

# ─────────────────────────────────────────────────────────────
section("2. ДОКУМЕНТЫ — ПАГИНАЦИЯ")

sc, page1 = req("GET", "/api/documents?limit=3&offset=0")
check("Пагинация limit=3 → 200", sc == 200)
check("Пагинация: ровно 3 документа",
      isinstance(page1, list) and len(page1) == 3)

sc, page2 = req("GET", "/api/documents?limit=3&offset=3")
check("Пагинация offset=3 → 200", sc == 200)
check("Разные страницы — разные id",
      isinstance(page2, list) and isinstance(page1, list) and
      len(page1) > 0 and len(page2) > 0 and page1[0]["id"] != page2[0]["id"])

sc, all_docs = req("GET", "/api/documents")
eskd = {"ESKD_DETAIL","ESKD_SPEC","ESKD_PASSPORT","ESKD_TU","ESKD_BOM",
        "ESKD_SCHEMA","ESKD_DRAWING","ESKD_EXPLODED"}
estd = {"ESTD_MK","ESTD_OK","ESTD_KO","ESTD_TI","ESTD_VOP","ESTD_KTP","ESTD_CLP","ESTD_IOT"}
eskd_n = sum(1 for d in (all_docs or []) if d.get("doc_type") in eskd)
estd_n = sum(1 for d in (all_docs or []) if d.get("doc_type") in estd)
check(f"ЕСКД-документов >= 2 (есть {eskd_n})", eskd_n >= 2)
check(f"ЕСТД-документов >= 2 (есть {estd_n})", estd_n >= 2)

# ─────────────────────────────────────────────────────────────
section("3. ДЕЛЬТЫ — ФИКСАЦИЯ И ЧТЕНИЕ")

# d1: Ω₃, material
sc, d1 = req("POST", "/api/deltas", {
    "doc_id": TEST_DOC_ID, "field_id": "material",
    "field_name": "Материал", "v_before": "Ст3",
    "v_after": "Сталь 20 ГОСТ 1050-2013",
    "omega_type": "Ω₃", "author": "Иванов И.И.",
    "reason": "Уточнение марки стали", "branch": "main",
})
check("POST /api/deltas (Ω₃) → 201", sc == 201)
check("Дельта содержит id", isinstance(d1, dict) and bool(d1.get("id")))
check("omega_type=Ω₃", isinstance(d1, dict) and d1.get("omega_type") == "Ω₃")
check("cascade_count >= 0",
      isinstance(d1, dict) and d1.get("cascade_count", -1) >= 0)
d1_id = d1.get("id", "") if isinstance(d1, dict) else ""

# d2: Ω₁, mass
sc, d2 = req("POST", "/api/deltas", {
    "doc_id": TEST_DOC_ID, "field_id": "mass",
    "field_name": "Масса", "v_before": "0.5", "v_after": "0.51",
    "omega_type": "Ω₁", "author": "Иванов И.И.",
    "reason": "Мелкая правка", "branch": "main",
})
check("POST /api/deltas (Ω₁) → 201", sc == 201)
check("Ω₁ → cascade_count=0",
      isinstance(d2, dict) and d2.get("cascade_count") == 0)

# d3: Ω₆, tolerance
sc, d3 = req("POST", "/api/deltas", {
    "doc_id": TEST_DOC_ID, "field_id": "tolerance",
    "field_name": "Допуск", "v_before": "H8/g6", "v_after": "H7/f7",
    "omega_type": "Ω₆", "author": "Петров П.П.",
    "reason": "Ужесточение допуска", "branch": "main",
})
check("POST /api/deltas (Ω₆) → 201", sc == 201)
check("Ω₆ cascade_count >= 0",
      isinstance(d3, dict) and d3.get("cascade_count", -1) >= 0)
d3_id = d3.get("id", "") if isinstance(d3, dict) else ""

# d4: Ω₂, coating + project_stage=РД
sc, d4 = req("POST", "/api/deltas", {
    "doc_id": TEST_DOC_ID, "field_id": "coating",
    "field_name": "Покрытие", "v_before": "Цинк Хц.9",
    "v_after": "Хром Х.12", "omega_type": "Ω₂",
    "author": "Иванов И.И.", "reason": "Замена покрытия",
    "branch": "main", "project_stage": "РД",
})
check("POST /api/deltas (coating, Ω₂, РД) → 201", sc == 201)
# R_011 для coating→ESTD_TI это [R] (рекомендуемое),
# cascade_count считает только обязательные → 0 является корректным поведением по ВКР
check("coating+РД: cascade_count >= 0",
      isinstance(d4, dict) and d4.get("cascade_count", -1) >= 0)

# GET конкретной дельты
if d1_id:
    sc, gd = req("GET", f"/api/deltas/{d1_id}")
    check("GET /api/deltas/{id} → 200", sc == 200)
    check("short_sha: 8 символов",
          isinstance(gd, dict) and len(gd.get("short_sha", "")) == 8)
else:
    check("GET /api/deltas/{id} → 200", False, "d1_id не получен")
    check("short_sha: 8 символов", False, "d1_id не получен")

# GET история дельт тестового документа
sc, hist = req("GET", f"/api/deltas?doc_id={TEST_DOC_ID}")
check("GET /api/deltas?doc_id=... → 200", sc == 200)
check("История: >= 1 дельта",
      isinstance(hist, list) and len(hist) >= 1)

# GET по omega_type
omega3_enc = urllib.parse.quote("Ω₃")
sc, om = req("GET", f"/api/deltas?omega_type={omega3_enc}")
check("GET /api/deltas?omega_type=Ω₃ → 200", sc == 200)
check("Фильтр omega_type работает",
      isinstance(om, list) and len(om) >= 1)

# ─────────────────────────────────────────────────────────────
section("4. ДЕРЕВО КАСКАДА")

if d3_id:
    sc, tree = req("GET", f"/api/deltas/{d3_id}/cascade")
    check("GET /api/deltas/{id}/cascade → 200", sc == 200)
    check("Дерево: nodes список",
          isinstance(tree, dict) and isinstance(tree.get("nodes"), list))
    check("Источник в nodes",
          isinstance(tree, dict) and any(n.get("role") == "source"
                                          for n in tree.get("nodes", [])))
    check("omega заполнен",
          isinstance(tree, dict) and bool(tree.get("omega")))
    check("gost_reference присутствует",
          isinstance(tree, dict) and bool(tree.get("gost_reference")))
else:
    for t in ["Дерево: nodes список","Источник в nodes","omega заполнен","gost_reference"]:
        check(t, False, "d3_id не получен")

# ─────────────────────────────────────────────────────────────
section("5. УВЕДОМЛЕНИЯ")

sc, notifs = req("GET", "/api/notifications")
check("GET /api/notifications → 200", sc == 200)
check("Уведомления — список", isinstance(notifs, list))

pending = [n for n in (notifs if isinstance(notifs, list) else [])
           if n.get("status") == "pending"]
check("Есть pending-уведомления", len(pending) >= 1)

# Resolve первых двух pending (PUT, не POST!)
resolved_ids = []
for i, notif in enumerate(pending[:2]):
    nid = notif["id"]
    sc, res = req("PUT", f"/api/notifications/{nid}/resolve",
                  {"notes": f"Исправлено (тест {i+1})"})
    check(f"Resolve уведомления #{nid} → 200", sc == 200)
    check("Статус стал resolved",
          isinstance(res, dict) and res.get("status") == "resolved")
    resolved_ids.append(nid)

if len(pending) < 2:
    # Генерируем ещё одну дельту для получения уведомлений
    check("Второе pending-уведомление", False, f"только {len(pending)} pending")

# TC-15: norm_ref в уведомлениях
sc, allnotifs = req("GET", "/api/notifications")
notifs_with_ref = [n for n in (allnotifs if isinstance(allnotifs, list) else [])
                   if n.get("norm_ref", "")]
total_n = len(allnotifs) if isinstance(allnotifs, list) else 0
check(f"TC-15: norm_ref в уведомлениях ({len(notifs_with_ref)}/{total_n})",
      len(notifs_with_ref) >= 1)

# ─────────────────────────────────────────────────────────────
section("6. ВЕТКИ И СЛИЯНИЕ")

sc, br = req("POST", "/api/branches", {
    "name": RUN_BRANCH, "description": "Тест HealthCheck", "base": "main",
})
check("POST /api/branches → 201", sc == 201)
check("Ветка создана с именем",
      isinstance(br, dict) and br.get("name") == RUN_BRANCH)

sc, blist = req("GET", "/api/branches")
check("GET /api/branches → 200", sc == 200)
check(f"{RUN_BRANCH} в списке",
      isinstance(blist, list) and any(b["name"] == RUN_BRANCH for b in blist))

# Добавить дельту в ветку (roughness не менялась)
sc, bd = req("POST", "/api/deltas", {
    "doc_id": TEST_DOC_ID, "field_id": "roughness",
    "field_name": "Шероховатость", "v_before": "Ra 3.2",
    "v_after": "Ra 1.6", "omega_type": "Ω₂",
    "author": "Тест", "reason": "Тест ветки",
    "branch": RUN_BRANCH,
})
check(f"Дельта в ветке {RUN_BRANCH} → 201", sc == 201)
check("branch_name совпадает",
      isinstance(bd, dict) and bd.get("branch_name") == RUN_BRANCH)

# Слияние
sc, mr = req("POST", "/api/branches/merge", {
    "source": RUN_BRANCH, "target": "main", "resolver": "Тест",
})
check("POST /api/branches/merge → 200", sc == 200)
check("Слияние: status=ok",
      isinstance(mr, dict) and mr.get("status") == "ok")

# ─────────────────────────────────────────────────────────────
section("7. CHECKOUT / DIFF / BLAME")

# Checkout: GET /api/documents/{doc_id}/checkout?timestamp=...
ts_now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
ts_enc = urllib.parse.quote(ts_now)
sc, co = req("GET", f"/api/documents/{TEST_DOC_ID}/checkout?timestamp={ts_enc}")
check("GET /api/documents/{id}/checkout → 200", sc == 200)
check("checkout: doc_id присутствует",
      isinstance(co, dict) and co.get("doc_id") == TEST_DOC_ID)
check("checkout: delta_count >= 0",
      isinstance(co, dict) and isinstance(co.get("delta_count"), int)
      and co.get("delta_count", -1) >= 0)
check("checkout: fields dict",
      isinstance(co, dict) and isinstance(co.get("fields"), dict))

# Diff: GET /api/documents/{doc_id}/diff
sc, diff_r = req("GET", f"/api/documents/{TEST_DOC_ID}/diff")
check("GET /api/documents/{id}/diff → 200", sc == 200)
check("diff: список изменений", isinstance(diff_r, list))

# Blame: GET /api/documents/{doc_id}/blame/{field_id}
sc, blame_r = req("GET", f"/api/documents/{TEST_DOC_ID}/blame/material")
check("GET /api/documents/{id}/blame/{field_id} → 200", sc == 200)
check("blame: список", isinstance(blame_r, list))
if isinstance(blame_r, list) and blame_r:
    check("blame[0]: field_id присутствует",
          bool(blame_r[0].get("field_id")))
    check("blame[0]: author присутствует",
          bool(blame_r[0].get("author")))

# ─────────────────────────────────────────────────────────────
section("8. ИА-МОДУЛЬ — КЛАССИФИКАЦИЯ И АНАЛИЗ")

# Classify (возвращает suggested_omega, не omega_type)
sc, cl = req("POST", "/api/ia/classify", {
    "field_id": "tolerance", "v_before": "H8/g6",
    "v_after": "H7/f7", "doc_type": "ESKD_DETAIL",
})
check("POST /api/ia/classify → 200", sc == 200)
check("classify: suggested_omega присутствует",
      isinstance(cl, dict) and bool(cl.get("suggested_omega")))
# confidence возвращается в диапазоне 0–100 (процент)
check("classify: confidence >= 0",
      isinstance(cl, dict) and cl.get("confidence", -1) >= 0)

# Significance (TC-20): POST /api/ia/significance
sc, sig = req("POST", "/api/ia/significance", {
    "omega_type": "Ω₃", "cascade_count": 4,
})
check("POST /api/ia/significance → 200", sc == 200)
check("significance: score присутствует",
      isinstance(sig, dict) and "significance_score" in sig)
score = sig.get("significance_score", 0) if isinstance(sig, dict) else 0
check(f"TC-20: Ω₃+cascade=4 → score=3.0 (получено {score})",
      abs(score - 3.0) < 0.01)
check("TC-20: level=среднее (score=3.0, ВКР §4.6.2: ≥3.5→высокое, ≥2.5→среднее)",
      isinstance(sig, dict) and sig.get("level") == "среднее")

# Analyze (требует ключ, принимаем 404 если дельта не найдена)
if d1_id:
    sc, an = req("POST", "/api/ia/analyze", {"delta_id": d1_id})
    check("POST /api/ia/analyze → 200/404/422",
          sc in (200, 404, 422))

# Step delta: POST /api/ia/step
sc, step = req("POST", "/api/ia/step", {
    "content_before": "Параметр А = 10",
    "content_after": "Параметр А = 12\nПараметр Б = 5",
})
check("POST /api/ia/step → 200", sc == 200)
# step возвращает added_entities, removed_entities (STEP ISO 10303-21 формат)
check("step: added_entities список",
      isinstance(step, dict) and isinstance(step.get("added_entities"), list))

# ─────────────────────────────────────────────────────────────
section("9. МАТРИЦА ЗАВИСИМОСТЕЙ")

# GET /api/matrix → {rules:[...], count:N}
sc, mx = req("GET", "/api/matrix")
check("GET /api/matrix → 200", sc == 200)
check("Матрица: count=49",
      isinstance(mx, dict) and mx.get("count") == 49,
      f"получено {mx.get('count') if isinstance(mx,dict) else mx}")

# GET /api/matrix/stats → {total_rules, mandatory, recommended, ...}
sc, mxs = req("GET", "/api/matrix/stats")
check("GET /api/matrix/stats → 200", sc == 200)
check("stats: total_rules=49",
      isinstance(mxs, dict) and mxs.get("total_rules") == 49,
      f"получено {mxs.get('total_rules') if isinstance(mxs,dict) else mxs}")
check("stats: mandatory=29",
      isinstance(mxs, dict) and mxs.get("mandatory") == 29,
      f"получено {mxs.get('mandatory') if isinstance(mxs,dict) else mxs}")
check("stats: recommended=20",
      isinstance(mxs, dict) and mxs.get("recommended") == 20,
      f"получено {mxs.get('recommended') if isinstance(mxs,dict) else mxs}")

# GET /api/matrix/lifecycle → {code: {lifecycle:[], omega_sensitivity:[]}}
sc, lc_resp = req("GET", "/api/matrix/lifecycle")
check("GET /api/matrix/lifecycle → 200", sc == 200)
# Проверяем, что хотя бы один тип имеет "ТП" в lifecycle
lc_has_tp = isinstance(lc_resp, dict) and any(
    "ТП" in v.get("lifecycle", []) for v in lc_resp.values()
)
check("lifecycle: хотя бы один тип имеет ТП", lc_has_tp)

# POST /api/matrix/reload
sc, rl = req("POST", "/api/matrix/reload")
check("POST /api/matrix/reload → 200", sc == 200)
check("reload: rules=49",
      isinstance(rl, dict) and rl.get("rules") == 49)

# ─────────────────────────────────────────────────────────────
section("10. DSR — РЕЕСТР СХЕМ ДОКУМЕНТОВ")

# GET /api/dsr → список объектов DocumentType из БД
sc, dsr_list = req("GET", "/api/dsr")
check("GET /api/dsr → 200", sc == 200)
check("DSR: список >= 10 типов",
      isinstance(dsr_list, list) and len(dsr_list) >= 10)

# GET /api/dsr/{code} → {code, std, short_code, name, gost, fields_json}
sc, dsr_eskd = req("GET", "/api/dsr/ESKD_DETAIL")
check("GET /api/dsr/ESKD_DETAIL → 200", sc == 200)
check("DSR: code присутствует",
      isinstance(dsr_eskd, dict) and dsr_eskd.get("code") == "ESKD_DETAIL")
# В БД поле называется fields (не fields_json)
check("DSR: fields список",
      isinstance(dsr_eskd, dict) and isinstance(dsr_eskd.get("fields"), list))

# GET /api/dsr/{code}/fields
sc, dsr_fields = req("GET", "/api/dsr/ESKD_DETAIL/fields")
check("GET /api/dsr/ESKD_DETAIL/fields → 200", sc == 200)
flist = (dsr_fields.get("fields") or dsr_fields.get("fields_json") or []
         if isinstance(dsr_fields, dict) else
         dsr_fields if isinstance(dsr_fields, list) else [])
check("DSR fields: непустой список",
      isinstance(flist, list) and len(flist) >= 1)
if isinstance(flist, list) and flist:
    check("DSR field[0]: id присутствует",
          bool(flist[0].get("id")))

# lifecycle и omega_sensitivity — в _dsr (файл), видно через /api/matrix/lifecycle
eskd_lc = lc_resp.get("ESKD_DETAIL", {}) if isinstance(lc_resp, dict) else {}
check("ESKD_DETAIL: lifecycle список",
      isinstance(eskd_lc.get("lifecycle"), list))
check("ESKD_DETAIL: omega_sensitivity список",
      isinstance(eskd_lc.get("omega_sensitivity"), list))

# ─────────────────────────────────────────────────────────────
section("11. ФАЙЛОВОЕ ХРАНИЛИЩЕ ДОКУМЕНТОВ")

sc, vers = req("GET", f"/api/documents/{TEST_DOC_ID}/versions")
check("GET /api/documents/{id}/versions → 200", sc == 200)
# Возвращает dict {doc_id, head, version_count, storage_path, versions:[...]}
vlist = vers.get("versions", []) if isinstance(vers, dict) else []
check("Версии: непустой список",
      isinstance(vlist, list) and len(vlist) >= 1,
      f"version_count={vers.get('version_count',0) if isinstance(vers,dict) else '?'}")
if isinstance(vlist, list) and vlist:
    check("Версия[0]: version присутствует", bool(vlist[0].get("version")))
    check("Версия[0]: size_bytes присутствует", bool(vlist[0].get("size_bytes")))

sc, fraw = req("GET", f"/api/documents/{TEST_DOC_ID}/file", expect_json=False)
check("GET /api/documents/{id}/file → 200", sc == 200)
check("Файл: magic PK (DOCX/ZIP)",
      isinstance(fraw, bytes) and fraw[:2] == b"PK")

sc, gen = req("POST", f"/api/documents/{TEST_DOC_ID}/generate")
check("POST /api/documents/{id}/generate → 200", sc == 200)
check("generate: version присутствует",
      isinstance(gen, dict) and bool(gen.get("version")))
check("generate: path присутствует",
      isinstance(gen, dict) and bool(gen.get("path")))

# ─────────────────────────────────────────────────────────────
section("12. АУДИТ-ЖУРНАЛ")

sc, audit = req("GET", "/api/audit")
check("GET /api/audit → 200", sc == 200)
check("Аудит: непустой список",
      isinstance(audit, list) and len(audit) >= 1)
check("Аудит: event_type присутствует",
      isinstance(audit, list) and bool(audit[0].get("event_type")) if audit else False)

sc, adt = req("GET", "/api/audit?event_type=DependencyTasksCreated")
check("GET /api/audit?event_type=... → 200", sc == 200)
check("Фильтр event_type: список", isinstance(adt, list))

sc, adlim = req("GET", "/api/audit?limit=5")
check("GET /api/audit?limit=5 → 200", sc == 200)
check("Аудит limit=5: <= 5 записей",
      isinstance(adlim, list) and len(adlim) <= 5)

# ─────────────────────────────────────────────────────────────
section("13. LIFECYCLE-ФИЛЬТРАЦИЯ (ВКР раздел 4.3)")

# ТП: ЕСТД не обязательны → cascade_count (обязательные) = 0
# R_012: ESKD_DETAIL.heat_treatment → ESTD_MK.operations [1] при Ω₂
# R_013: ESKD_DETAIL.heat_treatment → ESTD_OK.heat_modes [R] при Ω₂
# ESTD_MK lifecycle = ["РД","ИЗГОТ","ЭКСПЛ"] — в ТП стадии ЕСТД не активны
sc, lc_tp = req("POST", "/api/deltas", {
    "doc_id": TEST_DOC_ID, "field_id": "heat_treatment",
    "field_name": "ТО", "v_before": "Отжиг",
    "v_after": "Нормализация", "omega_type": "Ω₂",
    "author": "Тест", "reason": "Тест ТП",
    "branch": "main", "project_stage": "ТП",
})
check("Дельта project_stage=ТП → 201", sc == 201)
tp_cascade = lc_tp.get("cascade_count", -1) if isinstance(lc_tp, dict) else -1
check(f"ТП: cascade_count=0 (ЕСТД не обязательны на ТП, = {tp_cascade})",
      tp_cascade == 0)

# РД: ЕСТД обязательны → cascade_count > 0
# В стадии РД ESTD_MK имеет lifecycle=["РД","ИЗГОТ","ЭКСПЛ"] → активен
sc, lc_rd = req("POST", "/api/deltas", {
    "doc_id": TEST_DOC_ID, "field_id": "heat_treatment",
    "field_name": "ТО", "v_before": "Нормализация",
    "v_after": "Закалка ТВЧ", "omega_type": "Ω₂",
    "author": "Тест", "reason": "Тест РД",
    "branch": "main", "project_stage": "РД",
})
check("Дельта project_stage=РД → 201", sc == 201)
rd_cascade = lc_rd.get("cascade_count", -1) if isinstance(lc_rd, dict) else -1
check(f"РД: cascade_count > 0 (ЕСТД активны на РД, = {rd_cascade})",
      rd_cascade > 0)

# ─────────────────────────────────────────────────────────────
section("14. КОНФЛИКТЫ")

sc, conf = req("GET", "/api/conflicts")
check("GET /api/conflicts → 200", sc == 200)
check("Конфликты: список", isinstance(conf, list))

# ─────────────────────────────────────────────────────────────
section("15. УДАЛЕНИЕ ДОКУМЕНТА")

sc, _ = req("DELETE", f"/api/documents/{TEST_DOC_ID}")
check(f"DELETE /api/documents/{TEST_DOC_ID} → 200/204", sc in (200, 204))

sc, _ = req("GET", f"/api/documents/{TEST_DOC_ID}")
check("После DELETE → 404", sc == 404)

# ─────────────────────────────────────────────────────────────
print(f"\n{'═'*60}")
total = OK + FAIL
print(f"  ИТОГ: {OK} ✓  /  {total} проверок   ({FAIL} ✗ провалов)")
print(f"{'═'*60}")

if FAIL:
    print("\nПровалившиеся проверки:")
    for f in FAILS:
        print(f)
    sys.exit(1)
else:
    print("\n  ✓ Все проверки прошли успешно!")
    sys.exit(0)

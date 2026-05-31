"""
СУЖЦД — Модуль интеллектуального анализа дельт (IA Module)
Задачи:
1. Автоматическая классификация типа Ω входящей дельты
2. Оценка семантической существенности изменения
3. AI-анализ через Claude API
"""
import re
import os
import json
import httpx
from typing import Optional, Dict, List


# ---------------------------------------------------------------------------
# 1. Детерминированный классификатор Ω (на основе ключевых признаков из диплома)
# ---------------------------------------------------------------------------

OMEGA_FEATURES = {
    # Ω₁ — редакционные правки, не влияющие на содержание
    "Ω₁": {
        "keywords": [
            "опечатка", "опечатки", "переоформление", "редакция", "актуализация",
            "исправление опечатки", "обновление номера", "переиздание", "форматирование",
            "орфографическая", "пунктуация", "штамп", "оформление", "шрифт",
            "нумерация страниц", "заголовок", "колонтитул", "стиль оформления",
        ],
        "patterns": [
            r"гост\s+\d+[\.\d–\-]+\d{2,4}\s+→\s+гост",
            r"изм\.?\s+№\s*\d+\s+к\s+гост",
        ],
    },
    # Ω₂ — изменение параметра компонента (материал, допуск, режим и т.д.)
    "Ω₂": {
        "keywords": [
            "допуск", "посадка", "размер", "материал", "марка материала", "шероховатость",
            "покрытие", "масса", "режим резания", "скорость резания", "подача", "глубина резания",
            "норма времени", "параметр", "температура", "давление", "напряжение питания",
            "ток потребления", "мощность", "твёрдость", "термообработка", "отклонение",
            "точность обработки", "квалитет", "шаг резьбы", "угол", "радиус",
            "напряжение", "частота", "ёмкость", "индуктивность", "сопротивление",
            "ra", "rz", "rmax", "нормализация", "закалка", "отпуск", "цементация",
            "модификация", "исполнение", "типоразмер", "модель",
        ],
        "patterns": [
            r"[-+]?\d+[\.,]\d+\s*(?:мм|мкм|кг|н·м|мпа|вт|а|в|об/мин|м/с|°с|гц|мгц)",
            r"[Hh]\d+/[a-zA-Zgjhkmnps]\d+",
            r"[Rr][aAzZ]\s*\d+[\.,]?\d*",
            r"±\s*\d+[\.,]?\d*",
            r"\d+\s*квалитет",
            r"[Gg]\d+\s*/\s*[hH]\d+",
            # Смена обозначения/модели: буквы (1–4) + ОБЯЗАТЕЛЬНЫЙ ДЕФИС + цифры
            # (Д-47М → Д-48М, ВД-12А → ВД-14А, AM-25 → AM-26).
            # Намеренно НЕ совпадает с позиционными обозначениями Q5, BD139, R1, C2
            # (у них нет дефиса между буквой и цифрой) → те корректно идут в Ω₃
            r"[А-ЯA-Z]{1,4}-\d+[А-ЯA-Z]{0,2}\d*",
        ],
    },
    # Ω₃ — изменение состава (добавление/удаление/замена позиции, операции)
    "Ω₃": {
        "keywords": [
            "добавить позицию", "добавлена позиция", "исключить позицию", "исключена позиция",
            "замена позиции", "заменена позиция", "новый компонент", "замена компонента",
            "новая операция", "добавлена операция", "исключена операция", "введена операция",
            "новая функция", "добавить модуль", "замена модуля", "ввести в спецификацию",
            "исключить из спецификации", "состав изменён", "спецификация", "комплектность",
            "замена транзистора", "замена резистора", "замена конденсатора", "замена микросхемы",
            "позиция добавлена", "позиция исключена", "добавлен", "исключён", "заменён",
        ],
        "patterns": [
            r"поз\.?\s*\d+\s*(?:добавл|исключ|замен)",
            r"(?:добавл|исключ|замен)\w*\s+\d+\s+поз",
            r"[QRCTLVZ]\d{1,4}\s*(?:заменён|замен|исключ|добавл)",
            r"(?:ввест[иь]|исключит[ьь])\s+(?:в|из)\s+состав",
        ],
    },
    # Ω₄ — комплексный показатель (масса изделия, MTBF, КПД, производительность)
    "Ω₄": {
        "keywords": [
            "масса изделия", "суммарная масса", "общая мощность", "ресурс", "срок службы",
            "надёжность", "mtbf", "наработка на отказ", "кпд", "производительность",
            "пропускная способность", "быстродействие", "трудоёмкость суммарная",
            "нормо-час", "общее потребление", "суммарное", "комплексный показатель",
            "технические характеристики изделия", "характеристики системы",
        ],
        "patterns": [
            r"mtbf\s*[≥>]\s*\d+",
            r"кпд\s*=\s*\d+",
            r"наработка\s*[≥>]\s*\d+\s*(?:ч|лет|год)",
            r"вероятность безотказной\s+\d+[\.,]\d+",
        ],
    },
    # Ω₅ — изменение технологического процесса (оборудование, метод обработки)
    "Ω₅": {
        "keywords": [
            "новое оборудование", "замена станка", "замена оборудования", "изменить метод",
            "новый метод обработки", "изменение технологии", "новый алгоритм обработки",
            "метод обработки изменён", "технологический процесс изменён", "новая оснастка",
            "перенастройка", "новый инструмент", "замена инструмента", "метод контроля изменён",
            "маршрут изменён", "последовательность операций", "новая технологическая операция",
        ],
        "patterns": [
            r"(?:заменить|заменён)\s+(?:станок|оборудование|инструмент)",
            r"(?:новый|изменён)\s+(?:маршрут|технологический процесс)",
            r"\d{3}\s+(?:токарная|фрезерная|шлифовальная|сверлильная)\s+(?:исключена|добавлена)",
        ],
    },
    # Ω₆ — нормативное основание (обновление/замена ГОСТ, ТУ, ОСТ)
    "Ω₆": {
        "keywords": [
            "гост обновлён", "гост заменён", "гост введён", "гост отменён",
            "новая редакция гост", "актуализация ссылки", "заменён стандарт",
            "введён стандарт", "отменён стандарт", "изменение нормативной ссылки",
            "ту изменены", "ост заменён", "нормативный документ",
        ],
        "patterns": [
            r"гост\s+р?\s*\d+[\.\d–\-]+\d{2,4}\s+(?:обновлён|заменён|введён|изменён|отменён)",
            r"гост\s+р?\s*\d+\.?\d*[–\-]\d{4}\s*→\s*гост",
            r"взамен\s+гост",
        ],
    },
    # Ω₇ — инновационное изменение (принципиально новое решение)
    "Ω₇": {
        "keywords": [
            "принципиально новая", "принципиально новое", "принципиально иной",
            "новая архитектура", "коренная переработка", "новая концепция", "патент",
            "изобретение", "инновационное", "радикально новый", "принципиальное изменение",
            "новый принцип работы", "новая схемотехника", "новый алгоритм управления",
        ],
        "patterns": [
            r"(?:принципиально|коренн)\w+\s+(?:нов|перераб)",
            r"патент\s+(?:на|№)",
        ],
    },
}


# ---------------------------------------------------------------------------
# Вспомогательные данные для classify_omega
# ---------------------------------------------------------------------------

# Маппинг английских field_id → русские ключевые слова для обогащения combined-строки.
# Решает проблему: field_id="material" не совпадал с keyword "материал".
_EN_RU_FIELD: Dict[str, str] = {
    "material":          "материал марка материала",
    "tolerance":         "допуск посадка квалитет",
    "roughness":         "шероховатость",
    "coating":           "покрытие",
    "heat_treatment":    "термообработка закалка нормализация",
    "mass":              "масса",
    "composition":       "состав комплектность спецификация",
    "bought_parts":      "покупные изделия состав",
    "elements":          "перечень элементов состав",
    "operations":        "операции маршрут",
    "purpose":           "назначение область применения",
    "name_field":        "наименование",
    "designation":       "обозначение",
    "tech_req":          "технические требования",
    "tech_chars":        "технические характеристики",
    "cutting_modes":     "режимы резания",
    "norm_time":         "норма времени",
    "equipment":         "оборудование",
    "tool":              "инструмент",
    "fixture":           "приспособление",
    "func_requirements": "функциональные требования",
    "reliability_req":   "надёжность",
    "conditions":        "условия эксплуатации",
    "guarantee":         "гарантийный срок",
    "gost_ref":          "гост нормативный",
    "norm_ref":          "нормативный документ",
    "standard":          "стандарт гост",
    "marking":           "маркировка обозначение",
    "delivery_set":      "комплект поставки",
    "product_name":      "наименование изделия",
    "kd_designation":    "обозначение кд",
    "blank_mass":        "масса заготовки",
    "material_rate":     "норма расхода",
    "op_code":           "код операции номер операции",
    "op_name":           "наименование операции",
    "assembly_dims":     "сборочные размеры",
    "control_methods":   "методы контроля",
    "control_ops":       "операции контроля",
    "control_tools":     "средства измерений",
    "tech_requirements": "технические требования",
    "heat_modes":        "режимы термообработки",
    "finishing_method":  "финишная обработка шлифование",
}

# Поля, связанные со «составом» изделия (для fast-path Ω₃)
_COMPOSITION_FIELDS_FP = frozenset({
    "composition", "bought_parts", "elements", "состав",
    "комплектность", "комплект", "перечень", "quantity",
})

# Паттерн: «замена Q5», «замена VD3», «замена BD139» и т.п.
_COMP_REPL_RE = re.compile(
    r"замен[аеуыьить]+\s+[A-Za-zА-ЯА-яёЁ]{1,5}\d",
    re.IGNORECASE,
)


def _kw_match(kw: str, text: str) -> bool:
    """
    Безопасная проверка вхождения ключевого слова.
    Для коротких слов (≤4 символа) требует границу слова, чтобы избежать
    ложных срабатываний типа «ra» внутри «tolerance».
    Граница: символ не является буквой (рус/лат) или цифрой.
    """
    if len(kw) <= 4:
        return bool(re.search(
            r"(?<![а-яёa-zA-Z0-9])" + re.escape(kw) + r"(?![а-яёa-zA-Z0-9])",
            text, re.IGNORECASE,
        ))
    return kw in text


def classify_omega(field_id: str, v_before: str, v_after: str,
                   doc_type: str = "") -> dict:
    """
    Детерминированная классификация типа Ω.
    Возвращает тип и вероятность по каждой категории.
    """
    v_before_s = (v_before or "").strip()
    v_after_s  = (v_after  or "").strip()

    # ── Быстрые детерминированные правила (приоритет над score-based) ───────
    # 1. Нет изменений вообще → Ω₁
    if not v_before_s and not v_after_s:
        scores_empty = {o: {"score": 0, "keywords": [], "patterns": []} for o in OMEGA_FEATURES}
        scores_empty["Ω₁"]["score"] = 10
        return {
            "suggested_omega": "Ω₁",
            "confidence": 100.0,
            "scores": {k: v["score"] for k, v in scores_empty.items()},
            "matched_keywords": ["пустые значения — редакционная"],
        }

    # 2. Поле-обозначение / нормативный реквизит → Ω₆
    _NORMATIVE_FIELDS = {"designation", "oboznachenie", "gost_ref", "norm_ref",
                         "standard", "marking", "cipher", "gost"}
    if field_id.lower() in _NORMATIVE_FIELDS:
        scores_norm = {o: {"score": 0, "keywords": [], "patterns": []} for o in OMEGA_FEATURES}
        scores_norm["Ω₆"]["score"] = 10
        return {
            "suggested_omega": "Ω₆",
            "confidence": 100.0,
            "scores": {k: v["score"] for k, v in scores_norm.items()},
            "matched_keywords": [f"поле '{field_id}' — нормативный реквизит"],
        }

    # 3. Поле «вводится впервые» (v_before пустое) для технологических процессов → Ω₃
    _PROCESS_FIELDS = {"heat_treatment", "coating", "operations", "process",
                       "method", "stages", "tech_process", "route"}
    _EMPTY_VALUES   = {"", "нет", "—", "-", "не предусмотрено", "отсутствует"}
    if (field_id.lower() in _PROCESS_FIELDS
            and v_before_s.lower() in _EMPTY_VALUES
            and v_after_s
            and v_after_s.lower() not in _EMPTY_VALUES):
        scores_proc = {o: {"score": 0, "keywords": [], "patterns": []} for o in OMEGA_FEATURES}
        scores_proc["Ω₃"]["score"] = 10
        return {
            "suggested_omega": "Ω₃",
            "confidence": 100.0,
            "scores": {k: v["score"] for k, v in scores_proc.items()},
            "matched_keywords": [f"поле '{field_id}' вводится впервые — добавление процесса"],
        }

    # 4. Поле «состав» + признак замены позиционного компонента → Ω₃
    #    Пример: замена Q5→BD139, замена VD3→1N4007 (позиционные обозначения по ГОСТ 2.710)
    if (field_id.lower() in _COMPOSITION_FIELDS_FP
            and _COMP_REPL_RE.search(f"{v_before_s} {v_after_s}")):
        scores_comp = {o: {"score": 0, "keywords": [], "patterns": []} for o in OMEGA_FEATURES}
        scores_comp["Ω₃"]["score"] = 10
        return {
            "suggested_omega": "Ω₃",
            "confidence": 100.0,
            "scores": {k: v["score"] for k, v in scores_comp.items()},
            "matched_keywords": [f"поле '{field_id}' + замена позиционного компонента → Ω₃"],
        }

    # ── Балльная классификация по ключевым словам и паттернам ───────────────
    # Обогащаем поисковую строку русским переводом field_id (если поле на английском)
    _field_ru = _EN_RU_FIELD.get(field_id.lower(), "")
    combined = f"{field_id} {_field_ru} {v_before_s} {v_after_s}".lower()
    scores = {}

    for omega, cfg in OMEGA_FEATURES.items():
        score = 0
        matched_kw = []
        matched_pat = []

        for kw in cfg["keywords"]:
            if _kw_match(kw, combined):
                score += 1
                matched_kw.append(kw)

        for pat in cfg["patterns"]:
            if re.search(pat, combined, re.IGNORECASE):
                score += 2
                matched_pat.append(pat)

        scores[omega] = {"score": score, "keywords": matched_kw, "patterns": matched_pat}

    # Нормализация
    max_score = max((v["score"] for v in scores.values()), default=0)
    best = "Ω₂"  # по умолчанию при равенстве
    best_score = -1

    for omega, data in scores.items():
        if data["score"] > best_score:
            best_score = data["score"]
            best = omega

    # Если ничего не нашли — Ω₂ (самый частый в инженерной документации)
    if best_score == 0:
        best = "Ω₂"

    confidence = round(min(best_score / max(max_score, 1), 1.0) * 100, 1)

    return {
        "suggested_omega": best,
        "confidence": confidence,
        "scores": {k: v["score"] for k, v in scores.items()},
        "matched_keywords": scores[best]["keywords"],
    }


# ---------------------------------------------------------------------------
# 2. Оценка существенности изменения
# ---------------------------------------------------------------------------

SIGNIFICANCE_MAP = {
    # Базовые баллы по раздел 4.6.2
    "Ω₁": 0, "Ω₂": 1, "Ω₃": 2, "Ω₄": 2, "Ω₅": 2, "Ω₆": 3, "Ω₇": 4,
}

def estimate_significance(omega: str, cascade_count: int) -> dict:
    """
    significance = base_score[Ω] + min(1.0, cascade_count / 3)
    Пороги: ≥3.5 → критическое, ≥2.5 → высокое, ≥1.5 → среднее, <1.5 → низкое
    (раздел 4.6.2)
    """
    base = SIGNIFICANCE_MAP.get(omega, 2)
    total = round(base + min(1.0, cascade_count / 3), 1)
    # Пороги по §4.6.2: ≥4.5 критическое, ≥3.5 высокое, ≥2.5 среднее, <2.5 низкое
    return {
        "significance_score": total,
        "level": "критическое" if total >= 4.5 else
                 "высокое"     if total >= 3.5 else
                 "среднее"     if total >= 2.5 else
                 "низкое",
        "requires_immediate_action": total >= 4.5,
    }


# ---------------------------------------------------------------------------
# 3. AI-анализ через Anthropic Claude API
# ---------------------------------------------------------------------------

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL   = "claude-sonnet-4-20250514"

# Hugging Face Inference API (новый роутер, OpenAI-совместимый формат)
# Документация: https://huggingface.co/docs/api-inference/
HF_ROUTER_BASE = "https://router.huggingface.co"
HF_MODEL       = "Qwen/Qwen2.5-72B-Instruct"   # отличная поддержка русского языка

# Список провайдеров в порядке приоритета (первый доступный используется)
HF_PROVIDERS = ["novita", "together", "fireworks-ai", "nebius", "hf-inference"]

# Обратная совместимость (устарел, но оставлен для явного указания)
HF_API_BASE = f"{HF_ROUTER_BASE}/hf-inference/v1"

# Groq API (бесплатно, 6000 запросов/день, OpenAI-совместимый формат)
# Регистрация: https://console.groq.com  → API Keys
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL   = "llama-3.3-70b-versatile"   # лучшая бесплатная модель с русским языком

# OpenRouter API (бесплатно, 24+ бесплатных модели, OpenAI-совместимый формат)
# Регистрация: https://openrouter.ai → Keys → Create Key
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL   = "deepseek/deepseek-v4-flash:free"

# ModelGate API (платный, OpenAI-совместимый, российский агрегатор)
# Регистрация: https://modelgate.ru
MODELGATE_API_URL = "https://api.modelgate.ru/v1/chat/completions"
MODELGATE_MODEL   = "deepseek-v4-pro"

# Резервные модели — перебираются по порядку при 429/503/404 на основной
# Список актуален на 2025-05 (проверен через openrouter.ai/api/v1/models)
OPENROUTER_FALLBACK_MODELS = [
    "deepseek/deepseek-v4-flash:free",        # лучший выбор: отличный русский + технический анализ
    "meta-llama/llama-3.3-70b-instruct:free", # хороший универсальный вариант
    "qwen/qwen3-coder:free",                  # отличный русский язык
    "openai/gpt-oss-120b:free",               # мощный, но медленный
    "google/gemma-4-31b-it:free",
    "nousresearch/hermes-3-llama-3.1-405b:free",
    "meta-llama/llama-3.2-3b-instruct:free",  # запасной: быстрый, но слабее
]


def _build_prompt(delta_data: dict, dsr_context: dict, cascade_rules: list) -> str:
    return f"""Ты — эксперт по управлению жизненным циклом технической документации (PLM/PDM) в соответствии со стандартами ЕСКД, ЕСТД и ЕСПД.

Выполни детальный экспертный анализ следующей дельты документации:

=== ДЕЛЬТА ===
Документ: {delta_data.get('doc_name')} ({delta_data.get('doc_type')}) — {dsr_context.get('gost','')}
Поле: {delta_data.get('field_name')} [{delta_data.get('field_id')}]
Значение ДО: «{delta_data.get('v_before')}»
Значение ПОСЛЕ: «{delta_data.get('v_after')}»
Тип Ω: {delta_data.get('omega')} — {_omega_name(delta_data.get('omega',''))}
Автор: {delta_data.get('author')}
ИИ: {delta_data.get('iin')}
Обоснование: {delta_data.get('reason') or 'не указано'}

=== КАСКАДНЫЕ ЗАВИСИМОСТИ ({len(cascade_rules)} документов) ===
{_format_cascade(cascade_rules)}

=== НОРМАТИВНОЕ ОСНОВАНИЕ ===
ГОСТ Р 2.503–2023, п. 4.2: «Изменение документа, требующее изменений в других документах, должно сопровождаться одновременным внесением соответствующих изменений во все взаимосвязанные документы».

Предоставь структурированный анализ из четырёх разделов:

1. **ОЦЕНКА ИЗМЕНЕНИЯ** (50–80 слов)
   Технический смысл и значимость изменения для изделия/проекта.

2. **РИСКИ РАССИНХРОНИЗАЦИИ** (60–90 слов)
   Конкретные последствия несвоевременного обновления зависимых документов. Упоминай конкретные ГОСТ-ы и поля.

3. **ПЛАН КАСКАДНЫХ ДЕЙСТВИЙ** (80–120 слов)
   Приоритизированный порядок выполнения зависимых дельт с указанием ответственных ролей (конструктор/технолог/программист) и дедлайнов по типам Ω.

4. **РЕКОМЕНДАЦИЯ ОТВЕТСТВЕННОМУ** (40–60 слов)
   Кратко — что должен сделать исполнитель первым делом.

Отвечай на русском языке. Будь технически точным и конкретным."""


def _omega_name(o: str) -> str:
    names = {"Ω₁": "Редакционная", "Ω₂": "Параметр компонента", "Ω₃": "Изменение состава",
             "Ω₄": "Комплексный показатель", "Ω₅": "Изменение процесса",
             "Ω₆": "Нормативное основание", "Ω₇": "Инновационное"}
    return names.get(o, o)


def _format_cascade(rules: list) -> str:
    if not rules:
        return "Каскадных зависимостей нет (Ω₁ — редакционное изменение)"
    lines = []
    for i, r in enumerate(rules, 1):
        dep = "ОБЯЗАТЕЛЬНО" if r.get("dep_type") == "1" else "рекомендуется"
        lines.append(f"  {i}. [{dep}] {r.get('description','')}")
    return "\n".join(lines)


async def analyze_delta_ai(delta_data: dict, dsr_context: dict,
                           cascade_rules: list,
                           api_key: Optional[str] = None,
                           provider: str = "groq",
                           hf_model: Optional[str] = None) -> dict:
    """
    Асинхронный AI-анализ дельты.
    provider = "groq"        (по умолчанию, бесплатно) → GROQ_API_KEY
               "huggingface"                            → HF_TOKEN
               "anthropic"                              → ANTHROPIC_API_KEY
    """
    if provider == "anthropic":
        return await _analyze_anthropic(delta_data, dsr_context, cascade_rules, api_key)
    elif provider == "huggingface":
        return await _analyze_huggingface(delta_data, dsr_context, cascade_rules,
                                          api_key, hf_model)
    elif provider == "openrouter":
        return await _analyze_openrouter(delta_data, dsr_context, cascade_rules,
                                         api_key, hf_model)
    elif provider == "modelgate":
        return await _analyze_modelgate(delta_data, dsr_context, cascade_rules,
                                        api_key, hf_model)
    else:  # groq (default)
        return await _analyze_groq(delta_data, dsr_context, cascade_rules,
                                   api_key, hf_model)


async def _analyze_modelgate(delta_data: dict, dsr_context: dict,
                              cascade_rules: list,
                              api_key: Optional[str] = None,
                              model: Optional[str] = None) -> dict:
    """
    Анализ через ModelGate API (OpenAI-совместимый формат, российский агрегатор).
    Документация: https://modelgate.ru
    Модели: deepseek-v4-pro, и др.
    """
    key = api_key or os.environ.get("MODELGATE_API_KEY", "")
    if not key:
        return {"error": "MODELGATE_API_KEY не настроен. "
                         "Получите ключ на modelgate.ru и передайте в поле api_key "
                         "или задайте MODELGATE_API_KEY в переменных среды."}

    chosen_model = model or MODELGATE_MODEL
    prompt = _build_prompt(delta_data, dsr_context, cascade_rules)
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type":  "application/json",
    }
    body = {
        "model":       chosen_model,
        "messages":    [{"role": "user", "content": prompt}],
        "max_tokens":  3000,
        "temperature": 0.3,
    }
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(MODELGATE_API_URL, headers=headers, json=body)
            if resp.status_code == 401:
                return {"error": "Неверный ModelGate ключ (401). "
                                 "Проверьте ключ на modelgate.ru."}
            if resp.status_code == 429:
                return {"error": "Превышен лимит запросов ModelGate (429). "
                                 "Подождите немного и повторите."}
            if resp.status_code == 402:
                return {"error": "Недостаточно средств на балансе ModelGate (402). "
                                 "Пополните баланс на modelgate.ru."}
            resp.raise_for_status()
            data = resp.json()
    except httpx.ConnectError as exc:
        return {"error": f"Нет подключения к api.modelgate.ru: {exc}. "
                         "Проверьте доступ в интернет."}
    except httpx.TimeoutException:
        return {"error": "Превышен таймаут ожидания ответа от ModelGate (60 с)."}
    except httpx.HTTPStatusError as exc:
        return {"error": f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"}

    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        return {"error": f"Неожиданный формат ответа ModelGate: {exc}. Ответ: {str(data)[:300]}"}

    usage = data.get("usage", {})
    return {
        "analysis":     text,
        "model":        chosen_model,
        "provider":     "modelgate",
        "omega":        delta_data.get("omega"),
        "tokens_used":  usage.get("completion_tokens", 0),
        "tokens_total": usage.get("total_tokens", 0),
    }


async def _analyze_huggingface(delta_data: dict, dsr_context: dict,
                                cascade_rules: list,
                                hf_token: Optional[str] = None,
                                model: Optional[str] = None) -> dict:
    """
    Анализ через Hugging Face Inference Router (OpenAI-совместимый формат).
    Новый роутер: https://router.huggingface.co/{provider}/v1/chat/completions
    Автоматически перебирает провайдеров: novita → together → fireworks-ai → nebius → hf-inference
    """
    token = (hf_token or
             os.environ.get("HF_TOKEN") or
             os.environ.get("HUGGINGFACE_API_KEY", ""))
    if not token:
        return {"error": "HF токен не настроен. Установите HF_TOKEN в переменных среды "
                         "или передайте в поле api_key."}

    chosen_model = model or HF_MODEL
    prompt = _build_prompt(delta_data, dsr_context, cascade_rules)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
    }
    body = {
        "model":       chosen_model,
        "messages":    [{"role": "user", "content": prompt}],
        "max_tokens":  1200,
        "temperature": 0.3,
        "stream":      False,
    }

    last_error = ""
    used_provider = ""

    try:
        async with httpx.AsyncClient(timeout=90) as client:
            # Шаг 1: проверяем токен через /api/whoami
            whoami = await client.get(
                "https://huggingface.co/api/whoami",
                headers={"Authorization": f"Bearer {token}"},
            )
            if whoami.status_code == 401:
                return {"error": "Неверный HF токен (401 Unauthorized). "
                                 "Перейдите на huggingface.co → Settings → Access Tokens "
                                 "и создайте новый токен с правом Read."}

            # Шаг 2: перебираем провайдеров по приоритету
            for provider in HF_PROVIDERS:
                url = f"{HF_ROUTER_BASE}/{provider}/v1/chat/completions"
                resp = await client.post(url, headers=headers, json=body)

                if resp.status_code == 401:
                    return {"error": "Неверный HF токен (401 Unauthorized). "
                                     "Перейдите на huggingface.co → Settings → Access Tokens "
                                     "и создайте новый токен с правом Read."}
                if resp.status_code == 402:
                    return {"error": "Превышен лимит бесплатных запросов Hugging Face (402). "
                                     "Попробуйте позже или пополните баланс на huggingface.co/pricing."}
                if resp.status_code == 503:
                    last_error = f"Провайдер {provider}: модель загружается (503)"
                    continue  # пробуем следующий

                # Проверяем тело ответа на ошибку "not supported"
                if resp.status_code == 400:
                    try:
                        err_body = resp.json()
                        err_msg = err_body.get("error", "")
                        if "not supported" in err_msg.lower() or "not found" in err_msg.lower():
                            last_error = f"Провайдер {provider}: {err_msg}"
                            continue  # модель не поддерживается этим провайдером
                    except Exception:
                        pass

                if resp.status_code >= 400:
                    try:
                        last_error = f"Провайдер {provider}: HTTP {resp.status_code} — {resp.json().get('error', resp.text[:100])}"
                    except Exception:
                        last_error = f"Провайдер {provider}: HTTP {resp.status_code}"
                    continue

                # Успех
                data = resp.json()
                err_in_body = data.get("error", "")
                if err_in_body and ("not supported" in err_in_body.lower() or "not found" in err_in_body.lower()):
                    last_error = f"Провайдер {provider}: {err_in_body}"
                    continue

                used_provider = provider
                break
            else:
                # Ни один провайдер не подошёл
                return {
                    "error": f"Модель {chosen_model} недоступна ни у одного провайдера HF. "
                             f"Последняя ошибка: {last_error}. "
                             "Попробуйте выбрать другую модель или проверьте баланс на huggingface.co/pricing."
                }

    except httpx.ConnectError as exc:
        return {"error": f"Нет подключения к router.huggingface.co: {exc}. "
                         "Проверьте доступ в интернет."}
    except httpx.TimeoutException:
        return {"error": f"Превышен таймаут ожидания ответа от модели {chosen_model} (90 с). "
                         "Попробуйте позже или выберите более лёгкую модель."}
    except httpx.HTTPStatusError as exc:
        return {"error": f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"}

    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        return {"error": f"Неожиданный формат ответа HF API: {exc}. Ответ: {str(data)[:300]}"}

    usage = data.get("usage", {})
    return {
        "analysis":     text,
        "model":        chosen_model,
        "provider":     f"huggingface/{used_provider}",
        "omega":        delta_data.get("omega"),
        "tokens_used":  usage.get("completion_tokens", 0),
        "tokens_total": usage.get("total_tokens", 0),
    }


async def _analyze_anthropic(delta_data: dict, dsr_context: dict,
                              cascade_rules: list,
                              api_key: Optional[str] = None) -> dict:
    """Анализ через Anthropic Claude API"""
    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return {"error": "ANTHROPIC_API_KEY не настроен."}

    prompt = _build_prompt(delta_data, dsr_context, cascade_rules)
    headers = {
        "x-api-key":          key,
        "anthropic-version":  "2023-06-01",
        "content-type":       "application/json",
    }
    body = {
        "model":      ANTHROPIC_MODEL,
        "max_tokens": 1200,
        "messages":   [{"role": "user", "content": prompt}],
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(ANTHROPIC_API_URL, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
    except httpx.ConnectError as exc:
        return {"error": f"Нет подключения к api.anthropic.com: {exc}. "
                         "Проверьте доступ в интернет."}
    except httpx.TimeoutException:
        return {"error": "Превышен таймаут ожидания ответа от Anthropic API (30 с)."}
    except httpx.HTTPStatusError as exc:
        return {"error": f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"}

    text = "".join(b.get("text", "") for b in data.get("content", []))
    return {
        "analysis":    text,
        "model":       ANTHROPIC_MODEL,
        "provider":    "anthropic",
        "omega":       delta_data.get("omega"),
        "tokens_used": data.get("usage", {}).get("output_tokens", 0),
    }


async def _analyze_groq(delta_data: dict, dsr_context: dict,
                         cascade_rules: list,
                         api_key: Optional[str] = None,
                         model: Optional[str] = None) -> dict:
    """
    Анализ через Groq API (OpenAI-совместимый формат).
    Бесплатно: 6 000 запросов/день, до 500 000 токенов/день.
    Регистрация: https://console.groq.com → API Keys
    Модели: llama-3.3-70b-versatile, llama-3.1-8b-instant, mixtral-8x7b-32768
    """
    key = api_key or os.environ.get("GROQ_API_KEY", "")
    if not key:
        return {"error": "GROQ_API_KEY не настроен. "
                         "Получите бесплатный ключ на console.groq.com → API Keys "
                         "и передайте в поле api_key или задайте GROQ_API_KEY в переменных среды."}

    chosen_model = model or GROQ_MODEL
    prompt = _build_prompt(delta_data, dsr_context, cascade_rules)
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type":  "application/json",
    }
    body = {
        "model":       chosen_model,
        "messages":    [{"role": "user", "content": prompt}],
        "max_tokens":  1200,
        "temperature": 0.3,
        "stream":      False,
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(GROQ_API_URL, headers=headers, json=body)
            if resp.status_code == 401:
                return {"error": "Неверный Groq API ключ (401). "
                                 "Проверьте ключ на console.groq.com → API Keys."}
            if resp.status_code == 429:
                return {"error": "Превышен лимит запросов Groq (429 Too Many Requests). "
                                 "Подождите минуту и попробуйте снова."}
            resp.raise_for_status()
            data = resp.json()
    except httpx.ConnectError as exc:
        return {"error": f"Нет подключения к api.groq.com: {exc}. "
                         "Проверьте доступ в интернет."}
    except httpx.TimeoutException:
        return {"error": "Превышен таймаут ожидания ответа от Groq API (30 с)."}
    except httpx.HTTPStatusError as exc:
        return {"error": f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"}

    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        return {"error": f"Неожиданный формат ответа Groq API: {exc}. Ответ: {str(data)[:300]}"}

    usage = data.get("usage", {})
    return {
        "analysis":     text,
        "model":        chosen_model,
        "provider":     "groq",
        "omega":        delta_data.get("omega"),
        "tokens_used":  usage.get("completion_tokens", 0),
        "tokens_total": usage.get("total_tokens", 0),
    }


async def _analyze_openrouter(delta_data: dict, dsr_context: dict,
                               cascade_rules: list,
                               api_key: Optional[str] = None,
                               model: Optional[str] = None) -> dict:
    """
    Анализ через OpenRouter API (OpenAI-совместимый формат).
    Бесплатно: 24+ бесплатных модели (суффикс :free), без ограничений по аккаунту.
    Регистрация: https://openrouter.ai → Keys → Create Key
    Модели (бесплатные): meta-llama/llama-3.3-70b-instruct:free,
                         deepseek/deepseek-v4-flash:free,
                         google/gemma-4-31b-it:free
    """
    key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        return {"error": "OPENROUTER_API_KEY не настроен. "
                         "Получите бесплатный ключ на openrouter.ai → Keys → Create Key "
                         "и передайте в поле api_key или задайте OPENROUTER_API_KEY в переменных среды."}

    prompt = _build_prompt(delta_data, dsr_context, cascade_rules)
    headers = {
        "Authorization":  f"Bearer {key}",
        "Content-Type":   "application/json",
        "HTTP-Referer":   "https://sujzd.local",   # обязателен для OpenRouter
        "X-Title":        "SUJZD",
    }

    # Собираем список моделей для перебора
    if model:
        models_to_try = [model]
    else:
        models_to_try = list(OPENROUTER_FALLBACK_MODELS)

    last_error = ""
    data = None
    used_model = models_to_try[0]

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            for m in models_to_try:
                body = {
                    "model":       m,
                    "messages":    [{"role": "user", "content": prompt}],
                    "max_tokens":  1200,
                    "temperature": 0.3,
                }
                resp = await client.post(OPENROUTER_API_URL, headers=headers, json=body)

                if resp.status_code == 401:
                    return {"error": "Неверный OpenRouter ключ (401). "
                                     "Проверьте ключ на openrouter.ai/keys."}
                if resp.status_code == 402:
                    return {"error": f"Модель {m} платная. "
                                     "Используйте модель с суффиксом :free."}
                if resp.status_code == 429:
                    last_error = f"Модель {m}: превышен лимит (429)"
                    print(f"[OpenRouter] {last_error} → пробую следующую")
                    continue   # пробуем следующую
                if resp.status_code == 503:
                    last_error = f"Модель {m}: недоступна (503)"
                    print(f"[OpenRouter] {last_error} → пробую следующую")
                    continue

                if resp.status_code >= 400:
                    try:
                        last_error = f"Модель {m}: HTTP {resp.status_code} — {resp.json().get('error', resp.text[:100])}"
                    except Exception:
                        last_error = f"Модель {m}: HTTP {resp.status_code}"
                    print(f"[OpenRouter] {last_error} → пробую следующую")
                    continue

                data = resp.json()

                # OpenRouter иногда возвращает ошибку с кодом 200 в теле
                if "error" in data and "choices" not in data:
                    err = data["error"]
                    msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                    last_error = f"Модель {m}: {msg}"
                    data = None
                    continue

                used_model = m
                break
            else:
                return {"error": f"Все модели OpenRouter недоступны. Последняя ошибка: {last_error}"}

    except httpx.ConnectError as exc:
        return {"error": f"Нет подключения к openrouter.ai: {exc}. "
                         "Проверьте доступ в интернет."}
    except httpx.TimeoutException:
        return {"error": "Превышен таймаут ожидания ответа от OpenRouter (60 с)."}
    except httpx.HTTPStatusError as exc:
        return {"error": f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"}

    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        return {"error": f"Неожиданный формат ответа OpenRouter: {exc}. Ответ: {str(data)[:300]}"}

    usage = data.get("usage", {})
    return {
        "analysis":     text,
        "model":        used_model,
        "provider":     "openrouter",
        "omega":        delta_data.get("omega"),
        "tokens_used":  usage.get("completion_tokens", 0),
        "tokens_total": usage.get("total_tokens", 0),
    }


# ---------------------------------------------------------------------------
# 4. Автоматическое определение типа документа и извлечение полей
# ---------------------------------------------------------------------------

# Ключевые слова для автоопределения типа документа
_DOCTYPE_HINTS: list[tuple[str, list[str]]] = [
    ("ESKD_DETAIL",   ["чертёж детали", "чертеж детали", "деталь", "заготовка"]),
    ("ESKD_ASSEMBLY", ["сборочный чертёж", "сборочный чертеж", "сборочная единица", "сб"]),
    ("ESKD_SPEC",     ["спецификация", "specification", "перечень элементов"]),
    ("ESKD_VO",       ["общий вид", "чертёж общего вида"]),
    ("ESKD_TU",       ["технические условия", "ту ", "приёмки", "правила приемки"]),
    ("ESKD_PASSPORT", ["паспорт", "формуляр", "свидетельство о приёмке"]),
    ("ESKD_RE",       ["руководство по эксплуатации", "рэ ", "техническое обслуживание", "монтаж"]),
    ("ESKD_FORMULAR", ["формуляр", "учёт то", "хранения"]),
    ("ESKD_SCHEME_E3",   ["схема электрическая", "принципиальная", "э3", "перечень элементов"]),
    ("ESKD_ZIP",      ["ведомость зип", "запасные части", "зип"]),
    ("ESTD_MK",       ["маршрутная карта", "мк ", "маршрут", "строка м:"]),
    ("ESTD_OK",       ["операционная карта", "ок ", "режимы резания", "переход"]),
    ("ESTD_KTK",      ["карта технического контроля", "ктк", "контроль"]),
    ("ESTD_KK",       ["комплектовочная карта", "кк ", "сборочная операция"]),
    ("ESTD_TI",       ["технологическая инструкция", "ти ", "нанесение покрытия"]),
    ("ESTD_KTP",      ["карта технологического процесса", "ктп"]),
    ("ESTD_VTP",      ["ведомость технологических процессов", "втп"]),
    ("ESPD_TZ",       ["техническое задание", "тз ", "назначение и область применения",
                        "функциональные требования", "стадии разработки"]),
    ("ESPD_SPEC",     ["спецификация по", "сппо", "компоненты программного"]),
    ("ESPD_OP",       ["описание программы", "оп ", "логическая структура"]),
    ("ESPD_RO",       ["руководство оператора", "ро ", "выполнение программы"]),
    ("ESPD_PMI",      ["программа и методика", "пми", "тестовые данные", "методы испытаний"]),
    ("ESPD_FORMULAR", ["формуляр по", "фпо", "история эксплуатации"]),
    ("ESPD_RP",       ["руководство программиста", "рп ", "структура данных"]),
    ("ESPD_RSP",      ["руководство системного", "рсп", "конфигурация"]),
]


def detect_doc_type(text: str) -> str | None:
    """Определить тип документа по тексту. Возвращает код типа или None."""
    low = text.lower()
    scores: dict[str, int] = {}
    for code, hints in _DOCTYPE_HINTS:
        cnt = sum(1 for h in hints if h in low)
        if cnt:
            scores[code] = cnt
    return max(scores, key=scores.get) if scores else None


# Паттерны извлечения для каждого поля (field_id → list of regex)
_FIELD_PATTERNS: dict[str, list[str]] = {
    # ── ESKD_DETAIL ──────────────────────────────────────────────────
    "designation":      [r"(?:обозначение|designation)[:\s]+([А-ЯA-Z0-9][А-ЯA-Z0-9.\-]{4,30})",
                         r"([А-Я]{2,5}[\.\s]\d{3}[\d\.\-]{4,15})"],
    "name_field":       [r"наименование[:\s]+([^\n,;]{4,80})",
                         r"деталь[:\s]+([^\n,;]{4,80})"],
    "material":         [r"материал[:\s]+([^\n,;]{3,60})",
                         r"(?:Ст|Ал|АМ|12Х|40Х|ВТ|Д16|АК)\w{1,8}(?:\s+ГОСТ[\s\d\-]+)?",
                         r"сталь\s+[\w\d\-]+(?:\s+ГОСТ[\s\d\-]+)?"],
    "mass":             [r"масса[:\s]+([\d,\.]+)\s*кг",
                         r"(\d+[,\.]\d+)\s*кг"],
    "scale":            [r"масштаб[:\s]*(\d+\s*:\s*\d+)",
                         r"\b(\d+\s*:\s*\d+)\b"],
    "tolerance":        [r"(H\d+/[a-z]\d+)",
                         r"допуск[:\s]+([^\n;]{4,60})",
                         r"(±\s*\d+[,\.]\d+\s*мм)"],
    "roughness":        [r"(Ra\s*[\d,\.]+)",
                         r"(Rz\s*[\d,\.]+)",
                         r"шероховатость[:\s]+([^\n;]{3,40})"],
    "coating":          [r"покрытие[:\s]+([^\n;]{4,80})",
                         r"(цинкование\s+[\w\.]+)",
                         r"(хромирование\s+[\w\.]+)",
                         r"(оксидирование\s+[\w\.]*)"],
    "heat_treatment":   [r"(?:термообработка|то)[:\s]+([^\n;]{4,80})",
                         r"(нормализация[^\n;]{0,40})",
                         r"(закалка[^\n;]{0,40})",
                         r"(отпуск\s+\d+[^\n;]{0,30})"],
    "tech_requirements":[r"технические\s+требования[:\s\n]+([\s\S]{10,500}?)(?:\n\n|\Z)"],
    # ── ESKD_ASSEMBLY / ESKD_SPEC ─────────────────────────────────────
    "composition":      [r"(?:состав|позиции?)[:\s\n]+([\s\S]{10,400}?)(?:\n\n|\Z)",
                         r"(\d+\s+[А-ЯA-Z][^\n]{5,60})(?:\n|$)"],
    "bought_parts":     [r"покупные\s+изделия[:\s\n]+([\s\S]{5,300}?)(?:\n\n|\Z)"],
    "assembly_dims":    [r"(?:монтажные|сборочные)\s+размеры[:\s]+([^\n;]{4,100})"],
    "mounting_schema":  [r"схема\s+монтажа[:\s]+([^\n;]{4,100})"],
    "quantity":         [r"количество[:\s]+([\d]+)\s*(?:шт|ед|штук)?"],
    # ── ESKD_TU ───────────────────────────────────────────────────────
    "tech_req":         [r"технические\s+требования[:\s\n]+([\s\S]{20,1000}?)(?:\n\n\d|\Z)"],
    "acceptance":       [r"правила?\s+приёмки[:\s\n]+([\s\S]{10,500}?)(?:\n\n|\Z)"],
    "control_methods":  [r"методы\s+контроля[:\s\n]+([\s\S]{10,500}?)(?:\n\n|\Z)",
                         r"средства?\s+измерений?[:\s]+([^\n]{4,100})"],
    "guarantee":        [r"гарантийный\s+срок[:\s]+([\d]+\s*(?:месяц|лет|год)[^\n;]{0,40})",
                         r"гарантия[:\s]+([\d]+\s*(?:месяц|лет|год)[^\n;]{0,40})"],
    "conditions":       [r"условия\s+эксплуатации[:\s\n]+([\s\S]{10,400}?)(?:\n\n|\Z)",
                         r"температур[^\n]{0,10}([-–−]?\d+[^\n]{0,30}°C)",
                         r"(температура\s+[-–−]?\d+[^\n]{0,40})"],
    # ── ESKD_PASSPORT ─────────────────────────────────────────────────
    "tech_chars":       [r"технические\s+характеристики[:\s\n]+([\s\S]{10,800}?)(?:\n\n|\Z)",
                         r"(?:U|I|P|Uпит|Uвых)[^\n:]{0,10}:\s*([^\n]{4,80})"],
    "delivery_set":     [r"комплект\s+поставки[:\s\n]+([\s\S]{10,400}?)(?:\n\n|\Z)"],
    "acceptance_cert":  [r"свидетельство[^\n]{0,20}приёмки[:\s]+([^\n;]{4,100})"],
    # ── ESKD_RE ────────────────────────────────────────────────────────
    "installation":     [r"(?:монтаж|установка)[:\s\n]+([\s\S]{10,600}?)(?:\n\n|\Z)"],
    "operation":        [r"порядок\s+работы[:\s\n]+([\s\S]{10,600}?)(?:\n\n|\Z)"],
    "maintenance":      [r"техническое\s+обслуживание[:\s\n]+([\s\S]{10,600}?)(?:\n\n|\Z)"],
    "repair":           [r"ремонт[:\s\n]+([\s\S]{10,400}?)(?:\n\n|\Z)"],
    "zip":              [r"зип[:\s\n]+([\s\S]{10,400}?)(?:\n\n|\Z)",
                         r"запасные\s+части[:\s\n]+([\s\S]{10,400}?)(?:\n\n|\Z)"],
    # ── ESTD_MK ────────────────────────────────────────────────────────
    "product_name":     [r"наименование\s+(?:изделия|детали)[:\s]+([^\n,;]{4,80})"],
    "kd_designation":   [r"обозначение\s+КД[:\s]+([^\n,;]{4,40})"],
    "blank_mass":       [r"масса\s+заготовки[:\s]+([\d,\.]+)\s*кг"],
    "material_rate":    [r"норма\s+расхода[:\s]+([\d,\.]+)"],
    "operations":       [r"(?:маршрут|операции)[:\s\n]+([\s\S]{10,800}?)(?:\n\n|\Z)",
                         r"(\d{3}\s+[А-Я][^\n]{4,60})(?:\n|$)"],
    "equipment":        [r"оборудование[:\s]+([^\n;]{4,100})",
                         r"станок[:\s]+([^\n;]{4,60})"],
    # ── ESTD_OK ────────────────────────────────────────────────────────
    "op_code":          [r"(?:код|номер)\s+операции[:\s]+(\d{3,4})",
                         r"^(\d{3})\s+"],
    "op_name":          [r"наименование\s+операции[:\s]+([^\n,;]{4,60})",
                         r"\d{3}\s+([А-Я][^\n]{3,40}(?:ная|ная|овка|ка|ние))"],
    "cutting_modes":    [r"режимы\s+резания[:\s]+([^\n;]{4,100})",
                         r"n\s*=\s*[\d,\.]+[^\n;]{0,40}",
                         r"(n\s*=\s*\d+[^\n,;]{0,50})"],
    "tool":             [r"(?:инструмент|резец|сверло|фреза)[:\s]+([^\n;]{4,80})"],
    "fixture":          [r"(?:приспособление|патрон|тиски)[:\s]+([^\n;]{4,80})"],
    "finishing_method": [r"(?:финишная|чистовая)\s+обработка[:\s]+([^\n;]{4,80})",
                         r"шлифование[^\n;]{0,40}"],
    "heat_modes":       [r"режимы?\s+термообработки?[:\s]+([^\n;]{4,80})",
                         r"(?:закалка|нормализация|отпуск)\s+(\d+[^\n;]{0,40}°)"],
    "norm_time":        [r"норма\s+времени[:\s]+([\d,\.]+)\s*(?:мин|ч)",
                         r"Тшт[:\s]+([\d,\.]+)"],
    # ── ESTD_KTK ───────────────────────────────────────────────────────
    "control_ops":      [r"операции\s+контроля[:\s\n]+([\s\S]{10,400}?)(?:\n\n|\Z)"],
    "control_tools":    [r"средства?\s+(?:измерений?|контроля)[:\s]+([^\n;]{4,80})"],
    "frequency":        [r"периодичность[:\s]+([^\n;]{4,60})"],
    # ── ESTD_TI ────────────────────────────────────────────────────────
    "coating_procedure":[r"(?:нанесение|порядок)\s+покрытия[:\s\n]+([\s\S]{10,400}?)(?:\n\n|\Z)"],
    "installation_order":[r"порядок\s+монтажа[:\s\n]+([\s\S]{10,400}?)(?:\n\n|\Z)"],
    "tolerances":       [r"допуски\s+при\s+монтаже[:\s]+([^\n;]{4,80})"],
    # ── ESPD_TZ ────────────────────────────────────────────────────────
    "purpose":          [r"назначение[:\s\n]+([\s\S]{10,600}?)(?:\n\n|\Z)",
                         r"область\s+применения[:\s\n]+([\s\S]{10,400}?)(?:\n\n|\Z)"],
    "func_requirements":[r"функциональные\s+требования[:\s\n]+([\s\S]{10,800}?)(?:\n\n|\Z)",
                         r"(?:функции|требования)[:\s\n]+([\s\S]{10,500}?)(?:\n\n|\Z)"],
    "reliability_req":  [r"(?:надёжност|надежност)[^\n]{0,20}[:\s\n]+([\s\S]{10,400}?)(?:\n\n|\Z)",
                         r"MTBF[:\s]+([\d,\.]+\s*[чч\.])",
                         r"вероятность\s+безотказной[^\n]{0,20}([\d,\.]+)"],
    "hw_req":           [r"технические\s+средства[:\s\n]+([\s\S]{10,400}?)(?:\n\n|\Z)",
                         r"(?:процессор|RAM|ОЗУ|Flash|ПЗУ)[^\n]{0,60}"],
    "sw_req":           [r"программное\s+обеспечение[:\s\n]+([\s\S]{10,400}?)(?:\n\n|\Z)"],
    "doc_req":          [r"требования\s+к\s+документации[:\s\n]+([\s\S]{10,400}?)(?:\n\n|\Z)"],
    "stages":           [r"стадии[^\n]{0,20}этапы[:\s\n]+([\s\S]{10,400}?)(?:\n\n|\Z)",
                         r"(?:аванпроект|технический\s+проект|рабочая\s+документация)[^\n]{0,60}"],
    # ── ESPD_OP ────────────────────────────────────────────────────────
    "general_info":     [r"общие\s+сведения[:\s\n]+([\s\S]{10,600}?)(?:\n\n|\Z)"],
    "functions":        [r"функциональное\s+назначение[:\s\n]+([\s\S]{10,600}?)(?:\n\n|\Z)"],
    "structure":        [r"логическая\s+структура[:\s\n]+([\s\S]{10,600}?)(?:\n\n|\Z)"],
    "environment":      [r"среда[^\n]{0,20}применения[:\s]+([^\n;]{4,100})"],
    "input_output":     [r"входные[^\n]{0,10}выходные[:\s\n]+([\s\S]{10,400}?)(?:\n\n|\Z)"],
    # ── ESPD_RO ────────────────────────────────────────────────────────
    "description":      [r"(?:описание|назначение)\s+функций[:\s\n]+([\s\S]{10,600}?)(?:\n\n|\Z)"],
    "execution_order":  [r"выполнение\s+программы[:\s\n]+([\s\S]{10,400}?)(?:\n\n|\Z)"],
    "diagnostics":      [r"диагностические[^\n]{0,20}[:\s\n]+([\s\S]{10,300}?)(?:\n\n|\Z)"],
    # ── ESPD_PMI ───────────────────────────────────────────────────────
    "test_object":      [r"объект\s+испытаний[:\s]+([^\n;]{4,80})"],
    "test_purpose":     [r"цель\s+испытаний[:\s\n]+([\s\S]{10,400}?)(?:\n\n|\Z)"],
    "test_methods":     [r"методы\s+испытаний[:\s\n]+([\s\S]{10,600}?)(?:\n\n|\Z)"],
    "test_conditions":  [r"условия\s+испытаний[:\s\n]+([\s\S]{10,400}?)(?:\n\n|\Z)"],
    "test_data":        [r"тестовые\s+данные[:\s\n]+([\s\S]{10,400}?)(?:\n\n|\Z)"],
    # ── ESPD_RP / RSP ──────────────────────────────────────────────────
    "data_structures":  [r"структура\s+данных[:\s\n]+([\s\S]{10,600}?)(?:\n\n|\Z)"],
    "modification":     [r"(?:правила|модификац)[^\n]{0,20}[:\s\n]+([\s\S]{10,400}?)(?:\n\n|\Z)"],
    "config":           [r"конфигурация[:\s\n]+([\s\S]{10,400}?)(?:\n\n|\Z)"],
    "environment_setup":[r"настройка\s+среды[:\s\n]+([\s\S]{10,400}?)(?:\n\n|\Z)"],
    # ── Universal ──────────────────────────────────────────────────────
    "layout":           [r"компоновка[:\s\n]+([\s\S]{10,400}?)(?:\n\n|\Z)"],
    "principle":        [r"принцип\s+работы[:\s\n]+([\s\S]{10,400}?)(?:\n\n|\Z)"],
    "elements":         [r"(?:перечень|состав)\s+элементов[:\s\n]+([\s\S]{10,600}?)(?:\n\n|\Z)"],
    "connections":      [r"(?:связи|цепи)[:\s\n]+([\s\S]{10,400}?)(?:\n\n|\Z)"],
    "designations":     [r"позиционные\s+обозначения[:\s\n]+([\s\S]{10,300}?)(?:\n\n|\Z)"],
    "zip_items":        [r"перечень\s+зип[:\s\n]+([\s\S]{10,400}?)(?:\n\n|\Z)"],
    "quantity_kit":     [r"количество\s+на\s+комплект[:\s]+([\d]+)"],
}

# Поля для каждого типа документа (взяты из DSR)
_TYPE_FIELDS: dict[str, list[str]] = {
    "ESKD_DETAIL":   ["designation","name_field","material","mass","scale","tolerance","roughness","coating","heat_treatment","tech_requirements"],
    "ESKD_ASSEMBLY": ["designation","composition","assembly_dims","mounting_schema"],
    "ESKD_SPEC":     ["designation","composition","bought_parts","quantity"],
    "ESKD_VO":       ["designation","layout","principle"],
    "ESKD_TU":       ["tech_req","acceptance","control_methods","guarantee","conditions"],
    "ESKD_PASSPORT": ["tech_chars","delivery_set","guarantee","acceptance_cert"],
    "ESKD_RE":       ["conditions","installation","operation","maintenance","repair","zip"],
    "ESKD_FORMULAR": ["tech_data","manufacture_info","service_log"],
    "ESKD_SCHEME_E3":   ["elements","connections","designations"],
    "ESKD_ZIP":      ["zip_items","quantity_kit"],
    "ESTD_MK":       ["product_name","kd_designation","material","blank_mass","material_rate","operations","equipment"],
    "ESTD_OK":       ["op_code","op_name","equipment","cutting_modes","tool","fixture","finishing_method","heat_modes","norm_time"],
    "ESTD_KTK":      ["control_ops","control_methods","control_tools","frequency"],
    "ESTD_KK":       ["assembly_composition","op_number"],
    "ESTD_TI":       ["coating_procedure","installation_order","tolerances"],
    "ESTD_KTP":      ["all_operations","equipment_list","total_norm_time"],
    "ESTD_VTP":      ["process_list"],
    "ESPD_TZ":       ["purpose","func_requirements","reliability_req","hw_req","sw_req","doc_req","stages"],
    "ESPD_SPEC":     ["components"],
    "ESPD_OP":       ["general_info","functions","structure","environment","input_output"],
    "ESPD_RO":       ["description","conditions","execution_order","diagnostics"],
    "ESPD_PMI":      ["test_object","test_purpose","test_methods","test_conditions","test_data"],
    "ESPD_FORMULAR": ["purpose","resources","service_history"],
    "ESPD_RP":       ["data_structures","modification"],
    "ESPD_RSP":      ["config","installation","environment_setup"],
}


# Маппинг русских заголовков таблиц → field_id DSR
_HEADER_TO_FIELD: dict[str, str] = {
    # ЕСКД — Деталь
    "обозначение":              "designation",
    "наименование":             "name_field",
    "материал":                 "material",
    "марка материала":          "material",
    "масса":                    "mass",
    "масса, кг":                "mass",
    "масштаб":                  "scale",
    "допуск":                   "tolerance",
    "посадка":                  "tolerance",
    "шероховатость":            "roughness",
    "ra":                       "roughness",
    "покрытие":                 "coating",
    "термообработка":           "heat_treatment",
    "то":                       "heat_treatment",
    "технические требования":   "tech_requirements",
    "тех. требования":          "tech_requirements",
    # ЕСКД — Спецификация / Сборочный
    # "позиция" намеренно НЕ маппится сюда — позиция накапливается через composition_parts
    "состав":                   "composition",
    "кол-во":                   "quantity",
    "количество":               "quantity",
    "кол.":                     "quantity",
    # ЕСТД — МК
    "наименование изделия":     "product_name",
    "обозначение кд":           "kd_designation",
    "масса заготовки":          "blank_mass",
    "норма расхода":            "material_rate",
    "маршрут":                  "operations",
    "операции":                 "operations",
    "оборудование":             "equipment",
    # ЕСТД — ОК
    "номер операции":           "op_code",
    "код операции":             "op_code",
    "наименование операции":    "op_name",
    "режимы резания":           "cutting_modes",
    "инструмент":               "tool",
    "приспособление":           "fixture",
    "норма времени":            "norm_time",
    "тшт":                      "norm_time",
    # ЕСТД — КТК
    "операции контроля":        "control_ops",
    "средства измерений":       "control_tools",
    "периодичность":            "frequency",
    # ЕСПД — ТЗ
    "назначение":               "purpose",
    "область применения":       "purpose",
    "функциональные требования":"func_requirements",
    "требования к надёжности":  "reliability_req",
    "надёжность":               "reliability_req",
    "технические средства":     "hw_req",
    "программное обеспечение":  "sw_req",
    "требования к документации":"doc_req",
    "стадии разработки":        "stages",
    # Паспорт
    "технические характеристики":"tech_chars",
    "комплект поставки":        "delivery_set",
    "гарантия":                 "guarantee",
    "гарантийный срок":         "guarantee",
    # ТУ
    "правила приёмки":          "acceptance",
    "методы контроля":          "control_methods",
    "условия эксплуатации":     "conditions",
}


def extract_fields_from_rows(rows: list[dict], doc_type: str) -> dict:
    """
    Извлечь DSR-поля из структурированных строк таблицы (XLSX или таблицы DOCX).
    Каждая строка — dict {заголовок_колонки: значение}.
    Стратегия:
      1. Прямой маппинг заголовка → field_id через _HEADER_TO_FIELD
      2. Для ESTD_MK/OK — каждая строка — отдельная операция
      3. Для спецификаций — накапливаем состав
    """
    if not rows:
        return {}

    result: dict[str, str] = {}
    composition_parts: list[str] = []

    spec_types = {"ESKD_SPEC", "ESKD_ASSEMBLY", "ESTD_KTP", "ESTD_VTP"}
    op_types   = {"ESTD_MK", "ESTD_OK", "ESTD_KTP"}

    operations_parts: list[str] = []

    for row in rows:
        # Нормализуем ключи строки для case-insensitive lookup
        row_ci = {k.strip().lower(): v for k, v in row.items()}

        for header, value in row.items():
            if not value or not str(value).strip():
                continue
            val_str = str(value).strip()
            key_norm = header.lower().strip(" :.")

            # Прямой маппинг
            field_id = _HEADER_TO_FIELD.get(key_norm)
            if field_id and field_id not in result:
                result[field_id] = val_str[:800]
                continue

            # Частичное совпадение заголовка (только не-однобуквенные совпадения)
            if len(key_norm) >= 3:
                for hint, fid in _HEADER_TO_FIELD.items():
                    if len(hint) >= 3 and (hint in key_norm or key_norm in hint):
                        if fid not in result:
                            result[fid] = val_str[:800]
                        break

        def _ci_get(row_lower: dict, *keys: str) -> str:
            """Case-insensitive dict lookup."""
            for k in keys:
                v = row_lower.get(k.lower().strip())
                if v:
                    return str(v).strip()
            return ""

        # Накапливаем состав для спецификаций
        if doc_type in spec_types:
            pos = _ci_get(row_ci, "Позиция", "№", "поз.", "Pos")
            nm  = _ci_get(row_ci, "Наименование", "Наименование изделия",
                          "Обозначение", "Name")
            qty = _ci_get(row_ci, "Количество", "Кол-во", "кол.", "Qty")
            if nm and nm not in (pos, qty):  # не берём номер позиции как наименование
                part = f"{pos} {nm}".strip() if pos else nm
                if qty:
                    part += f" — {qty} шт."
                composition_parts.append(part)

        # Накапливаем операции для маршрутных карт
        if doc_type in op_types:
            op_no  = _ci_get(row_ci, "Операция", "№ операции", "Номер операции", "Код")
            op_nm  = _ci_get(row_ci, "Наименование операции", "Наименование")
            equip  = _ci_get(row_ci, "Оборудование", "Станок", "Equipment")
            if op_nm:
                part = f"{op_no} {op_nm}".strip() if op_no else op_nm
                if equip:
                    part += f", {equip}"
                operations_parts.append(part)

    if composition_parts and "composition" not in result:
        result["composition"] = "; ".join(composition_parts[:50])
    if operations_parts and "operations" not in result:
        result["operations"] = "; ".join(operations_parts[:30])

    return result


def extract_fields_from_text(text: str, doc_type: str) -> dict:
    """
    Извлечь поля DSR из произвольного текста документа.
    Возвращает словарь {field_id: значение}, готовый к записи в fields_json.
    """
    fields = {}
    low = text.lower()
    target_fields = _TYPE_FIELDS.get(doc_type, [])

    for fid in target_fields:
        patterns = _FIELD_PATTERNS.get(fid, [])
        for pat in patterns:
            try:
                m = re.search(pat, low if "\\" not in pat else text, re.IGNORECASE | re.MULTILINE)
                if m:
                    val = m.group(1).strip() if m.lastindex else m.group(0).strip()
                    val = re.sub(r"\s+", " ", val).strip(" \n\t,;:")
                    if len(val) > 2:
                        fields[fid] = val[:800]   # обрезаем слишком длинные значения
                        break
            except re.error:
                continue

    # Всегда сохраняем сырой текст для полноты
    fields["_raw_text"] = text[:3000]
    fields["_doc_type_detected"] = doc_type
    return fields


# ---------------------------------------------------------------------------
# 4. Адаптеры форматов (заглушки с реальной структурой)
# ---------------------------------------------------------------------------

def parse_step_delta(content_before: str, content_after: str) -> dict:
    """
    Адаптер дельт STEP (ISO 10303-21). Алгоритм §4.6.3:
      Шаг 1: нормализация — замена #N → {N} для сравнимости, сортировка строк
      Шаг 2: структурный diff — выявить добавленные/удалённые/изменённые строки
      Шаг 3: семантическое обогащение — аннотировать типы сущностей ISO 10303
    """
    # -----------------------------------------------------------------------
    # Шаг 1: нормализация
    # Заменяем ссылки вида #123 на {123} чтобы избежать псевдо-изменений при
    # перенумерации. Извлекаем только DATA-секцию (между DATA; и ENDSEC;).
    # -----------------------------------------------------------------------
    _data_re = re.compile(r"DATA;(.*?)ENDSEC;", re.S | re.I)

    def _extract_data(text: str) -> str:
        m = _data_re.search(text)
        return m.group(1).strip() if m else text.strip()

    def _normalize(text: str) -> list:
        """Нормализует STEP: #N → {N}, одна запись — одна строка, сортировка."""
        data = _extract_data(text)
        # Разбить по ';' — каждая запись заканчивается точкой с запятой
        entries = [e.strip() for e in re.split(r";", data) if e.strip()]
        normalized = []
        for entry in entries:
            # Заменяем #NNN на {NNN} для сравнения без учёта перенумерации
            entry_norm = re.sub(r"#(\d+)", r"{\1}", entry)
            normalized.append(entry_norm + ";")
        normalized.sort()
        return normalized

    before_lines = _normalize(content_before)
    after_lines  = _normalize(content_after)

    before_set = set(before_lines)
    after_set  = set(after_lines)

    added_lines   = sorted(after_set - before_set)
    removed_lines = sorted(before_set - after_set)

    # -----------------------------------------------------------------------
    # Шаг 2: структурный diff — помечаем каждую строку знаком (+/-/=)
    # -----------------------------------------------------------------------
    all_lines = sorted(before_set | after_set)
    structural_diff = []
    for line in all_lines:
        if line in after_set and line not in before_set:
            structural_diff.append({"sign": "+", "entry": line})
        elif line in before_set and line not in after_set:
            structural_diff.append({"sign": "-", "entry": line})
        else:
            structural_diff.append({"sign": "=", "entry": line})

    # -----------------------------------------------------------------------
    # Шаг 3: семантическое обогащение
    # Аннотируем каждую изменённую строку — выявляем тип ISO 10303 сущности.
    # -----------------------------------------------------------------------
    # Словарь ключевых сущностей ISO 10303-21 / AP214 / AP242
    _ENTITY_TYPES = {
        "PRODUCT(":                          "PRODUCT",
        "PRODUCT_DEFINITION(":               "PRODUCT_DEFINITION",
        "PRODUCT_DEFINITION_SHAPE(":         "PRODUCT_DEFINITION_SHAPE",
        "NEXT_ASSEMBLY_USAGE_OCCURRENCE(":   "NEXT_ASSEMBLY_USAGE_OCCURRENCE",
        "ADVANCED_BREP_SHAPE_REPRESENTATION(": "ADVANCED_BREP_SHAPE_REPRESENTATION",
        "MANIFOLD_SOLID_BREP(":              "MANIFOLD_SOLID_BREP",
        "MEASURE_WITH_UNIT(":                "MEASURE_WITH_UNIT",
        "LENGTH_MEASURE(":                   "LENGTH_MEASURE",
        "PLANE_ANGLE_MEASURE(":              "PLANE_ANGLE_MEASURE",
        "MATERIAL_DESIGNATION(":             "MATERIAL_DESIGNATION",
        "APPLIED_DATE_AND_TIME_ASSIGNMENT(": "DATE_AND_TIME",
        "PERSON_AND_ORGANIZATION(":          "PERSON_AND_ORGANIZATION",
        "DIMENSIONAL_CHARACTERISTIC_REPRESENTATION(": "DIMENSIONAL_CHARACTERISTIC",
    }

    def _annotate(line: str) -> str:
        upper = line.upper()
        for keyword, label in _ENTITY_TYPES.items():
            if keyword in upper:
                return label
        # Попробуем извлечь имя сущности из {N}=ENTITYNAME(
        m = re.match(r"\{\d+\}=([A-Z_]+)\(", line.strip())
        if m:
            return m.group(1)
        return "UNKNOWN"

    enriched_added   = [{"entry": ln, "entity_type": _annotate(ln)} for ln in added_lines]
    enriched_removed = [{"entry": ln, "entity_type": _annotate(ln)} for ln in removed_lines]

    # Определяем suggested_omega:
    # — если изменились PRODUCT/ASSEMBLY → Ω₃ (изменение состава)
    # — если изменились только MEASURE/LENGTH → Ω₂ (изменение параметра)
    # — если добавлено много сущностей (>5) → Ω₆ (конструктивное)
    structural_types = {e["entity_type"] for e in enriched_added + enriched_removed}
    n_changed = len(added_lines) + len(removed_lines)

    if n_changed > 10 or "PRODUCT" in structural_types or \
            "NEXT_ASSEMBLY_USAGE_OCCURRENCE" in structural_types:
        if n_changed > 30:
            suggested = "Ω₆"
        else:
            suggested = "Ω₃"
    elif structural_types & {"MEASURE_WITH_UNIT", "LENGTH_MEASURE",
                              "PLANE_ANGLE_MEASURE", "DIMENSIONAL_CHARACTERISTIC"}:
        suggested = "Ω₂"
    elif n_changed == 0:
        suggested = "Ω₁"
    else:
        suggested = "Ω₂"

    return {
        "format": "STEP ISO 10303-21",
        "added_entities": enriched_added,
        "removed_entities": enriched_removed,
        "changed_count": n_changed,
        "entity_types_affected": sorted(structural_types),
        "suggested_omega": suggested,
        "structural_diff_sample": structural_diff[:20],  # первые 20 строк diff
        "note": (
            "Алгоритм §4.6.3: нормализация (#N→{N}) + структурный diff + "
            "семантическое обогащение по ISO 10303 AP214/AP242."
        ),
    }


def parse_xlsx_delta(rows_before: list, rows_after: list,
                     field_mapping: dict = None) -> dict:
    """
    Адаптер дельт XLSX (спецификации, МК, ведомости).
    Diff именованных ячеек с маппингом к полям ГОСТ.
    """
    mapping = field_mapping or {}
    changes = []

    max_rows = max(len(rows_before), len(rows_after))
    for i in range(max_rows):
        row_b = rows_before[i] if i < len(rows_before) else {}
        row_a = rows_after[i]  if i < len(rows_after)  else {}

        for col in set(list(row_b.keys()) + list(row_a.keys())):
            vb = row_b.get(col, "")
            va = row_a.get(col, "")
            if vb != va:
                changes.append({
                    "row": i + 1,
                    "column": col,
                    "gost_field": mapping.get(col, col),
                    "v_before": vb,
                    "v_after": va,
                })

    return {
        "format": "XLSX/ODS",
        "changed_cells": len(changes),
        "changes": changes,
        "suggested_omega": "Ω₃" if any(c["gost_field"] in ("composition", "operations")
                                        for c in changes) else "Ω₂",
    }


def parse_docx_delta(paragraphs_before: list, paragraphs_after: list) -> dict:
    """
    Адаптер дельт DOCX (ПЗ, ТУ, РЭ, паспорт, ТЗ).
    Структурный diff абзацев с привязкой к разделам по ГОСТ.
    """
    added   = [p for p in paragraphs_after  if p not in paragraphs_before]
    removed = [p for p in paragraphs_before if p not in paragraphs_after]

    return {
        "format": "DOCX/ODT",
        "added_paragraphs":   len(added),
        "removed_paragraphs": len(removed),
        "samples_added":   added[:3],
        "samples_removed": removed[:3],
        "suggested_omega": classify_omega("", " ".join(removed), " ".join(added))["suggested_omega"],
    }

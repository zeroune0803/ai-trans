import re
import os
import json
import csv
import glob

_RULES_DIR = os.path.dirname(os.path.abspath(__file__))

FONT_POLICY = {
    "word": {
        "Chinese": "宋体",
        "Japanese": "MS Mincho",
    },
    "presentation": {
        "Chinese": "微软雅黑",
        "Japanese": "Meiryo UI",
    },
}

LANG_CODE_MAP = {
    "Chinese": "CN",
    "Japanese": "JP",
    "English": "EN",
}

_HANZI_RE = re.compile(r"[\u4e00-\u9fff]")
_KANA_RE = re.compile(r"[\u3041-\u3096\u30a1-\u30fa\u30fd-\u30ff]")
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")
_CJK_INNER_SPACE_RE = re.compile(r"(?<=[\u3040-\u30ff\u4e00-\u9fff])\s+(?=[\u3040-\u30ff\u4e00-\u9fff])")
_PUNCT_SPACE_RE = re.compile(r"\s*([、。:：;；，,])\s*")
_CAPS_SPACED_RE = re.compile(r"\b(?:[A-Z]\s+){2,}[A-Z]\b")


def _clean_text(value):
    t = str(value or "")
    for ch in ("\ufeff", "\u200b", "\u200c", "\u200d", "\u2060"):
        t = t.replace(ch, "")
    t = t.replace("\xa0", " ")
    return t.strip()


def _load_glossary(filename):
    """Load glossary from json/csv/xlsx file. Expected format: column A = source, column B = target."""
    path = os.path.join(_RULES_DIR, filename)
    ext = os.path.splitext(filename)[1].lower()
    try:
        if ext == ".json":
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        elif ext == ".csv":
            result = {}
            with open(path, "r", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                for row in reader:
                    if len(row) >= 2:
                        src = _clean_text(row[0])
                        dst = _clean_text(row[1])
                        if src and dst:
                            result[src] = dst
            return result
        elif ext in (".xlsx", ".xls"):
            from openpyxl import load_workbook
            result = {}
            wb = load_workbook(path, read_only=True, data_only=True)
            ws = wb.active
            for row in ws.iter_rows(min_row=1, max_col=2, values_only=True):
                src = _clean_text(row[0])
                dst = _clean_text(row[1]) if len(row) > 1 else ""
                if src and dst:
                    result[src] = dst
            wb.close()
            return result
    except Exception:
        return {}
    return {}


def _load_all_glossaries(prefix):
    """Load all glossary files by prefix (e.g., glossary_ja / glossary_en) and merge them."""
    merged = {}
    for ext in ("json", "csv", "xlsx"):
        for filepath in sorted(glob.glob(os.path.join(_RULES_DIR, f"{prefix}*.{ext}"))):
            merged.update(_load_glossary(os.path.basename(filepath)))
    return merged


JAPANESE_TERM_REPLACEMENTS = _load_all_glossaries("glossary_ja")
ENGLISH_TERM_REPLACEMENTS = _load_all_glossaries("glossary_en")


def get_target_font_name(target_lang, content_type="presentation"):
    policy = FONT_POLICY.get(content_type) or FONT_POLICY["presentation"]
    return policy.get(target_lang)


def get_lang_code(target_lang):
    return LANG_CODE_MAP.get(target_lang, (target_lang or "XX")[:2].upper())


def get_project_term_replacements(target_lang):
    if target_lang == "Japanese":
        return JAPANESE_TERM_REPLACEMENTS
    if target_lang == "English":
        return ENGLISH_TERM_REPLACEMENTS
    return {}


def _collect_relevant_project_terms(target_lang, source_texts=None, existing_glossary=None):
    project_map = get_project_term_replacements(target_lang)
    if not project_map:
        return {}

    relevant = {}
    existing_glossary = existing_glossary if isinstance(existing_glossary, dict) else {}
    source_texts = source_texts or []
    source_blob = "\n".join(_clean_text(x) for x in source_texts if _clean_text(x))

    for k, v in project_map.items():
        ks = _clean_text(k)
        vs = _clean_text(v)
        if not ks or not vs:
            continue
        if ks in existing_glossary:
            relevant[ks] = vs
            continue
        if source_blob and ks in source_blob:
            relevant[ks] = vs

    return relevant


def resolve_speed_options(speed_mode):
    mode = (speed_mode or "balanced").lower()
    if mode == "fast":
        return {
            "batch_size": 30,
            "max_retries": 1,
            "prefer_large_model": False,
            "enable_quality_gate": False,
        }
    if mode == "strict":
        return {
            "batch_size": 20,
            "max_retries": 3,
            "prefer_large_model": False,
            "enable_quality_gate": True,
        }
    # 新增 "root_cause" 模式：直接用大模型翻译，跳过小模型
    if mode == "root_cause":
        return {
            "batch_size": 20,
            "max_retries": 2,
            "prefer_large_model": True,
            "use_large_model_only": True,
            "enable_quality_gate": True,
        }
    return {
        "batch_size": 20,
        "max_retries": 2,
        "prefer_large_model": False,
        "enable_quality_gate": True,
    }


def contains_hanzi(text):
    return bool(text and _HANZI_RE.search(text))


def has_kana(text):
    return bool(text and _KANA_RE.search(text))


def looks_untranslated_cn_in_ja(text):
    t = (text or "").strip()
    if not t:
        return False
    return contains_hanzi(t) and (not has_kana(t))


def cleanup_japanese_text(text):
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    t = _MULTI_SPACE_RE.sub(" ", t)
    t = _CJK_INNER_SPACE_RE.sub("", t)
    t = _PUNCT_SPACE_RE.sub(r"\1", t)

    def _collapse_caps(m):
        return re.sub(r"\s+", "", m.group(0))

    t = _CAPS_SPACED_RE.sub(_collapse_caps, t)

    # Pattern to detect English acronyms/abbreviations (all uppercase, possibly with numbers/hyphens)
    # These should NOT be translated per system prompt constraint 4
    _ACRONYM_PATTERN = re.compile(r"^[A-Z][A-Z0-9\-]*$")

    for src, dst in JAPANESE_TERM_REPLACEMENTS.items():
        # Skip English acronyms to comply with system prompt constraint 4:
        # "KEEP AS-IS (DO NOT translate): pure English words, English acronyms/abbreviations (e.g. AI, DX, APP, KPI, ERP, AEON, IoT, RPA, BI, SaaS)"
        if _ACRONYM_PATTERN.match(src):
            continue
        t = t.replace(src, dst)

    return t.strip()


def sanitize_glossary_for_japanese(glossary):
    return sanitize_glossary_for_target(glossary, "Japanese")


def sanitize_glossary_for_target(glossary, target_lang, source_texts=None):
    if not isinstance(glossary, dict):
        glossary = {}

    cleaned_auto = {}
    for k, v in glossary.items():
        ks = _clean_text(k)
        vs = _clean_text(v)
        if not ks or not vs:
            continue
        # Drop obvious untranslated Chinese->Japanese identity mappings from auto-generated glossary.
        if target_lang == "Japanese" and ks == vs and contains_hanzi(ks) and (not has_kana(ks)):
            continue
        cleaned_auto[ks] = vs

    project_map = _collect_relevant_project_terms(
        target_lang,
        source_texts=source_texts,
        existing_glossary=cleaned_auto,
    )
    fixed = {}

    # Project dictionary is canonical and should always win.
    for k, v in project_map.items():
        ks = _clean_text(k)
        vs = _clean_text(v)
        if ks and vs:
            fixed[ks] = vs

    for ks, vs in cleaned_auto.items():
        if ks in project_map:
            continue
        fixed[ks] = vs

    return fixed

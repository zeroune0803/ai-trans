# 全新 Agentic Batch 架构 PPT 翻译引擎
import os
import sys
import time
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pptx import Presentation
from pptx.enum.text import MSO_AUTO_SIZE
from pptx.oxml import parse_xml
from pptx.oxml.ns import qn
from pptx.util import Pt
from openai import OpenAI
from rules import get_target_font_name, resolve_speed_options, sanitize_glossary_for_target

API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
BASE_URL = (os.getenv("OPENAI_BASE_URL") or "").strip()

_client_kwargs = {"api_key": API_KEY, "default_headers": {"api-key": API_KEY}}
if BASE_URL:
    _client_kwargs["base_url"] = BASE_URL
client = OpenAI(**_client_kwargs)

# 定义大小两套模型（优先读取环境变量）
# 注意：在 Azure OpenAI 中，这里应填写“部署名”，不一定等于基础模型名。
LARGE_MODEL = os.getenv("LARGE_MODEL_NAME", "gpt-4o")
SMALL_MODEL = os.getenv("SMALL_MODEL_NAME", "gpt-4.1-mini")
SMALL_MODEL_FALLBACKS = [
    m.strip()
    for m in os.getenv("SMALL_MODEL_FALLBACKS", "gpt-4o").split(",")
    if m.strip()
]
DISABLED_MODEL_NAMES = {
    m.strip()
    for m in os.getenv("DISABLED_MODEL_NAMES", "gpt-4o-mini").split(",")
    if m.strip()
}

_CJK_RE = re.compile(r'[\u3000-\u9fff\uac00-\ud7af\uf900-\ufaff]')
_JP_KANA_RE = re.compile(r'[\u3041-\u3096\u30a1-\u30fa\u30fd-\u30ff]')
_HANZI_RE = re.compile(r'[\u4e00-\u9fff]')
_SIMPLIFIED_ONLY_RE = re.compile(
    r"[这后发图书体门风广东业车云龙头务数烟译简检测页签线为国汉标录审阶场景说产构图"
    r"全务调动踪陈点户网类据协账链销触单购运设监损鲜预侧报导览财级页钟册录宽"
    r"台现亿况队块态]"
)

def generate_glossary(all_texts, target_lang):
    """【第一步】：大模型提炼全局术语库"""
    print(f"[*] 正在使用大模型({LARGE_MODEL})提取全局术语...")
    combined_text = "\n".join(all_texts[:100])  # 摘取前100句作为样本提取字典即可，避免超长

    prompt = f"""You are a Localization PM. Review the following content and extract the 15 most important professional terms or proper nouns.
Generate a translation glossary for translating to {target_lang}.

CRITICAL RULES:
1. Values MUST be in {target_lang}. Do NOT keep values identical to keys. If you cannot translate a term, do not include it.
2. For terms containing English letters / acronyms / abbreviations (AI, DX, APP, GMS, KPI, ERP, AEON, IoT, RPA, BI, SaaS, etc.):
   - Translate ONLY the Japanese/Chinese parts.
   - Keep the English part AS-IS, in its original position.
   - Example (Japanese -> Chinese): "店舗DX" -> "门店DX" ✓   (NOT "门店数字化转型" ✗)
   - Example (Japanese -> Chinese): "AI発注最適化" -> "AI订货优化" ✓
   - Example (Japanese -> Chinese): "セルフレジ" -> "自助收银" ✓ (no English to preserve)
3. Keep product names, model numbers, version strings, URLs unchanged.

Return ONLY a valid JSON dictionary Object. Keys are source terms, values are translations.

Content:
{combined_text}
"""
    try:
        response = client.chat.completions.create(
            model=LARGE_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        glossary_json = response.choices[0].message.content or "{}"
        glossary = json.loads(glossary_json)
        print(f"[+] 术语库生成成功，共 {len(glossary)} 条")
        for k, v in list(glossary.items())[:10]:
            print(f"    - {k} => {v}")
        return glossary
    except Exception as e:
        print(f"[-] 术语库生成失败，跳过: {e}")
        return {}


def _has_cjk(text):
    """判断文本是否含有需要翻译的 CJK 字符（日文/中文）"""
    return bool(_CJK_RE.search(text))


def _is_suspected_lazy_translation(src, dst, target_lang):
    """检测疑似偷懒输出（原样返回、目标为中文时残留日文假名）。"""
    if not isinstance(dst, str):
        return True

    s = (src or "").strip()
    d = dst.strip()
    if not d:
        return True

    if s and d == s:
        return True

    if target_lang == "Japanese":
        # Japanese and Chinese share Hanzi. For QA, be conservative but sensitive:
        # 1) any simplified-only char is a strong under-translation signal;
        # 2) high Hanzi overlap with source suggests copy-through.
        if _SIMPLIFIED_ONLY_RE.search(d):
            return True

        src_hanzi = "".join(_HANZI_RE.findall(s))
        dst_hanzi = "".join(_HANZI_RE.findall(d))
        if len(src_hanzi) >= 8 and dst_hanzi:
            from collections import Counter
            common = sum((Counter(src_hanzi) & Counter(dst_hanzi)).values())
            overlap = common / max(1, len(src_hanzi))
            if overlap >= 0.78:
                return True
            if overlap >= 0.68 and not _JP_KANA_RE.search(d):
                return True

    if target_lang == "Chinese" and _JP_KANA_RE.search(d):
        return True

    return False


def _chat_with_model_fallback(messages, response_format, temperature, prefer_large=False):
    """按顺序尝试小模型候选，全部失败后回退到大模型。"""
    if prefer_large:
        candidates = [LARGE_MODEL] + [SMALL_MODEL] + [m for m in SMALL_MODEL_FALLBACKS if m != SMALL_MODEL]
    else:
        candidates = [SMALL_MODEL] + [m for m in SMALL_MODEL_FALLBACKS if m != SMALL_MODEL]
        if LARGE_MODEL not in candidates:
            candidates.append(LARGE_MODEL)

    # Skip disabled / known unavailable deployments to reduce noisy retries.
    candidates = [m for m in candidates if m and m not in DISABLED_MODEL_NAMES]
    if not candidates:
        candidates = [LARGE_MODEL]

    last_error = None
    for model_name in candidates:
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
                response_format=response_format,
                temperature=temperature,
            )
            return response, model_name
        except Exception as e:
            last_error = e
            print(f"    [!] 模型 {model_name} 调用失败，尝试下一个候选: {e}")

    raise RuntimeError(f"所有模型候选均不可用: {last_error}")


def _resolve_speed_options(speed_mode):
    return resolve_speed_options(speed_mode)


def _resolve_parallel_workers(speed_mode):
    mode = (speed_mode or "balanced").lower()
    if mode == "fast":
        return 6
    if mode == "strict":
        return 2
    return 4


def _collect_glossary_violations(translations, glossary, target_lang, sources=None):
    """Detect items that violate glossary constraints.

    If sources is provided, only terms that appear in source text are checked,
    and a violation is recorded when the expected glossary value is missing.
    """
    if not glossary:
        return {}

    violations = {}
    for key, expected in glossary.items():
        if not key:
            continue
        for tid, translated_text in translations.items():
            if not isinstance(translated_text, str):
                continue

            src_text = ""
            if isinstance(sources, dict):
                src_text = sources.get(tid, "") or ""

            if src_text:
                # Enforce only when source actually contains the glossary key.
                if key not in src_text:
                    continue
                if expected and expected not in translated_text:
                    violations.setdefault(tid, []).append(key)
            else:
                # Fallback behavior for legacy callers without source context.
                if key in translated_text:
                    violations.setdefault(tid, []).append(key)
    return violations


def _repair_suspicious_outputs(outputs, sources, glossary, target_lang, batch_number):
    """【修复阶段】：针对疑似偷懒翻译的条目，调用大模型二次修复。"""
    if not outputs or not sources:
        return outputs

    glossary_violations = _collect_glossary_violations(
        outputs,
        glossary,
        target_lang,
        sources=sources,
    )

    suspicious_items = []
    for tid, translated_text in outputs.items():
        source_text = sources.get(tid, "")
        has_glossary_issue = tid in glossary_violations
        if _is_suspected_lazy_translation(source_text, translated_text, target_lang) or has_glossary_issue:
            suspicious_items.append((tid, source_text, translated_text))

    if not suspicious_items:
        return outputs

    print(f"      [!] 批次 {batch_number} 检测到 {len(suspicious_items)} 条疑似未翻译条目，调用大模型二次修复...")

    repaired = {}
    for tid, src, dst in suspicious_items:
        glossary_str = json.dumps(glossary, ensure_ascii=False) if glossary else "{}"
        prompt = f"""Fix this bad translation. Source ({target_lang}): {src}
Current output: {dst}
Glossary: {glossary_str}

Rules:
- Translate FULLY into {target_lang}
- Follow glossary strictly
- Keep line breaks and structure
- Return ONLY the corrected translation"""

        try:
            response, model_used = _chat_with_model_fallback(
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "text"},
                temperature=0.3,
                prefer_large=True,  # Use large model for repairs
            )
            fixed = response.choices[0].message.content.strip()
            if fixed and fixed != dst:
                repaired[tid] = fixed
                print(f"        [+] {tid}: {dst[:30]}... => {fixed[:30]}...")
        except Exception as e:
            print(f"        [-] {tid} 修复失败: {e}")

    # Merge repaired back into outputs
    outputs.update(repaired)
    return outputs


def _enforce_glossary_terms_for_item(translated_text, source_text, glossary, target_lang):
    """Post-translation glossary enforcement: substitute known glossary terms back if missed."""
    if not glossary or not isinstance(translated_text, str):
        return translated_text

    result = translated_text
    for key, value in glossary.items():
        if not key or not value:
            continue
        if key in source_text and value not in result and key in result:
            result = result.replace(key, value)
    return result


def _detect_translation_source_language(texts):
    han_hits = 0
    kana_hits = 0
    latin_hits = 0

    for text in texts:
        if not isinstance(text, str):
            continue
        if _HANZI_RE.search(text):
            han_hits += 1
        if _JP_KANA_RE.search(text):
            kana_hits += 1
        if re.search(r"[A-Za-z]", text):
            latin_hits += 1

    if han_hits > 0:
        return "Chinese"
    if kana_hits > 0:
        return "Japanese"
    if latin_hits > 0:
        return "English"
    return "Unknown"


def _encode_line_break_tokens(text):
    """Replace line breaks with stable tokens so the model can preserve structure."""
    if not isinstance(text, str) or not text:
        return text, []

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    tokens = []
    out = []
    token_idx = 0

    for ch in normalized:
        if ch in ("\n", "\v"):
            tokens.append(ch)
            out.append(f"[[LB{token_idx}]]")
            token_idx += 1
        else:
            out.append(ch)

    return "".join(out), tokens


def _decode_line_break_tokens(text, lb_tokens):
    if not isinstance(text, str) or not lb_tokens:
        return text

    restored = text
    for idx, ch in enumerate(lb_tokens):
        restored = restored.replace(f"[[LB{idx}]]", ch)
    return restored


def _force_restore_line_breaks_like_source(source_text, translated_text):
    """Fallback: if line breaks are lost, split translated text into source-like line count."""
    if not isinstance(source_text, str) or not isinstance(translated_text, str):
        return translated_text

    src_breaks = [ch for ch in source_text if ch in ("\n", "\v")]
    if not src_breaks:
        return translated_text

    if any(ch in translated_text for ch in ("\n", "\v")):
        return translated_text

    line_count = len(src_breaks) + 1
    if line_count <= 1:
        return translated_text

    src_lines = re.split(r"[\n\v]", source_text)
    if not src_lines:
        return translated_text

    weights = [max(len(x.strip()), 1) for x in src_lines]
    total_weight = sum(weights) or line_count
    total_len = len(translated_text)

    segments = []
    cursor = 0
    for i in range(line_count):
        if i == line_count - 1:
            segments.append(translated_text[cursor:])
            break
        take = max(1, round(total_len * (weights[i] / total_weight)))
        end = min(total_len - (line_count - i - 1), cursor + take)
        segments.append(translated_text[cursor:end])
        cursor = end

    rebuilt = []
    for i, seg in enumerate(segments):
        rebuilt.append(seg)
        if i < len(src_breaks):
            rebuilt.append(src_breaks[i])
    return "".join(rebuilt)








def translate_batch(batch_items, glossary, target_lang, max_retries=2, enable_quality_gate=True, batch_number=0, prefer_large_model=False):
    """【第二步】：Batch translation with quality gates and repair stages.
    
    Args:
        prefer_large_model: If True, skip small model and use large model directly (从根源解决)
    """
    if not batch_items:
        return {}, None

    lb_tokens_by_id = {}
    source_text_by_id = {}
    source_payload = ""
    
    for item in batch_items:
        tid = str(item["id"])
        source_text_by_id[tid] = item["text"]
        encoded_text, lb_tokens = _encode_line_break_tokens(item["text"])
        lb_tokens_by_id[tid] = lb_tokens
        source_payload += f'<t id="{item["id"]}">{encoded_text}</t>\n'

    glossary_str = json.dumps(glossary, ensure_ascii=False) if glossary else "{}"
    expected_ids = [str(item["id"]) for item in batch_items]

    # Determine source language heuristic from the actual source texts.
    source_lang = _detect_translation_source_language(source_text_by_id.values())
    
    system_prompt = f"""You are a professional business document translator specializing in {source_lang} ↔ {target_lang} translation.

SOURCE LANGUAGE: {source_lang}
TARGET LANGUAGE: {target_lang}
Glossary (MUST follow): {glossary_str}

CRITICAL INSTRUCTIONS:
1. ⚠️  TRANSLATE EVERY SINGLE WORD from {source_lang} into {target_lang}. NO EXCEPTIONS.
2. Do NOT return text that is identical to the source. Always translate.
3. Strictly follow the glossary when provided. Do not skip glossary terms.
4. Keep English acronyms (AI, DX, APP, IoT, RPA, etc.), product names, URLs, version strings unchanged.
5. Preserve ALL line-break tokens [[LBn]] exactly as they appear.
6. Format: Return ONLY valid JSON dict with same IDs as input: {{"<id>": "<translated_text>", ...}}

TRANSLATION QUALITY CRITERIA:
- Full and complete translation required
- No mixture of {source_lang} and {target_lang}
- Maintain original meaning and structure
- Professional business terminology"""

    for attempt in range(max_retries):
        try:
            if prefer_large_model:
                # 【从根源解决】：直接用大模型，跳过小模型
                print(f"      [*] 批次 {batch_number}: 使用大模型进行第一轮翻译（跳过小模型）")
                response, used_model = _chat_with_model_fallback(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": source_payload},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.3,
                    prefer_large=True,  # 强制使用大模型
                )
            else:
                # 常规流程：用小模型，但提高温度让它更敢翻译
                response, used_model = _chat_with_model_fallback(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": source_payload},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.5,  # 增加到 0.5，让模型更有信心翻译而不是保守地原样返回
                )
            content = response.choices[0].message.content or "{}"
            result = json.loads(content)

            normalized_result = {}
            for tid in expected_ids:
                raw_dst = result.get(tid, "")
                if isinstance(raw_dst, str):
                    decoded = _decode_line_break_tokens(raw_dst, lb_tokens_by_id.get(tid, []))
                    decoded = _force_restore_line_breaks_like_source(source_text_by_id.get(tid, ""), decoded)
                    # Post-translation glossary enforcement
                    decoded = _enforce_glossary_terms_for_item(decoded, source_text_by_id.get(tid, ""), glossary, target_lang)
                    normalized_result[tid] = decoded
                else:
                    normalized_result[tid] = raw_dst

            # Quality gate: repair suspicious outputs
            if enable_quality_gate and normalized_result:
                normalized_result = _repair_suspicious_outputs(
                    normalized_result, 
                    source_text_by_id, 
                    glossary, 
                    target_lang, 
                    batch_number
                )

            return normalized_result, used_model
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"    [-] Batch translation error (attempt {attempt + 1}): {e}, retrying...")
                time.sleep(2)
            else:
                print(f"    [-] Batch translation failed after {max_retries} attempts: {e}")
                return {}, None

    return {}, None



def translate_items_in_parallel(
    text_items,
    glossary,
    target_lang,
    speed_mode="balanced",
    max_retries=2,
    batch_size=20,
    enable_quality_gate=True,
    prefer_large_model=False,
    progress_callback=None,
    progress_stage="调用模型并行翻译中...",
    log_prefix="[*]",
):
    translated_dict = {}
    used_models = set()
    last_model_used = None
    if not text_items:
        return translated_dict, last_model_used, sorted(used_models)

    batches = [text_items[i: i + batch_size] for i in range(0, len(text_items), batch_size)]
    total_batches = len(batches)
    workers = min(_resolve_parallel_workers(speed_mode), total_batches)

    print(f"{log_prefix} 并发翻译启动: workers={workers}, batches={total_batches}")
    if prefer_large_model:
        print(f"{log_prefix} 【从根源解决】使用大模型直接翻译，跳过小模型")

    completed = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                translate_batch,
                batch,
                glossary,
                target_lang,
                max_retries,
                enable_quality_gate,
                idx + 1,
                prefer_large_model,  # 传递参数
            ): (idx + 1, batch)
            for idx, batch in enumerate(batches)
        }

        for future in as_completed(futures):
            batch_no, batch = futures[future]
            try:
                result, used_model = future.result()
            except Exception as e:
                print(f"{log_prefix} 批次 {batch_no}/{total_batches} 并发执行异常: {e}")
                result, used_model = {}, None

            for k, v in result.items():
                try:
                    translated_dict[int(k)] = v
                except (ValueError, TypeError):
                    continue

            completed += 1
            if used_model:
                used_models.add(used_model)
                last_model_used = used_model
            if progress_callback:
                progress_callback(progress_stage, completed, total_batches, model=used_model)
            print(f"{log_prefix} 批次完成 {batch_no}/{total_batches} ({len(batch)}条), model={used_model or 'unknown'}")

    return translated_dict, last_model_used, sorted(used_models)


def apply_font(run, font_name):
    """应用东亚字体"""
    if not font_name:
        return
    run.font.name = font_name
    rPr = run._r.get_or_add_rPr()
    for old_ea in rPr.findall(qn("a:ea")):
        rPr.remove(old_ea)
    ea = parse_xml(
        f'<a:ea typeface="{font_name}" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"/>'
    )
    rPr.append(ea)


def _emu_to_pt(emu_val):
    return (emu_val or 0) / 12700.0


def _get_run_font_size_pt(run, default_pt=14.0):
    try:
        if run.font and run.font.size:
            return float(run.font.size.pt)
    except Exception:
        pass
    return default_pt


def _estimate_shape_capacity_chars(shape, paragraph, base_font_pt):
    """Rough capacity estimate used for overflow risk detection."""
    if not shape or not getattr(shape, "has_text_frame", False):
        return None
    try:
        tf = shape.text_frame
        width_pt = _emu_to_pt(shape.width) - _emu_to_pt(tf.margin_left) - _emu_to_pt(tf.margin_right)
        height_pt = _emu_to_pt(shape.height) - _emu_to_pt(tf.margin_top) - _emu_to_pt(tf.margin_bottom)
        if width_pt <= 1 or height_pt <= 1:
            return None

        # CJK average width around 0.95em, line height around 1.25em.
        chars_per_line = max(1, int(width_pt / max(5.0, base_font_pt * 0.95)))
        max_lines = max(1, int(height_pt / max(8.0, base_font_pt * 1.25)))
        return chars_per_line * max_lines
    except Exception:
        return None


def _is_overflow_risky(src_text, dst_text, shape, paragraph, base_font_pt):
    if not dst_text:
        return False
    src_len = max(1, len((src_text or "").strip()))
    dst_len = len(dst_text.strip())
    if dst_len <= src_len:
        return False

    cap = _estimate_shape_capacity_chars(shape, paragraph, base_font_pt)
    if cap is None:
        # Conservative fallback: only mark very large growth as risky.
        return dst_len >= int(src_len * 1.8)

    # Risk when text grows substantially and approaches/exceeds estimated capacity.
    return (dst_len >= int(src_len * 1.35) and dst_len >= int(cap * 0.85)) or dst_len > cap


def _dedupe_leading_year_from_prefix(prefix_text, translated_text):
    """Avoid duplicated years like '20262026年...' when prefix already contains the year.

    This happens when the paragraph keeps non-CJK prefix runs (e.g. "1.2026") while
    translated text also starts with the same year.
    """
    if not isinstance(prefix_text, str) or not isinstance(translated_text, str):
        return translated_text

    prefix = prefix_text.strip()
    if not prefix:
        return translated_text

    # Use the last 4-digit year in prefix as duplication anchor.
    year_matches = list(re.finditer(r"\d{4}", prefix))
    if not year_matches:
        return translated_text

    year = year_matches[-1].group(0)
    # Only consider it a prefix year when it appears near the tail.
    if year not in prefix[-8:]:
        return translated_text

    m = re.match(rf"^(\s*){re.escape(year)}", translated_text)
    if not m:
        return translated_text

    # Remove duplicated leading year from translated text; keep trailing '年' if present.
    keep_leading_ws = m.group(1)
    trimmed = translated_text[m.end():]
    return keep_leading_ws + trimmed


def _repair_paragraph_layout(pointer, translated_text, target_lang):
    paragraph = pointer["paragraph"]
    first_idx = pointer["first_cjk_idx"]
    shape = pointer.get("shape")

    if first_idx >= len(paragraph.runs):
        return False

    target_font = get_target_font_name(target_lang, content_type="presentation")
    run = paragraph.runs[first_idx]
    base_pt = _get_run_font_size_pt(run, default_pt=14.0)

    # Enable built-in fit strategy first.
    if shape and getattr(shape, "has_text_frame", False):
        try:
            tf = shape.text_frame
            tf.word_wrap = True
            tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        except Exception:
            pass

    cap = _estimate_shape_capacity_chars(shape, paragraph, base_pt)
    new_pt = base_pt
    if cap and cap > 0:
        growth = max(1.0, len(translated_text) / cap)
        if growth > 1.0:
            # Shrink proportionally but keep readability floor.
            new_pt = max(8.0, min(base_pt, base_pt / (growth ** 0.55)))

    try:
        run.font.size = Pt(new_pt)
    except Exception:
        pass
    apply_font(run, target_font)
    return True


def _collect_paragraph(paragraph, text_items, pointers, idx_ref, owner_shape=None):
    """收集段落文本：从第一个含 CJK 的 run 开始，避免把 ❶❻ 等前缀符号发给 AI。"""
    all_runs = paragraph.runs

    first_cjk_idx = None
    for i, r in enumerate(all_runs):
        if _has_cjk(r.text):
            first_cjk_idx = i
            break

    if first_cjk_idx is None:
        return

    cjk_text = "".join(r.text for r in all_runs[first_cjk_idx:]).strip()
    if not cjk_text:
        return

    text_items.append({"id": idx_ref[0], "text": cjk_text})
    pointers[idx_ref[0]] = {
        "paragraph": paragraph,
        "first_cjk_idx": first_cjk_idx,
        "shape": owner_shape,
        "source_text": cjk_text,
    }
    idx_ref[0] += 1


def collect_paragraphs_from_shape(shape, text_items, para_pointers, idx_ref):
    """递归收集 shape 中所有段落 / runs"""
    if shape.has_text_frame:
        for paragraph in shape.text_frame.paragraphs:
            _collect_paragraph(paragraph, text_items, para_pointers, idx_ref, owner_shape=shape)
    if shape.has_table:
        for row in shape.table.rows:
            for cell in row.cells:
                for paragraph in cell.text_frame.paragraphs:
                    _collect_paragraph(paragraph, text_items, para_pointers, idx_ref, owner_shape=shape)
    if shape.shape_type == 6:  # MSO_SHAPE_TYPE.GROUP
        for sub in shape.shapes:
            collect_paragraphs_from_shape(sub, text_items, para_pointers, idx_ref)


def translate_ppt_presentation(input_path, output_path, target_lang="Japanese", speed_mode="balanced", progress_callback=None):
    print(f"[*] 加载 PPT: {input_path}")
    prs = Presentation(input_path)

    mode_opts = _resolve_speed_options(speed_mode)
    batch_size = mode_opts["batch_size"]
    max_retries = mode_opts["max_retries"]
    prefer_large_model = mode_opts.get("prefer_large_model", False)  # 新增：读取配置
    print(
        f"[*] 速度模式: {speed_mode} | batch_size={batch_size} | max_retries={max_retries}"
    )
    if prefer_large_model:
        print(f"[*] 【从根源解决】：优先使用大模型第一轮翻译")

    text_items = []
    para_pointers = {}  # id -> (paragraph, first_cjk_run_idx)
    idx_ref = [0]

    for slide in prs.slides:
        for shape in slide.shapes:
            collect_paragraphs_from_shape(shape, text_items, para_pointers, idx_ref)

    if not text_items:
        print("[!] 未发现任何文本，直接保存。")
        prs.save(output_path)
        return

    just_texts = [item["text"] for item in text_items]
    glossary = generate_glossary(just_texts, target_lang)
    glossary = sanitize_glossary_for_target(glossary, target_lang, just_texts)

    total_batches = (len(text_items) + batch_size - 1) // batch_size
    print(f"[*] 共发现 {len(text_items)} 个文本碎片，合并分 {total_batches} 批发送...")

    t0 = time.time()
    translated_dict, last_model_used, used_models = translate_items_in_parallel(
        text_items,
        glossary,
        target_lang,
        speed_mode=speed_mode,
        max_retries=max_retries,
        batch_size=batch_size,
        enable_quality_gate=True,
        prefer_large_model=prefer_large_model,  # 传递配置
        progress_callback=progress_callback,
        progress_stage="调用模型并行翻译中...",
        log_prefix="[PPT]",
    )

    missing_ids_initial = [item["id"] for item in text_items if item["id"] not in translated_dict]
    if missing_ids_initial:
        print(f"[PPT] 首轮存在 {len(missing_ids_initial)} 个缺失片段，启动单独补翻一轮...")
        missing_items = [item for item in text_items if item["id"] in missing_ids_initial]
        retry_batch_size = min(8, batch_size)
        retry_dict, retry_last_model, retry_models = translate_items_in_parallel(
            missing_items,
            glossary,
            target_lang,
            speed_mode=speed_mode,
            max_retries=1,
            batch_size=retry_batch_size,
            enable_quality_gate=True,
            prefer_large_model=True,  # 补翻一定要用大模型
            progress_callback=progress_callback,
            progress_stage="缺失片段补翻中...",
            log_prefix="[PPT][补翻]",
        )
        if retry_dict:
            translated_dict.update(retry_dict)
            if retry_last_model:
                last_model_used = retry_last_model
            if retry_models:
                used_models = sorted(set(used_models).union(set(retry_models)))
            remaining_after_retry = sum(1 for item in text_items if item["id"] not in translated_dict)
            print(f"[PPT] 补翻结束，剩余缺失 {remaining_after_retry} 个片段。")
        else:
            print("[PPT] 补翻未获得可用结果，将按后续缺失率规则处理。")

    # Hard-fail when no model response is available, to avoid "completed but untranslated" outputs.
    if not translated_dict:
        raise RuntimeError(
            "模型调用失败：未返回任何翻译结果（可能是网络/防火墙 403）。任务已中止。"
        )

    if progress_callback and last_model_used:
        progress_callback("调用模型并行翻译中...", total_batches, total_batches, model=last_model_used)
    if used_models:
        print(f"[PPT] 本次任务命中模型: {', '.join(used_models)}")

    elapsed = time.time() - t0
    print(f"[*] LLM 阶段耗时: {elapsed:.1f}s")

    font_name = get_target_font_name(target_lang, content_type="presentation")
    missing = 0
    repaired = 0
    total_items = len(text_items)

    for idx, item in enumerate(text_items, 1):
        if progress_callback and idx % max(1, total_items // 20) == 0:
            progress_callback("排版回填阶段", idx, total_items)
            
        t_id = item["id"]
        original = item["text"]
        new_text = translated_dict.get(t_id)
        if new_text is None:
            missing += 1
            new_text = original

        pointer = para_pointers[t_id]
        paragraph = pointer["paragraph"]
        first_cjk_idx = pointer["first_cjk_idx"]
        all_runs = paragraph.runs
        if not all_runs or first_cjk_idx >= len(all_runs):
            continue

        prefix_text = "".join((r.text or "") for r in all_runs[:first_cjk_idx])
        new_text = _dedupe_leading_year_from_prefix(prefix_text, new_text)

        all_runs[first_cjk_idx].text = new_text
        apply_font(all_runs[first_cjk_idx], font_name)
        for j in range(first_cjk_idx + 1, len(all_runs)):
            all_runs[j].text = ""

        base_pt = _get_run_font_size_pt(all_runs[first_cjk_idx], default_pt=14.0)
        if _is_overflow_risky(pointer.get("source_text", original), new_text, pointer.get("shape"), paragraph, base_pt):
            if _repair_paragraph_layout(pointer, new_text, target_lang):
                repaired += 1

    missing_ratio = (missing / total_items) if total_items else 0.0
    if missing_ratio >= 0.15:
        raise RuntimeError(
            f"翻译不完整：{missing}/{total_items} 个文本碎片未获得翻译结果（{missing_ratio:.0%}）。任务已中止。"
        )

    if missing > 0:
        print(f"[!] 有 {missing} 个文本碎片AI未返回，已保留原文。")
    if repaired > 0:
        print(f"[PPT] 已触发自动排版修复 {repaired} 处（超框风险检测）。")

    save_path = output_path
    attempt = 0
    while True:
        try:
            prs.save(save_path)
            print(f"[*] 批量处理型 PPT 翻译完成，已保存至: {save_path}")
            break
        except PermissionError:
            attempt += 1
            base2, ext2 = os.path.splitext(output_path)
            save_path = f"{base2}_{attempt}{ext2}"
            print(f"[!] 文件被占用，改存至: {save_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="PPT 调试入口（与 Web 服务保持一致的处理链）"
    )
    parser.add_argument("input_file", help="待翻译的 PPTX 文件路径")
    parser.add_argument(
        "target_lang",
        nargs="?",
        default="Chinese",
        choices=["Chinese", "English", "Japanese"],
        help="目标语言，默认 Chinese",
    )
    parser.add_argument(
        "--speed_mode",
        default="balanced",
        choices=["fast", "balanced", "strict"],
        help="速度模式，默认 balanced",
    )

    args = parser.parse_args()

    # 延迟导入，避免模块初始化阶段产生循环依赖。
    from main import process_single_file

    result = process_single_file(
        args.input_file,
        args.target_lang,
        speed_mode=args.speed_mode,
    ) or {}

    if result.get("success"):
        print(f"[CLI] 完成，输出文件: {result.get('output_path')}")
        sys.exit(0)

    print(f"[CLI] 失败: {result.get('error', 'unknown error')}")
    sys.exit(1)

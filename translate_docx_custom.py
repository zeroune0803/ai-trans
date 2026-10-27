import os
import math
from docx import Document
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph
from docx.shared import Pt

from translate_ppt_batch import (
    generate_glossary,
    translate_items_in_parallel,
)
from rules import (
    get_target_font_name,
    resolve_speed_options,
    contains_hanzi,
    has_kana,
    looks_untranslated_cn_in_ja,
    cleanup_japanese_text,
    sanitize_glossary_for_target,
)


def _contains_hanzi(text):
    return contains_hanzi(text)


def _has_kana(text):
    return has_kana(text)


def _looks_untranslated_cn_in_ja(text):
    return looks_untranslated_cn_in_ja(text)


def _cleanup_japanese_text(text):
    return cleanup_japanese_text(text)


def _sanitize_glossary_for_target(glossary, target_lang, source_texts=None):
    return sanitize_glossary_for_target(glossary, target_lang, source_texts)


def _resolve_para_dominant_font_size_pt(para, fallback=11.0):
    sizes = []
    for run in para.runs:
        try:
            if run.font and run.font.size:
                sizes.append(float(run.font.size.pt))
        except Exception:
            continue
    if not sizes:
        return fallback
    return max(sizes)


def _apply_font(run, font_name):
    if not font_name:
        return
    run.font.name = font_name
    r_pr = run._element.get_or_add_rPr()
    r_pr.rFonts.set(qn("w:eastAsia"), font_name)


def _is_para_in_table_cell(para):
    node = para._p
    while node is not None:
        if getattr(node, "tag", "") == qn("w:tc"):
            return True
        node = node.getparent()
    return False


def _resolve_run_font_size_pt(run, fallback=11.0):
    try:
        if run.font and run.font.size:
            return float(run.font.size.pt)
    except Exception:
        pass
    return fallback


def _maybe_repair_docx_paragraph_layout(para, run, src_text, dst_text):
    """Best-effort overflow prevention for long translated text in constrained DOCX areas."""
    src_len = max(1, len((src_text or "").strip()))
    dst_len = len((dst_text or "").strip())
    if dst_len <= src_len:
        return False

    in_table = _is_para_in_table_cell(para)
    growth = dst_len / src_len
    # In flowing body text Word auto-wraps; tables are much more fragile.
    risky = growth >= (1.25 if in_table else 1.75)
    if not risky:
        return False

    base_pt = _resolve_run_font_size_pt(run, fallback=11.0)
    # Adaptive shrink with readability floor.
    ratio = max(1.0, growth)
    target_pt = max(8.0 if in_table else 9.0, min(base_pt, base_pt / (ratio ** 0.52)))
    try:
        run.font.size = Pt(target_pt)
    except Exception:
        pass

    try:
        pf = para.paragraph_format
        if in_table:
            pf.line_spacing = 1.0
            pf.space_before = Pt(0)
            pf.space_after = Pt(0)
    except Exception:
        pass

    return True


def _collect_paragraphs(element, parent, text_items, pointers, idx_ref):
    for p in element.xpath(".//w:p"):
        para = Paragraph(p, parent)
        if not para.runs:
            continue

        full_text = "".join(r.text for r in para.runs).strip()
        if not full_text:
            continue

        text_items.append({"id": idx_ref[0], "text": full_text})
        pointers[idx_ref[0]] = para
        idx_ref[0] += 1


def translate_docx_document(
    input_file,
    output_file,
    target_lang="Chinese",
    speed_mode="balanced",
    progress_callback=None,
):
    print(f"正在加载 Word 文件: {input_file}")
    doc = Document(input_file)

    text_items = []
    pointers = {}
    idx_ref = [0]

    _collect_paragraphs(doc.element, doc._body, text_items, pointers, idx_ref)
    for section in doc.sections:
        if section.header is not None:
            _collect_paragraphs(section.header._element, section.header, text_items, pointers, idx_ref)
        if section.footer is not None:
            _collect_paragraphs(section.footer._element, section.footer, text_items, pointers, idx_ref)

    if not text_items:
        print("[DOCX] 未发现可翻译文本，直接保存")
        doc.save(output_file)
        return

    mode_opts = resolve_speed_options(speed_mode)
    batch_size = mode_opts["batch_size"]
    max_retries = mode_opts["max_retries"]
    enable_quality_gate = mode_opts["enable_quality_gate"]

    source_texts = [x["text"] for x in text_items]
    glossary = generate_glossary(source_texts, target_lang)
    glossary = _sanitize_glossary_for_target(glossary, target_lang, source_texts)

    translated, last_model_used, used_models = translate_items_in_parallel(
        text_items,
        glossary,
        target_lang,
        speed_mode=speed_mode,
        max_retries=max_retries,
        enable_quality_gate=enable_quality_gate,
        batch_size=batch_size,
        progress_callback=progress_callback,
        progress_stage="调用模型并行翻译中...",
        log_prefix="[DOCX]",
    )
    total_batches = (len(text_items) + batch_size - 1) // batch_size
    if progress_callback and last_model_used:
        progress_callback("调用模型并行翻译中...", total_batches, total_batches, model=last_model_used)
    if used_models:
        print(f"[DOCX] 本次任务命中模型: {', '.join(used_models)}")

    font_name = get_target_font_name(target_lang, content_type="word")

    total_items = len(text_items)
    repaired = 0
    correction_candidates = []
    for idx, item in enumerate(text_items, 1):
        if progress_callback and idx % max(1, total_items // 20) == 0:
            progress_callback("段落排版回填阶段", idx, total_items)

        para = pointers[item["id"]]
        if not para.runs:
            continue

        new_text = translated.get(item["id"], item["text"])
        if target_lang == "Japanese":
            new_text = _cleanup_japanese_text(new_text)
        dominant_pt = _resolve_para_dominant_font_size_pt(para, fallback=11.0)
        para.runs[0].text = new_text
        _apply_font(para.runs[0], font_name)
        try:
            if target_lang == "Japanese":
                # Keep first-pass output readable and prevent accidental tiny-font collapse.
                para.runs[0].font.size = Pt(max(10.5, dominant_pt))
        except Exception:
            pass
        if _maybe_repair_docx_paragraph_layout(para, para.runs[0], item["text"], new_text):
            repaired += 1
        if target_lang == "Japanese" and _looks_untranslated_cn_in_ja(new_text):
            correction_candidates.append(
                {
                    "id": item["id"],
                    "text": new_text,
                    "source": item["text"],
                }
            )
        for run in para.runs[1:]:
            run.text = ""

    if target_lang == "Japanese" and correction_candidates:
        print(f"[DOCX] 检测到中文残留段落 {len(correction_candidates)} 条，执行二次纠错清洗")
        unique_fix_items = []
        unique_map = {}
        for item in correction_candidates:
            key = (item.get("text") or "").strip()
            if not key:
                continue
            if key in unique_map:
                continue
            uid = len(unique_fix_items)
            unique_map[key] = uid
            unique_fix_items.append({"id": uid, "text": key})

        fix_translated, _, _ = translate_items_in_parallel(
            unique_fix_items,
            {},
            target_lang,
            speed_mode="strict",
            max_retries=2,
            enable_quality_gate=True,
            batch_size=max(5, min(20, len(unique_fix_items))),
            progress_callback=progress_callback,
            progress_stage="日文残留纠错阶段",
            log_prefix="[DOCX-FIX]",
        )
        fixed = 0
        for item in correction_candidates:
            para = pointers[item["id"]]
            if not para.runs:
                continue
            key = (item.get("text") or "").strip()
            uid = unique_map.get(key)
            candidate_raw = fix_translated.get(uid, item["text"]) if uid is not None else item["text"]
            candidate = _cleanup_japanese_text(candidate_raw)
            if _looks_untranslated_cn_in_ja(candidate) and not _looks_untranslated_cn_in_ja(item["text"]):
                candidate = item["text"]
            para.runs[0].text = candidate
            _apply_font(para.runs[0], font_name)
            fixed += 1
        print(f"[DOCX] 二次纠错清洗完成，更新 {fixed} 条段落")

    if repaired > 0:
        print(f"[DOCX] 已触发自动排版修复 {repaired} 处（超框/拥挤风险）。")

    print(f"保存翻译完毕的新文件到: {output_file}")
    doc.save(output_file)
    print("Word翻译任务完成！")


if __name__ == "__main__":
    input_word = "test.docx"
    output_word = "test_translated.docx"
    if os.path.exists(input_word):
        translate_docx_document(input_word, output_word, target_lang="Japanese")
    else:
        print(f"测试文件 {input_word} 不存在，请放入测试文件。")

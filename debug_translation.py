#!/usr/bin/env python3
"""Debug script to diagnose translation issues"""

import json
import os
from translate_ppt_batch import generate_glossary, translate_batch, _encode_line_break_tokens
from rules import sanitize_glossary_for_target

# Test data: real untranslated Chinese text that should fail without glossary
test_texts = [
    "前端开发最佳实践",
    "需要集印花来享受优惠",
    "速配服务可在24小时内完成",
    "DX转型正在进行中",
    "数据分析和AI应用",
]

print("=" * 60)
print("DEBUG: Translation System Diagnostic")
print("=" * 60)

# Step 1: Generate glossary
print("\n[STEP 1] 生成术语表...")
glossary = generate_glossary(test_texts, "Japanese")
print(f"✓ Generated {len(glossary)} terms")
if glossary:
    print("\nGenerated glossary:")
    for k, v in list(glossary.items())[:15]:
        print(f"  - {k:20} => {v}")
else:
    print("⚠ WARNING: Glossary is empty!")

# Step 2: Check if it contains critical terms
print("\n[STEP 2] 检查术语表是否包含关键词...")
critical_terms = ["前端", "集印花", "速配", "DX"]
missing = [t for t in critical_terms if t not in glossary]
if missing:
    print(f"⚠ MISSING TERMS: {missing}")
else:
    print("✓ All critical terms found in glossary")

# Step 3: Test translation with glossary
print("\n[STEP 3] 测试翻译质量...")
sanitized = sanitize_glossary_for_target(glossary, "Japanese")
print(f"✓ Sanitized glossary: {len(sanitized)} terms")

batch_items = [
    {"id": i, "text": text}
    for i, text in enumerate(test_texts)
]

print(f"\n输入文本:")
for item in batch_items:
    print(f"  [{item['id']}] {item['text']}")

try:
    result, _ = translate_batch(batch_items, sanitized, "Japanese", enable_quality_gate=False)
    print(f"\n✓ 翻译完成，{len(result)} 条成功")
    
    print(f"\n输出文本:")
    for item in batch_items:
        tid = str(item['id'])
        output = result.get(tid, "❌ MISSING")
        
        # Check if Chinese characters remain
        chinese_chars = [c for c in output if '\u4e00' <= c <= '\u9fff']
        if chinese_chars and output != "❌ MISSING":
            print(f"  [{tid}] {output}")
            print(f"       ⚠ UNTRANSLATED CHINESE: {set(chinese_chars)}")
        else:
            print(f"  [{tid}] {output}")
            
except Exception as e:
    print(f"❌ Translation failed: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)

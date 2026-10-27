#!/usr/bin/env python3
"""Analyze translation quality of PPT file"""

from pptx import Presentation
import re

file_path = r"C:\Users\DMC86124042\Downloads\diag_strict_output.pptx"
prs = Presentation(file_path)

print("=" * 80)
print(f"文件: {file_path.split(chr(92))[-1]}")
print(f"总幻灯片数: {len(prs.slides)}")
print("=" * 80)

# Regex to detect Chinese characters
chinese_pattern = re.compile(r'[\u4e00-\u9fff]')
japanese_hiragana = re.compile(r'[\u3041-\u3096]')
japanese_katakana = re.compile(r'[\u30a1-\u30fa]')

chinese_count = 0
jp_count = 0
total_text = 0
untranslated_examples = []

for slide_idx, slide in enumerate(list(prs.slides)[:10], 1):  # Check first 10 slides
    print(f"\n【幻灯片 {slide_idx}】")
    
    for shape_idx, shape in enumerate(slide.shapes):
        if hasattr(shape, "text") and shape.text.strip():
            text = shape.text[:80]  # First 80 chars
            
            # Count Chinese, Japanese
            cn = len(chinese_pattern.findall(shape.text))
            jp_hiragana = len(japanese_hiragana.findall(shape.text))
            jp_katakana = len(japanese_katakana.findall(shape.text))
            
            chinese_count += cn
            jp_count += jp_hiragana + jp_katakana
            total_text += 1
            
            if cn > 0:
                print(f"  ⚠️  包含中文 ({cn}个): {text}...")
                if len(untranslated_examples) < 5:
                    untranslated_examples.append(shape.text[:100])
            elif jp_hiragana > 0 or jp_katakana > 0:
                print(f"  ✓ 日文: {text}...")
            else:
                print(f"  ⓘ 其他: {text}...")

print("\n" + "=" * 80)
print(f"统计 (前10张幻灯片):")
print(f"  包含中文的文本框: {chinese_count}")
print(f"  日文字符数: {jp_count}")
print(f"  文本框总数: {total_text}")
print("=" * 80)

if untranslated_examples:
    print("\n❌ 未翻译的中文例子:")
    for i, ex in enumerate(untranslated_examples, 1):
        print(f"  {i}. {ex}")

if chinese_count > 0:
    print(f"\n⚠️  警告: 仍有 {chinese_count} 个中文字符残留未翻译！")
else:
    print("\n✓ 没有检测到中文残留")

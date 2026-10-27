#!/usr/bin/env python3
"""Test glossary enforcement logic without calling LLM"""

import re
from translate_ppt_batch import _enforce_glossary_terms_for_item

# Simulate glossary
glossary = {
    "前端": "フロントエンド",
    "后端": "バックエンド",
    "DX": "DX",  # Keep acronyms
    "集印花": "スタンプを集める",
    "速配": "迅速配送",
}

test_cases = [
    # Case 1: Untranslated Chinese in output (should be fixed)
    {
        "src": "前端开发最佳实践",
        "dst": "前端開発ベストプラクティス",  # 前端 not translated
        "expected": "フロントエンド開発ベストプラクティス",
        "description": "Untranslated Chinese term in Japanese output",
    },
    # Case 2: Already translated (should not change)
    {
        "src": "前端开发",
        "dst": "フロントエンド開発",  # Already correct
        "expected": "フロントエンド開発",
        "description": "Already correctly translated",
    },
    # Case 3: Multiple untranslated terms
    {
        "src": "前端和后端",
        "dst": "前端とバックエンド",  # 前端 not translated
        "expected": "フロントエンドとバックエンド",
        "description": "Multiple terms, one untranslated",
    },
    # Case 4: DX acronym should stay
    {
        "src": "店舗DX",
        "dst": "店舗DX",  # Should remain DX
        "expected": "店舗DX",
        "description": "English acronym should not be translated",
    },
]

print("=" * 70)
print("Testing _enforce_glossary_terms_for_item() Logic")
print("=" * 70)

all_pass = True
for i, test in enumerate(test_cases, 1):
    print(f"\nTest {i}: {test['description']}")
    print(f"  Source: {test['src']}")
    print(f"  Input:  {test['dst']}")
    
    result = _enforce_glossary_terms_for_item(test['dst'], test['src'], glossary, "Japanese")
    
    print(f"  Output: {result}")
    print(f"  Expect: {test['expected']}")
    
    if result == test['expected']:
        print("  ✓ PASS")
    else:
        print("  ✗ FAIL")
        all_pass = False

print("\n" + "=" * 70)
if all_pass:
    print("✓ All tests passed!")
else:
    print("❌ Some tests failed - logic needs fixing")

# Debug: Test the actual condition
print("\n" + "=" * 70)
print("DEBUG: Analyzing condition 'if src_term in src_text and src_term in out'")
print("=" * 70)

src_text = "前端开发最佳实践"
dst_text = "前端開発ベストプラクティス"
term_key = "前端"
term_val = "フロントエンド"

print(f"\nSource text: {src_text}")
print(f"Output text: {dst_text}")
print(f"Glossary: {term_key} -> {term_val}")
print(f"\nCondition check:")
print(f"  {term_key} in src_text: {term_key in src_text}")
print(f"  {term_key} in out_text: {term_key in dst_text}")
print(f"  Both true? {term_key in src_text and term_key in dst_text}")

if term_key in src_text and term_key in dst_text:
    print(f"\n✓ Condition would trigger replacement:")
    print(f"  '{dst_text}' → '{dst_text.replace(term_key, term_val)}'")
else:
    print(f"\n❌ Condition would NOT trigger (this is the problem!)")

#!/usr/bin/env python3
"""
测试诊断工具 - 模拟几种未翻译的情况
"""

import sys
sys.path.insert(0, 'e:\\Dev\\translate_agent')

from diagnose_untranslated import TranslationDiagnostics

def test_case_1():
    """情况1：大模型根本没翻译（返回空）"""
    print("\n" + "="*80)
    print("【测试 1】大模型根本没翻译 - 返回空值")
    print("="*80)
    
    diag = TranslationDiagnostics(target_lang="Chinese")
    
    source = "店舗DXの推進により"
    translated = ""  # 空的！
    
    diag.diagnose_single_item(source, translated, item_id=1)
    diag.print_summary()


def test_case_2():
    """情况2：大模型原样返回（没有翻译）"""
    print("\n" + "="*80)
    print("【测试 2】大模型原样返回 - 未翻译")
    print("="*80)
    
    diag = TranslationDiagnostics(target_lang="Chinese")
    
    source = "AI発注最適化"
    translated = "AI発注最適化"  # 完全相同！
    
    diag.diagnose_single_item(source, translated, item_id=2)
    diag.print_summary()


def test_case_3():
    """情况3：残留日文假名（中文混日文）"""
    print("\n" + "="*80)
    print("【测试 3】残留日文假名 - 混合未翻译")
    print("="*80)
    
    diag = TranslationDiagnostics(target_lang="Chinese")
    
    source = "AI発注最適化"
    translated = "AI发布最适化と店舗DX"  # 混合了日文假名"と"
    
    diag.diagnose_single_item(source, translated, item_id=3)
    diag.print_summary()


def test_case_4():
    """情况4：Hanzi 重叠过高（翻译时直接拷贝了源）"""
    print("\n" + "="*80)
    print("【测试 4】Hanzi 重叠分析 - 高重叠度")
    print("="*80)
    
    diag = TranslationDiagnostics(target_lang="Japanese")
    
    source = "品質改善活動の推進"
    translated = "品質改善活動的推进"  # 保留了大部分汉字，只改了个别字
    
    diag.diagnose_single_item(source, translated, item_id=4)
    diag.print_summary()


def test_case_5():
    """情况5：正确翻译 - 应该通过质量门禁"""
    print("\n" + "="*80)
    print("【测试 5】正确翻译 - 通过质量门禁")
    print("="*80)
    
    diag = TranslationDiagnostics(target_lang="Chinese")
    
    source = "AI發注最適化により"
    translated = "通过 AI 订货优化"
    
    diag.diagnose_single_item(source, translated, item_id=5)
    diag.print_summary()


def test_case_6():
    """情况6：二次修复前后对比"""
    print("\n" + "="*80)
    print("【测试 6】二次修复机制 - 疑似偷懒 → 修复")
    print("="*80)
    print()
    print("这个测试会展示二次修复的实际效果（需要 API 调用）")
    print()
    
    diag = TranslationDiagnostics(target_lang="Chinese")
    
    # 模拟一个被标记为疑似偷懒但能被修复的案例
    source = "自動発注システムの構築"
    suspicious_output = "自动發行システムの構築"  # 部分翻译、混杂
    
    diag.diagnose_single_item(source, suspicious_output, item_id=6)
    
    print("\n📝 说明: 如果疑似偷懒，系统会调用大模型二次修复")
    print("   大模型会尝试完全翻译这个条目")
    diag.print_summary()


if __name__ == "__main__":
    print("\n" + "="*80)
    print("诊断工具演示 - 6 种未翻译情况")
    print("="*80)
    
    test_case_1()  # 返回空
    test_case_2()  # 原样返回
    test_case_3()  # 残留假名
    test_case_4()  # Hanzi 重叠
    test_case_5()  # 正确翻译
    test_case_6()  # 二次修复演示
    
    print("\n" + "="*80)
    print("诊断完成！")
    print("="*80)
    print()
    print("💡 如何使用诊断工具：")
    print()
    print("1. 单条诊断:")
    print("   python diagnose_untranslated.py --target Chinese \\")
    print("     --source '日本語テキスト' --translated '翻訳結果'")
    print()
    print("2. 交互模式（询问输入）:")
    print("   python diagnose_untranslated.py --target Chinese")
    print()
    print("3. 批量 JSON 诊断:")
    print("   python diagnose_untranslated.py --target Chinese \\")
    print("     --json '[{\"id\":1, \"source\":\"日本語\", \"translated\":\"翻訳\"}]'")

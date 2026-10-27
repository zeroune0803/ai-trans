#!/usr/bin/env python3
"""
诊断工具：追踪未翻译条目从源到输出的完整流程
用来确定是：大模型不翻译 vs 二次修复失败 vs 回填失败
"""

import sys
import json
sys.path.insert(0, 'e:\\Dev\\translate_agent')

from translate_ppt_batch import (
    generate_glossary,
    translate_batch,
    _is_suspected_lazy_translation,
    _repair_suspicious_outputs,
    _enforce_glossary_terms_for_item,
)

class TranslationDiagnostics:
    def __init__(self, target_lang="Chinese"):
        self.target_lang = target_lang
        self.glossary = {}
        self.diagnostics = []
        
    def log_step(self, stage, item_id, details):
        """记录每个阶段的诊断信息"""
        self.diagnostics.append({
            "stage": stage,
            "item_id": item_id,
            "details": details
        })
        print(f"[诊断] {stage:20} | 条目 {item_id}: {details[:60]}...")
        
    def diagnose_single_item(self, source_text, translated_text, item_id=1):
        """诊断单个条目的翻译过程"""
        print(f"\n{'='*80}")
        print(f"诊断条目 {item_id}")
        print(f"{'='*80}")
        print(f"源文本: {source_text[:80]}")
        print(f"模型输出: {translated_text[:80]}")
        print()
        
        # 第一步：检查大模型是否翻译
        print(f"【第一步】大模型是否返回翻译？")
        if not translated_text:
            print("  ❌ 模型返回空值 - 这是根本原因")
            self.log_step("model_output", item_id, "EMPTY")
            return
        elif translated_text == source_text:
            print("  ❌ 模型输出与源相同 - 未翻译")
            self.log_step("model_output", item_id, "IDENTICAL")
        else:
            print(f"  ✓ 模型有返回内容 ({len(translated_text)} 字符)")
            self.log_step("model_output", item_id, f"OK ({len(translated_text)} chars)")
        
        print()
        print(f"【第二步】质量门禁检测 - 是否被判定为'疑似偷懒'？")
        is_suspicious = _is_suspected_lazy_translation(
            source_text, translated_text, self.target_lang
        )
        if is_suspicious:
            print(f"  ⚠️  被判定为 SUSPICIOUS")
            self.log_step("quality_gate", item_id, "SUSPICIOUS")
            
            # 分析原因
            self._analyze_suspicious_reason(source_text, translated_text)
        else:
            print(f"  ✓ 通过质量门禁")
            self.log_step("quality_gate", item_id, "PASS")
            return  # 如果通过就不需要后续修复
        
        print()
        print(f"【第三步】二次修复 - 如果被检测为疑似，大模型会修复吗？")
        
        # 模拟二次修复（但实际调用需要 API）
        outputs = {str(item_id): translated_text}
        sources = {str(item_id): source_text}
        
        try:
            repaired = _repair_suspicious_outputs(
                outputs, sources, self.glossary, self.target_lang, batch_number=1
            )
            if str(item_id) in repaired and repaired[str(item_id)] != translated_text:
                print(f"  ✓ 二次修复成功")
                print(f"    原: {translated_text[:40]}")
                print(f"    修: {repaired[str(item_id)][:40]}")
                self.log_step("repair", item_id, f"SUCCESS: {repaired[str(item_id)][:30]}")
                translated_text = repaired[str(item_id)]
            else:
                print(f"  ❌ 二次修复未改变结果")
                self.log_step("repair", item_id, "NO_CHANGE")
        except Exception as e:
            print(f"  ❌ 二次修复异常: {e}")
            self.log_step("repair", item_id, f"ERROR: {str(e)[:30]}")
        
        print()
        print(f"【第四步】术语强制替换")
        if self.glossary:
            before = translated_text
            translated_text = _enforce_glossary_terms_for_item(
                translated_text, source_text, self.glossary, self.target_lang
            )
            if before != translated_text:
                print(f"  ✓ 术语替换生效")
                print(f"    原: {before[:40]}")
                print(f"    后: {translated_text[:40]}")
                self.log_step("glossary_enforce", item_id, f"CHANGED")
            else:
                print(f"  - 术语替换无改变")
                self.log_step("glossary_enforce", item_id, "NO_CHANGE")
        else:
            print(f"  - 没有术语库")
            
        print()
        print(f"【最终结果】")
        print(f"  源文本: {source_text[:50]}")
        print(f"  最终翻译: {translated_text[:50]}")
        
        return translated_text
    
    def _analyze_suspicious_reason(self, source_text, translated_text):
        """分析为什么被判定为疑似偷懒"""
        import re
        from collections import Counter
        
        _HANZI_RE = re.compile(r'[\u4e00-\u9fff]')
        _JP_KANA_RE = re.compile(r'[\u3041-\u3096\u30a1-\u30fa\u30fd-\u30ff]')
        _SIMPLIFIED_ONLY_RE = re.compile(
            r"[这后发图书体门风广东业车云龙头务数烟译简检测页签线为国汉标录审阶场景说产构图"
            r"全务调动踪陈点户网类据协账链销触单购运设监损鲜预侧报导览财级页钟册录宽"
            r"台现亿况队块态]"
        )
        
        s = source_text.strip()
        d = translated_text.strip()
        
        # 原因 1：输出为空
        if not d:
            print("    原因: 输出为空")
            return
        
        # 原因 2：完全相同
        if d == s:
            print("    原因: 输出与源相同（原样返回）")
            return
        
        # 原因 3：简体字残留（针对日文 -> 中文）
        if self.target_lang == "Chinese":
            if _JP_KANA_RE.search(d):
                print("    原因: 残留日文假名（未翻译）")
                return
        
        # 原因 4：Hanzi 重叠（针对中文 -> 日文）
        if self.target_lang == "Japanese":
            if _SIMPLIFIED_ONLY_RE.search(d):
                print("    原因: 检测到简体字（中文未翻译）")
                return
            
            src_hanzi = "".join(_HANZI_RE.findall(s))
            dst_hanzi = "".join(_HANZI_RE.findall(d))
            
            if len(src_hanzi) >= 8 and dst_hanzi:
                common = sum((Counter(src_hanzi) & Counter(dst_hanzi)).values())
                overlap = common / max(1, len(src_hanzi))
                
                print(f"    原因: Hanzi 重叠分析")
                print(f"      源 Hanzi: {len(src_hanzi)} 个")
                print(f"      输出 Hanzi: {len(dst_hanzi)} 个")
                print(f"      重叠度: {overlap:.1%}")
                
                if overlap >= 0.78:
                    print(f"      → 重叠度 >= 0.78，判定为未翻译")
                elif overlap >= 0.68 and not _JP_KANA_RE.search(d):
                    print(f"      → 重叠度 >= 0.68 且无假名，判定为可能未翻译")
                    
        print("    原因: 未知")
    
    def batch_diagnose(self, text_items):
        """批量诊断多个条目"""
        print(f"\n{'='*80}")
        print(f"批量诊断 {len(text_items)} 条条目")
        print(f"{'='*80}\n")
        
        # 第一步：生成术语库
        print("[步骤 1/3] 生成术语库...")
        all_texts = [item.get("source", "") for item in text_items if item.get("source")]
        if all_texts:
            self.glossary = generate_glossary(all_texts, self.target_lang)
        
        print(f"[步骤 2/3] 进行批量翻译...")
        batch_items = [
            {"id": item["id"], "text": item.get("source", "")}
            for item in text_items
        ]
        
        # 调用翻译
        translated_dict, used_model = translate_batch(
            batch_items,
            self.glossary,
            self.target_lang,
            max_retries=2,
            enable_quality_gate=True,
            batch_number=0
        )
        
        print(f"\n[步骤 3/3] 诊断每条条目...")
        for item in text_items:
            item_id = item["id"]
            source_text = item.get("source", "")
            translated_text = translated_dict.get(item_id, "")
            
            print(f"\n条目 {item_id}:")
            print(f"  源: {source_text[:50]}")
            print(f"  译: {translated_text[:50] if translated_text else '[无翻译]'}")
            
            if not translated_text:
                print(f"  → ❌ 未翻译（模型无返回）")
            elif translated_text == source_text:
                print(f"  → ❌ 未翻译（原样返回）")
            else:
                print(f"  → ✓ 已翻译")
    
    def print_summary(self):
        """打印诊断总结"""
        print(f"\n{'='*80}")
        print("诊断总结")
        print(f"{'='*80}\n")
        
        for diag in self.diagnostics:
            print(f"{diag['stage']:20} | 条目 {diag['item_id']:3} | {diag['details'][:60]}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="诊断工具：追踪未翻译条目")
    parser.add_argument("--target", default="Chinese", choices=["Chinese", "Japanese", "English"],
                       help="目标语言")
    parser.add_argument("--source", type=str, help="源文本（单个条目）")
    parser.add_argument("--translated", type=str, help="已翻译文本（单个条目）")
    parser.add_argument("--json", type=str, help="JSON 格式的多条目（格式: [{id, source, translated}]）")
    
    args = parser.parse_args()
    
    diag = TranslationDiagnostics(target_lang=args.target)
    
    if args.source and args.translated:
        # 单条诊断
        print(f"目标语言: {args.target}\n")
        diag.diagnose_single_item(args.source, args.translated, item_id=1)
        diag.print_summary()
    
    elif args.json:
        # 批量诊断
        try:
            items = json.loads(args.json)
            diag.batch_diagnose(items)
            diag.print_summary()
        except json.JSONDecodeError as e:
            print(f"❌ JSON 解析失败: {e}")
            sys.exit(1)
    
    else:
        # 交互模式
        print(f"诊断工具 - 追踪未翻译条目")
        print(f"目标语言: {args.target}\n")
        
        source = input("请输入源文本: ").strip()
        if not source:
            print("❌ 源文本不能为空")
            sys.exit(1)
        
        translated = input("请输入翻译结果: ").strip()
        
        diag.diagnose_single_item(source, translated, item_id=1)
        diag.print_summary()

import os
import time
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from openai import OpenAI

# 配置大模型 API，这里使用标准的 OpenAI 格式
# 针对 Azure 的代理或直连，有时需要 api-key 头
API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
_BASE_URL = (os.getenv("OPENAI_BASE_URL") or "").strip()
_client_kwargs = {"api_key": API_KEY, "default_headers": {"api-key": API_KEY}}
if _BASE_URL:
    _client_kwargs["base_url"] = _BASE_URL
client = OpenAI(**_client_kwargs)  # 兼容 Azure 鉴权头
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o") # 如果有特定的部署名，请在此替换！例如 'gpt-4o' 或 'gpt-35-turbo'

def call_llm_translate(text, target_lang="Chinese", max_retries=5):
    """调用大模型进行翻译"""
    if not text or not text.strip():
        return text
        
    prompt = f"Translate the following text to {target_lang}. Only return the translation, no extra explanations or quotes:\n\n{text}"
    
    # 动态根据目标语言调整系统提示词，防止提示词冲突导致翻译失败
    if target_lang == "Japanese":
        system_content = (
            "You are a professional Japanese business translator for PPT/Word/Excel documents. "
            "Priority 1: Preserve the original meaning completely and accurately - never drop key terms. "
            "Priority 2: Be as concise as possible to fit within tight slide/table cell layouts: prefer Japanese kanji compounds (漢語) over hiragana phrasing (e.g. use 実施 not 行う, use 確認 not 確かめる), drop optional structural particles (の, を) in headings/table headers when natural, and avoid redundant words. "
            "Priority 3: Try to keep the translated character count within +/-20% of the source. If extra characters are truly required for semantic completeness, allow it - never sacrifice meaning for length. "
            "Use natural native Japanese expressions. Do not copy Chinese kanji directly if they are unnatural in Japanese (e.g., translate '未尽事宜' or '未决事项' to '残課題' or '未決事項'). Maintain the original professional tone."
        )
    elif target_lang == "Chinese":
        system_content = "You are a professional translator translating foreign text to fluent, native Simplified Chinese. Maintain the original professional tone and formatting."
    else:
        system_content = "You are a professional translator. Maintain the original professional tone."

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2, # 翻译任务推荐较低的temperature
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "cooldown" in error_msg:
                import re
                reset_seconds = 22 # 默认22秒
                match = re.search(r"'reset_seconds':\s*(\d+)", error_msg)
                if match:
                    reset_seconds = int(match.group(1)) + 2 # 多加2秒缓冲
                print(f"\n⚠️ 触发API请求限速 (429)! 等待 {reset_seconds} 秒后重试 (第 {attempt+1}/{max_retries} 次)...")
                time.sleep(reset_seconds)
            elif attempt < max_retries - 1:
                print(f"\n⚠️ API异常: {error_msg}，等待 3 秒后重试 (第 {attempt+1}/{max_retries} 次)...")
                time.sleep(3)
            else:
                print(f"\n❌ Translation failed for text: '{text[:20]}...'. Error: {e}")
                return text
    return text

def translate_paragraph(paragraph, target_lang):
    """
    【核心格式还原逻辑】翻译段落并尽量保留格式
    """
    full_text = paragraph.text.strip()
    if not full_text:
        return

    translated_text = call_llm_translate(full_text, target_lang=target_lang)
    print(f"  [Translated]: {full_text[:30]}... -> {translated_text[:30]}...")
    
    if paragraph.runs:
        # 将翻译结果放在第一个 run 中
        paragraph.runs[0].text = translated_text
        
        # 根据目标语言限定输出字体
        font_name = "Meiryo UI" if target_lang == "Japanese" else ("微软雅黑" if target_lang == "Chinese" else None)
        if font_name:
            paragraph.runs[0].font.name = font_name
            # 对于PPT中的中日韩字体，也需要额外强制设置东亚字体 (<a:ea>)
            from pptx.oxml import parse_xml
            from pptx.oxml.ns import qn
            rPr = paragraph.runs[0]._r.get_or_add_rPr()
            # 移除旧的ea（如果存在），防止冲突
            for old_ea in rPr.findall(qn('a:ea')):
                rPr.remove(old_ea)
            ea = parse_xml(f'<a:ea typeface="{font_name}" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"/>')
            rPr.append(ea)

        # 清空其他 run 的内容，不要直接删除 run 会破坏内部 XML 顺序
        for i in range(1, len(paragraph.runs)):
            paragraph.runs[i].text = ""

def process_shape(shape, target_lang):
    """【核心节点遍历逻辑】递归处理形状，覆盖文本框、表格、组合图形"""
    
    # 1. 基础文本框 (普通形状、独立文本框)
    if shape.has_text_frame:
        for paragraph in shape.text_frame.paragraphs:
            translate_paragraph(paragraph, target_lang)
            
    # 2. 表格 (Table) - 遍历所有行和单元格
    elif shape.has_table:
        for row in shape.table.rows:
            for cell in row.cells:
                if cell.text_frame:
                    for paragraph in cell.text_frame.paragraphs:
                        translate_paragraph(paragraph, target_lang)
                        
    # 3. 组合图形 (Group Shape) - PPT里非常高频的操作，需要递归解析内部对象
    elif shape.shape_type == MSO_SHAPE_TYPE.GROUP:
        for child_shape in shape.shapes:
            process_shape(child_shape, target_lang)

def translate_presentation(input_file, output_file, target_lang="Chinese"):
    print(f"正在加载 PPT 文件: {input_file}")
    prs = Presentation(input_file)
    
    total_slides = len(prs.slides)
    for i, slide in enumerate(prs.slides):
        print(f"正在处理第 {i+1}/{total_slides} 页幻灯片...")
        for shape in slide.shapes:
            process_shape(shape, target_lang)
            
        # 防止大模型 API 并发过度被限流
        time.sleep(0.5) 
        
    print(f"\n保存翻译完毕的新文件到: {output_file}")
    try:
        prs.save(output_file)
        print("翻译任务完成！")
    except PermissionError:
        # 如果文件被占用（比如用户在PPT软件里打开了它）
        import datetime
        timestamp = datetime.datetime.now().strftime("%H%M%S")
        fallback_file = output_file.replace(".pptx", f"_{timestamp}.pptx")
        print(f"⚠️ 无法覆盖原文件（可能被其他程序/Office打开中），将另存为: {fallback_file}")
        prs.save(fallback_file)
        print("翻译任务完成！")

if __name__ == "__main__":
    # 使用指南:
    # 1. 在同级目录放一个测试用的 test.pptx
    # 2. 填入上方的 API_KEY
    # 3. 运行此文件
    input_ppt = "test.pptx"
    output_ppt = "test_translated.pptx"
    
    if os.path.exists(input_ppt):
        translate_presentation(input_ppt, output_ppt, target_lang="Japanese")
    else:
        print(f"测试文件 {input_ppt} 不存在，请丢一个测试 PPT 到该目录下运行测试。")

import os

filepath = r'e:\Dev\translate_agent\translate_ppt_custom.py'
with open(filepath, 'r', encoding='utf-8') as f:
    text = f.read()

# Replace the previously inserted block
old_block = '''        # 根据目标语言限定输出字体
        font_name = "Meiryo UI" if target_lang == "Japanese" else ("微软雅黑" if target_lang == "Chinese" else None)
        if font_name:
            paragraph.runs[0].font.name = font_name
            # 对于PPT中的中日韩字体，也需要额外强制设置东亚字体 (<a:ea>)
            from pptx.oxml import parse_xml
            rPr = paragraph.runs[0]._r.get_or_add_rPr()
            ea = parse_xml(f'<a:ea typeface="{font_name}" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"/>')
            rPr.append(ea)'''

new_block = '''        # 根据目标语言限定输出字体
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
            rPr.append(ea)'''

if old_block in text:
    print('Match found ppt custom update')
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(text.replace(old_block, new_block))
else:
    print('No match ppt custom')

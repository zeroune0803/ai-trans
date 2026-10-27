import os

filepath = r'e:\Dev\translate_agent\translate_docx_custom.py'
with open(filepath, 'r', encoding='utf-8') as f:
    text = f.read()

old_block = '''    font_name = "Meiryo UI" if target_lang == "Japanese" else ("微软雅黑" if target_lang == "Chinese" else None)
    if font_name:
        first_run.font.name = font_name
        # Word里面的中日韩字体需要特别指定其属于东亚字体范围
        if first_run._element.rPr is not None:
            first_run._element.rPr.rFonts.set(qn('w:eastAsia'), font_name)'''

new_block = '''    font_name = "Meiryo UI" if target_lang == "Japanese" else ("微软雅黑" if target_lang == "Chinese" else None)
    if font_name:
        first_run.font.name = font_name
        # Word里面的中日韩字体需要特别指定其属于东亚字体范围
        rPr = first_run._element.get_or_add_rPr()
        rPr.rFonts.set(qn('w:eastAsia'), font_name)'''

if old_block in text:
    print('Match found docx')
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(text.replace(old_block, new_block))
else:
    print('No match docx')

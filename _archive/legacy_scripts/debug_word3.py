import os
import tempfile
import docx

upload_dir = os.path.join(tempfile.gettempdir(), 'translate_agent_uploads')
file_path = os.path.join(upload_dir, '個人情報取扱の委託に関する覚書25.08.07.docx')
doc = docx.Document(file_path)

for i, p in enumerate(doc.element.xpath('.//w:p')[:10]):
    print(f"--- Para {i} XML ---")
    xml_str = p.xml
    print(xml_str[:1500])


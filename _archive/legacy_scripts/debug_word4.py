import os
import tempfile
import docx

upload_dir = os.path.join(tempfile.gettempdir(), 'translate_agent_uploads')
file_path = os.path.join(upload_dir, '個人情報取扱の委託に関する覚書25.08.07.docx')
import zipfile
import xml.etree.ElementTree as ET

with zipfile.ZipFile(file_path) as z:
    xml_content = z.read('word/document.xml')
    tree = ET.fromstring(xml_content)
    
    # Let's find all text elements
    for t in tree.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'):
        if t.text and t.text.strip():
            print("FOUND TEXT:", t.text)


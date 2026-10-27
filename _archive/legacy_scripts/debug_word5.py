import os
import tempfile
import zipfile
import xml.etree.ElementTree as ET

upload_dir = os.path.join(tempfile.gettempdir(), 'translate_agent_uploads')
file_path = os.path.join(upload_dir, '個人情報取扱の委託に関する覚書25.08.07.docx')

with zipfile.ZipFile(file_path) as z:
    xml_content = z.read('word/document.xml')
    tree = ET.fromstring(xml_content)
    
    # Check what wraps the first 't' tag
    for t in tree.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'):
        if t.text and '個人情報取扱の委託' in t.text:
            print("Found it!")
            # trace parents
            parent = tree
            r = t
            print(t.tag)

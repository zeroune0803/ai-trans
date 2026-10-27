import os
import tempfile
import docx
from docx.text.run import Run

upload_dir = os.path.join(tempfile.gettempdir(), 'translate_agent_uploads')
file_path = os.path.join(upload_dir, '個人情報取扱の委託に関する覚書25.08.07.docx')
doc = docx.Document(file_path)

missing_text_paras = []
for p in doc.element.xpath('.//w:p'):
    # Extract all text using lxml
    raw_text = "".join(t.text for t in p.xpath('.//w:t') if t.text)
    if raw_text.strip():
        # See how many runs python-docx finds
        para = docx.text.paragraph.Paragraph(p, doc._body)
        if not para.text.strip():
            print(f"FAILED PARAGRAPH: {raw_text[:30]}")
            # Can we use custom run list?
            all_r = p.xpath('.//w:r')
            if all_r:
                print(f"  Found {len(all_r)} w:r tags using xpath!")
                r0 = Run(all_r[0], para)
                print(f"  First run text: {r0.text}")


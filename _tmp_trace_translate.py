import io
import os
import sys
import traceback

os.environ['OPENAI_API_KEY'] = os.environ.get('OPENAI_API_KEY') or 'dummy-key'

sys.path.insert(0, r'e:/Dev/translate_agent')
import app as webapp

webapp.app.testing = True
client = webapp.app.test_client()

try:
    resp = client.post(
        '/translate',
        data={
            'file': (io.BytesIO(b'dummy content'), 'smoke.docx'),
            'target_lang': 'Japanese',
            'speed_mode': 'balanced',
        },
        content_type='multipart/form-data',
    )
    print('STATUS', resp.status_code)
    print('BODY', resp.get_data(as_text=True))
except Exception:
    print(traceback.format_exc())

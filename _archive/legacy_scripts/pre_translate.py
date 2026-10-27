import json
import time
from deep_translator import GoogleTranslator

# Load unique and translated so far
uniq_file = 'e:/Dev/translate_agent/uniq.json'
map_file = 'e:/Dev/translate_agent/trans_map.json'

with open(uniq_file, 'r', encoding='utf-8') as f:
    uniq_texts = json.load(f)

# Load existing translations
trans_map = {}
try:
    with open(map_file, 'r', encoding='utf-8') as f:
        trans_map = json.load(f)
except:
    pass

# Hardcode user preference
trans_map["双社长会"] = "ステコミ会議"

translator = GoogleTranslator(source='zh-CN', target='ja')

modified = False
for text in uniq_texts:
    if text not in trans_map:
        # Pre-process text specific overrides
        t = text.replace("双社长会", "ステコミ会議")
        try:
            print(f"Translating: {text} ...")
            if t == "Gap" or t == "GAP：" or t == "GAP":
                trans_map[text] = t
            elif t == "11%↓":
                trans_map[text] = "11%↓"
            else:
                res = translator.translate(t)
                trans_map[text] = res
            with open(map_file, 'w', encoding='utf-8') as f:
                json.dump(trans_map, f, ensure_ascii=False, indent=2)
            time.sleep(0.5)
        except Exception as e:
            print(f"Failed to translate {text}: {e}")

if modified:
    with open(map_file, 'w', encoding='utf-8') as f:
        json.dump(trans_map, f, ensure_ascii=False, indent=2)

print(f"Total translations available: {len(trans_map)}")

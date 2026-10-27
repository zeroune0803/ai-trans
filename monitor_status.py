#!/usr/bin/env python3
import json
import urllib.request
import time
import sys

task_id = '5d56498d-f1c7-4937-8c37-08b9e5e72c3d'

for i in range(120):
    try:
        r = urllib.request.urlopen(f'http://127.0.0.1:5000/status/{task_id}', timeout=3)
        data = json.loads(r.read())
        status = data.get('status')
        
        print(f"[{i*2:3d}s] Status: {status}", end='')
        
        if status == 'completed':
            print()
            print(json.dumps(data.get('metrics'), indent=2, ensure_ascii=False))
            sys.exit(0)
        
        if 'progress' in data and isinstance(data['progress'], dict):
            p = data['progress']
            print(f" | {p.get('stage', '')} {p.get('percentage', 0)}%")
        else:
            print()
        
        sys.stdout.flush()
    except Exception as e:
        print(f"[{i*2:3d}s] Error: {type(e).__name__}", end='\n')
    
    if i < 119:
        time.sleep(2)

print("Timeout")

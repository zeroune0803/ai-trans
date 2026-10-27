#!/usr/bin/env python3
"""快速检查翻译状态并下载结果"""
import requests
import json
from pathlib import Path

task_id = '517f8e29-a2e1-4a60-aea0-464bd05a8b2c'
api_url = 'http://127.0.0.1:5000'

try:
    # 检查状态
    resp = requests.get(f'{api_url}/status/{task_id}', timeout=5)
    data = resp.json()
    
    print(f"✓ 状态: {data.get('status')}")
    
    if data.get('status') == 'completed':
        print(f"✓ 翻译完成!")
        
        # 打印指标
        if 'metrics' in data:
            print("\n📊 质量指标:")
            for k, v in data['metrics'].items():
                print(f"  - {k}: {v}")
        
        # 下载文件
        print(f"\n📥 下载文件...")
        resp = requests.get(f'{api_url}/download/{task_id}', timeout=30)
        
        if resp.status_code == 200:
            filename = resp.headers.get('Content-Disposition', '').split('filename=')[-1].strip('"\'')
            if not filename:
                filename = f'translated_{task_id[:8]}.pptx'
            
            output = Path.home() / 'Downloads' / filename
            output.write_bytes(resp.content)
            print(f"  → {output}")
            print(f"  → 大小: {len(resp.content) / 1024 / 1024:.2f} MB")
    else:
        print(f"  进度: {data.get('progress', {})}")
        
except Exception as e:
    print(f"✗ 错误: {e}")

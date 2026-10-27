#!/usr/bin/env python3
"""
诊断脚本：通过 Flask API 提交翻译任务并实时监控日志
"""

import json
import time
import urllib.request
import urllib.parse
import io
from pathlib import Path

# Flask API 配置
API_URL = "http://127.0.0.1:5000"
SOURCE_FILE = r"C:\Users\DMC86124042\Downloads\source_for_diagnosis.pptx"
TARGET_LANG = "Japanese"

print("=" * 80)
print("翻译诊断脚本 - 原始文件重新翻译")
print("=" * 80)

# 检查文件
if not Path(SOURCE_FILE).exists():
    print(f"✗ 源文件不存在: {SOURCE_FILE}")
    exit(1)

file_size = Path(SOURCE_FILE).stat().st_size / (1024*1024)  # MB
print(f"\n📄 源文件: {Path(SOURCE_FILE).name}")
print(f"📊 文件大小: {file_size:.1f} MB")
print(f"🎯 目标语言: {TARGET_LANG}")

# 提交翻译任务
print("\n▶️  正在提交翻译任务...")
try:
    with open(SOURCE_FILE, 'rb') as f:
        file_data = f.read()
    
    # 构建 multipart form data
    boundary = '----FormBoundary7MA4YWxkTrZu0gW'
    body = io.BytesIO()
    
    # 添加 target_lang 字段
    body.write(f'--{boundary}\r\n'.encode())
    body.write(b'Content-Disposition: form-data; name="target_lang"\r\n\r\n')
    body.write(f'{TARGET_LANG}\r\n'.encode())
    
    # 添加文件字段
    body.write(f'--{boundary}\r\n'.encode())
    body.write(b'Content-Disposition: form-data; name="file"; filename="source_for_diagnosis.pptx"\r\n')
    body.write(b'Content-Type: application/vnd.openxmlformats-officedocument.presentationml.presentation\r\n\r\n')
    body.write(file_data)
    body.write(f'\r\n--{boundary}--\r\n'.encode())
    
    # 发送请求
    url = f"{API_URL}/translate"
    req = urllib.request.Request(url, data=body.getvalue())
    req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
    
    with urllib.request.urlopen(req, timeout=120) as response:
        result = json.loads(response.read().decode('utf-8'))
        task_id = result.get('task_id')
        print(f"✓ 任务已提交")
        print(f"  Task ID: {task_id}")
        print(f"  Status: {result.get('status')}")
        
except Exception as e:
    print(f"✗ 提交失败: {e}")
    exit(1)

# 实时监控日志
print("\n▶️  实时监控翻译过程（日志）...\n")
print("-" * 80)

log_file = Path("e:/Dev/translate_agent/logs/translate_agent.log")
initial_size = log_file.stat().st_size if log_file.exists() else 0
start_time = time.time()
last_check = 0
found_task = False

while True:
    elapsed = time.time() - start_time
    
    # 每 2 秒检查一次日志
    if time.time() - last_check >= 2:
        try:
            # 读取新日志
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                f.seek(max(0, initial_size - 4096))  # 读最后 4KB
                new_logs = f.read()
                
            # 检查任务相关的日志
            for line in new_logs.split('\n'):
                if task_id in line:
                    found_task = True
                    print(f"[{elapsed:.0f}s] {line}")
                    
                    # 检查是否完成
                    if "completed successfully" in line or "Translation completed" in line:
                        print("-" * 80)
                        print(f"\n✓ 翻译完成！耗时 {elapsed:.1f} 秒\n")
                        exit(0)
                        
        except Exception as e:
            pass
            
        last_check = time.time()
    
    # 超时检查
    if elapsed > 300:  # 5 分钟超时
        print(f"\n✗ 翻译超时（5分钟）")
        exit(1)
    
    time.sleep(1)

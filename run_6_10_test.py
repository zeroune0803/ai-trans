#!/usr/bin/env python3
"""上传文件并运行 6/10 版本翻译"""
import time
import json
from pathlib import Path
import urllib.request
import urllib.parse
import mimetypes

FILE_PATH = r"C:\Users\DMC86124042\Downloads\日本ASPB上半年故障分析品质改善 20260615 (1).pptx"
API = "http://127.0.0.1:5000"

print("="*70)
print("6/10 版本翻译测试 - 日文 PPT → 中文")
print("="*70)
print()

# 上传
file = Path(FILE_PATH)
print(f"📤 上传: {file.name} ({file.stat().st_size/1024/1024:.2f} MB)")

try:
    with open(file, 'rb') as f:
        r = requests.post(f"{API}/translate", 
            files={'file': (file.name, f)},
            data={'target_lang': 'Chinese', 'speed_mode': 'balanced'},
            timeout=10)
    
    if r.status_code != 200:
        print(f"❌ 上传失败: {r.status_code}")
        print(r.text)
        exit(1)
    
    task_id = r.json()['task_id']
    print(f"✅ 上传成功! Task ID: {task_id[:8]}...")
    print()
    
except Exception as e:
    print(f"❌ 异常: {e}")
    exit(1)

# 监控进度
print("⏳ 等待翻译完成...")
print("-"*70)

start = time.time()
while time.time() - start < 300:  # 5 分钟超时
    try:
        r = requests.get(f"{API}/status/{task_id}", timeout=5)
        if r.status_code == 200:
            data = r.json()
            status = data.get('status')
            
            if status == 'completed':
                elapsed = time.time() - start
                print(f"\n✅ 翻译完成! ({elapsed:.1f}s)")
                
                # 显示指标
                if 'metrics' in data:
                    print("\n📊 质量指标 (6/10 版本):")
                    metrics = data['metrics']
                    total_segments = metrics.get('output_segments', 0)
                    unchanged = metrics.get('unchanged_segments', 0)
                    residual = metrics.get('source_residual_segments', 0)
                    
                    if total_segments > 0:
                        unchanged_pct = (unchanged / total_segments) * 100
                        residual_pct = (residual / total_segments) * 100
                        print(f"  - 总分段数: {total_segments}")
                        print(f"  - 未变更段: {unchanged} ({unchanged_pct:.1f}%)")
                        print(f"  - 源残留段: {residual} ({residual_pct:.1f}%)")
                        
                        # 质量评估
                        print("\n📈 质量评估:")
                        if unchanged_pct < 10:
                            print(f"  ✓ 未变更比例 <10% ✓ 通过质量门禁")
                        else:
                            print(f"  ⚠ 未变更比例 {unchanged_pct:.1f}% (阈值: 10%)")
                
                # 下载
                print("\n📥 下载翻译文件...")
                r = requests.get(f"{API}/download/{task_id}", timeout=30)
                
                if r.status_code == 200:
                    filename = f"CN_translated_{Path(file.stem).name}.pptx"
                    output = Path.home() / 'Downloads' / filename
                    output.write_bytes(r.content)
                    print(f"  → {output.name} ({len(r.content)/1024/1024:.2f} MB)")
                else:
                    print(f"  ❌ 下载失败: {r.status_code}")
                
                print()
                print("="*70)
                print("✅ 6/10 版本翻译测试完成")
                print("="*70)
                exit(0)
            
            elif status == 'failed':
                print(f"❌ 翻译失败: {data.get('error')}")
                exit(1)
            
            else:
                # 打印进度
                if 'progress' in data:
                    p = data['progress']
                    if isinstance(p, dict):
                        stage = p.get('stage', '')
                        pct = p.get('percentage', 0)
                        print(f"  {stage}... {pct}%")
    
    except Exception as e:
        print(f"  ⚠ {type(e).__name__}")
    
    time.sleep(1)

print("❌ 超时 (>5分钟)")

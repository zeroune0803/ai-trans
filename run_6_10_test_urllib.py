#!/usr/bin/env python3
"""上传文件并运行 6/10 版本翻译 (使用 urllib)"""
import time
import json
from pathlib import Path
import urllib.request
import urllib.error
import uuid
import io

FILE_PATH = r"C:\Users\DMC86124042\Downloads\日本ASPB上半年故障分析品质改善 20260615 (1).pptx"
API = "http://127.0.0.1:5000"

def upload_file(file_path):
    """上传文件到 Flask API"""
    file = Path(file_path)
    
    # 准备 multipart 表单数据
    boundary = str(uuid.uuid4())
    body = io.BytesIO()
    
    # 添加目标语言字段
    body.write(f'--{boundary}\r\n'.encode())
    body.write(b'Content-Disposition: form-data; name="target_lang"\r\n\r\n')
    body.write(b'Chinese\r\n')
    
    # 添加速度模式字段
    body.write(f'--{boundary}\r\n'.encode())
    body.write(b'Content-Disposition: form-data; name="speed_mode"\r\n\r\n')
    body.write(b'balanced\r\n')
    
    # 添加文件字段
    body.write(f'--{boundary}\r\n'.encode())
    body.write(f'Content-Disposition: form-data; name="file"; filename="{file.name}"\r\n'.encode())
    body.write(b'Content-Type: application/vnd.openxmlformats-officedocument.presentationml.presentation\r\n\r\n')
    
    with open(file, 'rb') as f:
        body.write(f.read())
    
    body.write(f'\r\n--{boundary}--\r\n'.encode())
    
    body_bytes = body.getvalue()
    
    # 发送请求
    req = urllib.request.Request(
        f"{API}/translate",
        data=body_bytes,
        headers={
            'Content-Type': f'multipart/form-data; boundary={boundary}',
            'Content-Length': len(body_bytes)
        }
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            if response.status == 200:
                data = json.loads(response.read().decode())
                return data.get('task_id')
    except urllib.error.URLError as e:
        print(f"❌ 上传失败: {e}")
        return None

def check_status(task_id):
    """检查翻译状态"""
    try:
        with urllib.request.urlopen(f"{API}/status/{task_id}", timeout=5) as response:
            if response.status == 200:
                return json.loads(response.read().decode())
    except Exception:
        pass
    return None

def download_file(task_id, output_path):
    """下载翻译文件"""
    try:
        with urllib.request.urlopen(f"{API}/download/{task_id}", timeout=30) as response:
            if response.status == 200:
                with open(output_path, 'wb') as f:
                    f.write(response.read())
                return True
    except Exception as e:
        print(f"❌ 下载失败: {e}")
    return False

# 主流程
print("="*70)
print("6/10 版本翻译测试 - 日文 PPT → 中文")
print("="*70)
print()

file = Path(FILE_PATH)
print(f"📤 上传: {file.name} ({file.stat().st_size/1024/1024:.2f} MB)")

task_id = upload_file(FILE_PATH)
if not task_id:
    print("❌ 上传失败")
    exit(1)

print(f"✅ 上传成功! Task ID: {task_id[:8]}...")
print()
print("⏳ 等待翻译完成...")
print("-"*70)

start = time.time()
while time.time() - start < 300:
    data = check_status(task_id)
    
    if data:
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
                        print(f"  ✓ 未变更比例 {unchanged_pct:.1f}% < 10% ✓ 通过质量门禁")
                    else:
                        print(f"  ⚠ 未变更比例 {unchanged_pct:.1f}% >= 10% ⚠ 需要改进")
            
            # 下载
            print("\n📥 下载翻译文件...")
            filename = f"CN_translated_{Path(file.stem).name}.pptx"
            output = Path.home() / 'Downloads' / filename
            
            if download_file(task_id, str(output)):
                print(f"  → {output.name} ({output.stat().st_size/1024/1024:.2f} MB)")
            
            print()
            print("="*70)
            print("✅ 6/10 版本翻译测试完成")
            print("="*70)
            exit(0)
        
        elif status == 'failed':
            print(f"❌ 翻译失败: {data.get('error')}")
            exit(1)
        
        elif status == 'processing':
            if 'progress' in data:
                p = data['progress']
                if isinstance(p, dict):
                    stage = p.get('stage', '')
                    pct = p.get('percentage', 0)
                    print(f"  {stage}... {pct}%", end='\r')
    
    time.sleep(1)

print("\n❌ 超时 (>5分钟)")

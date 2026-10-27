#!/usr/bin/env python3
"""通过 Flask API 测试 6/10 版本的翻译效果"""
import requests
import time
import json
from pathlib import Path

API_URL = "http://127.0.0.1:5000"
FILE_PATH = r"C:\Users\DMC86124042\Downloads\日本ASPB上半年故障分析品质改善 20260615 (1).pptx"

def upload_and_translate():
    """上传文件并监控翻译进度"""
    if not Path(FILE_PATH).exists():
        print(f"❌ 文件不存在: {FILE_PATH}")
        return
    
    print(f"📤 上传文件: {Path(FILE_PATH).name}")
    print(f"   大小: {Path(FILE_PATH).stat().st_size / 1024 / 1024:.2f} MB")
    print()
    
    # 上传文件
    with open(FILE_PATH, 'rb') as f:
        files = {
            'file': (Path(FILE_PATH).name, f)
        }
        data = {
            'target_lang': 'Chinese',
            'speed_mode': 'balanced'
        }
        
        try:
            response = requests.post(
                f"{API_URL}/translate",
                files=files,
                data=data,
                timeout=30
            )
            
            if response.status_code != 200:
                print(f"❌ 上传失败 (HTTP {response.status_code})")
                print(response.text)
                return
            
            result = response.json()
            task_id = result.get('task_id')
            print(f"✅ 上传成功!")
            print(f"   Task ID: {task_id}")
            print()
            
        except Exception as e:
            print(f"❌ 上传异常: {e}")
            return
    
    # 监控翻译进度
    print("⏳ 监控翻译进度...")
    print("-" * 60)
    
    max_wait = 600  # 最多等待 10 分钟
    start_time = time.time()
    last_status = None
    
    while time.time() - start_time < max_wait:
        try:
            response = requests.get(
                f"{API_URL}/status/{task_id}",
                timeout=10
            )
            
            if response.status_code == 200:
                status_data = response.json()
                current_status = status_data.get('status')
                
                # 仅在状态改变时打印
                if current_status != last_status:
                    last_status = current_status
                    print(f"状态: {current_status}")
                    
                    if current_status == 'completed':
                        print()
                        print("✅ 翻译完成!")
                        print(f"   用时: {time.time() - start_time:.1f} 秒")
                        print()
                        
                        # 获取详细信息
                        if 'metrics' in status_data:
                            metrics = status_data['metrics']
                            print("📊 质量指标:")
                            for key, value in metrics.items():
                                print(f"   - {key}: {value}")
                        print()
                        
                        # 下载文件
                        download_url = f"{API_URL}/download/{task_id}"
                        print(f"📥 下载链接: {download_url}")
                        print()
                        return
                    
                    elif current_status == 'failed':
                        print(f"错误: {status_data.get('error', 'Unknown')}")
                        return
                
                # 打印进度详情
                if 'progress' in status_data:
                    progress = status_data['progress']
                    if isinstance(progress, dict):
                        stage = progress.get('stage', '')
                        current = progress.get('current', 0)
                        total = progress.get('total', 0)
                        if stage and total > 0:
                            print(f"  → {stage}: {current}/{total}")
        
        except requests.exceptions.RequestException as e:
            print(f"  ⚠️  连接异常 (可能正在处理): {type(e).__name__}")
        
        time.sleep(2)  # 每 2 秒检查一次
    
    print("❌ 翻译超时 (>10分钟)")

if __name__ == "__main__":
    print("=" * 60)
    print("6/10 版本翻译测试")
    print("=" * 60)
    print()
    upload_and_translate()

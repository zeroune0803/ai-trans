import os

content = '''import os
import uuid
import time
import queue
import threading
from flask import Flask, request, render_template, send_file, jsonify
from werkzeug.utils import secure_filename

from main import process_single_file
from pathlib import Path
import tempfile
import shutil

app = Flask(__name__)

UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), 'translate_agent_uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

ALLOWED_EXTENSIONS = {'.pptx', '.docx', '.xlsx'}

task_queue = queue.Queue()
tasks = {}

def allowed_file(filename):
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS

def worker():
    while True:
        task_id = task_queue.get()
        task = tasks.get(task_id)
        if not task:
            task_queue.task_done()
            continue
            
        task['status'] = 'processing'
        input_path = task['input_path']
        target_lang = task['target_lang']
        original_filename = task['original_filename']
        
        base_name, ext = os.path.splitext(input_path)
        output_path = f"{base_name}_{target_lang}{ext}"
        
        try:
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except Exception:
                    pass
            process_single_file(input_path, target_lang)
            
            if os.path.exists(output_path):
                task['status'] = 'completed'
                task['output_path'] = output_path
                task['download_name'] = f"Translated_{target_lang}_{original_filename}"
            else:
                task['status'] = 'failed'
                task['error'] = "Translation completed but output file not found."
        except Exception as e:
            task['status'] = 'failed'
            task['error'] = str(e)
            
        task_queue.task_done()

threading.Thread(target=worker, daemon=True).start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/translate', methods=['POST'])
def translate():
    if 'file' not in request.files:
         return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    if file.filename == '':
         return jsonify({"error": "No selected file"}), 400
         
    target_lang = request.form.get('target_lang', 'Japanese')
    
    if file and allowed_file(file.filename):
        task_id = str(uuid.uuid4())
        original_filename = file.filename
        ext = os.path.splitext(original_filename)[1]
        
        safe_filename = f"{task_id}{ext}"
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
        file.save(input_path)
        
        tasks[task_id] = {
            'id': task_id,
            'status': 'pending',
            'input_path': input_path,
            'target_lang': target_lang,
            'original_filename': original_filename
        }
        
        task_queue.put(task_id)
        
        return jsonify({"task_id": task_id, "message": "Task queued successfully"})
        
    return jsonify({"error": "Unsupported file format"}), 400

@app.route('/status/<task_id>')
def task_status(task_id):
    task = tasks.get(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404
        
    response = {"status": task['status']}
    
    if task['status'] == 'pending':
        try:
            q_list = list(task_queue.queue)
            if task_id in q_list:
                response['position'] = q_list.index(task_id) + 1
            else:
                response['position'] = 1
        except Exception:
            response['position'] = "?"
    elif task['status'] == 'completed':
        response['download_name'] = task['download_name']
    elif task['status'] == 'failed':
        response['error'] = task.get('error', 'Unknown error')
        
    return jsonify(response)

@app.route('/download/<task_id>')
def download(task_id):
    task = tasks.get(task_id)
    if not task or task['status'] != 'completed' or 'output_path' not in task:
        return jsonify({"error": "File not available"}), 404
        
    return send_file(task['output_path'], as_attachment=True, download_name=task['download_name'])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
'''
with open(r'e:\Dev\translate_agent\app.py', 'w', encoding='utf-8') as f:
    f.write(content)

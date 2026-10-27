import os
import uuid
import queue
import threading
import time
import re
import copy
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, render_template, send_file, jsonify

from main import process_single_file
from rules import get_lang_code
from openai import OpenAI

# New: Import configuration, logging, and exceptions
from config import config, validate_config
from logger import setup_logging, get_task_logger
from exceptions import (
    TranslationError, ModelCallError, FileIOError,
    error_message_for_user
)

# Initialize logging and configuration FIRST, before app setup
logger = setup_logging()
logger.info("Flask app initialization starting...")

app = Flask(__name__)

# Validate configuration on startup
if not validate_config():
    logger.error("Configuration validation failed!")
    raise RuntimeError("Invalid configuration")

# Use configuration from config.py instead of hardcoded env vars
UPLOAD_FOLDER = config.upload_folder
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = config.max_upload_size_mb * 1024 * 1024

ALLOWED_EXTENSIONS = {'.pptx', '.docx', '.xlsx'}
ALLOWED_SPEED_MODES = {"fast", "balanced", "strict"}

task_queue = queue.Queue()
tasks = {}

_KANA_RE = re.compile(r"[\u3041-\u3096\u30a1-\u30fa\u30fd-\u30ff]")
_HANZI_RE = re.compile(r"[\u4e00-\u9fff]")
# Heuristic set of simplified-only Chinese chars commonly seen in untranslated filenames.
_SIMPLIFIED_ONLY_RE = re.compile(r"[这后发图书体门风广东业车云龙头务数烟译简检测页签线为国汉标录审]")

# Queue consumer concurrency for backend task processing (from config)
MAX_WORKERS = config.max_workers
worker_executor = None
active_workers = 0
_active_workers_lock = threading.Lock()
tasks_lock = threading.Lock()
cleanup_thread = None
runtime_services_started = False
runtime_services_lock = threading.Lock()

TERMINAL_TASK_STATUSES = {'completed', 'failed'}
TASK_RETENTION_SECONDS = config.task_retention_seconds
TASK_CLEANUP_INTERVAL_SECONDS = config.task_cleanup_interval_seconds

def allowed_file(filename):
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS


def _safe_remove_file(path):
    if not path:
        return
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except Exception:
        pass


def cleanup_expired_tasks_once(now=None):
    now_ts = now if now is not None else time.time()
    expired_tasks = []

    with tasks_lock:
        for task_id, task in list(tasks.items()):
            if task.get('status') not in TERMINAL_TASK_STATUSES:
                continue

            reference_ts = (
                task.get('completed_at')
                or task.get('failed_at')
                or task.get('updated_at')
                or task.get('created_at')
            )
            if reference_ts is None:
                continue
            if (now_ts - reference_ts) < TASK_RETENTION_SECONDS:
                continue

            popped = tasks.pop(task_id, None)
            if popped:
                expired_tasks.append(popped)

    for task in expired_tasks:
        _safe_remove_file(task.get('input_path'))
        _safe_remove_file(task.get('output_path'))


def cleanup_loop():
    while True:
        time.sleep(TASK_CLEANUP_INTERVAL_SECONDS)
        cleanup_expired_tasks_once()


def ensure_runtime_services_started():
    global runtime_services_started
    if runtime_services_started:
        return

    with runtime_services_lock:
        if runtime_services_started:
            return
        init_worker_pool()
        init_cleanup_worker()
        runtime_services_started = True


def log_startup_env_check():
    """Log startup configuration check."""
    key_status = 'configured' if config.openai_api_key else 'missing'
    logger.info(f'[startup-check] OPENAI_API_KEY={key_status}')
    if not config.openai_api_key:
        logger.warning('[startup-check] OPENAI_API_KEY is not set. Translation may fail!')

    logger.info(f'[startup-check] OPENAI_BASE_URL={config.openai_base_url or "(default SDK endpoint)"}')
    logger.info(f'[startup-check] Small model={config.small_model_name}, Large model={config.large_model_name}')
    logger.info(f'[startup-check] Model fallbacks={config.small_model_fallbacks}')
    logger.info(f'[startup-check] Workers={MAX_WORKERS}, Task retention={TASK_RETENTION_SECONDS}s, Cleanup interval={TASK_CLEANUP_INTERVAL_SECONDS}s')
    logger.info(f'[startup-check] Max upload size={config.max_upload_size_mb}MB')
    logger.info(f'[startup-check] Log level={config.log_level}, Log dir={config.log_dir}')


def _build_output_preview(output_path):
    ext = os.path.splitext(output_path)[1].lower()

    if ext == '.pptx':
        from pptx import Presentation

        prs = Presentation(output_path)
        lines = []
        if len(prs.slides) > 0:
            for shape in prs.slides[0].shapes:
                text_frame = getattr(shape, 'text_frame', None)
                if text_frame is not None:
                    for para in text_frame.paragraphs:
                        t = (para.text or '').strip()
                        if t:
                            lines.append(t)
                if len(lines) >= 16:
                    break

        return {
            "type": "text",
            "title": "PPT 首屏预览",
            "summary": f"共 {len(prs.slides)} 页，展示第 1 页部分文本。",
            "lines": lines[:16],
        }

    if ext == '.docx':
        from docx import Document

        d = Document(output_path)
        lines = [(p.text or '').strip() for p in d.paragraphs]
        lines = [x for x in lines if x][:18]
        return {
            "type": "text",
            "title": "Word 预览",
            "summary": "展示文档前几段文本。",
            "lines": lines,
        }

    if ext == '.xlsx':
        from openpyxl import load_workbook

        wb = load_workbook(output_path, read_only=True, data_only=True)
        try:
            ws = wb[wb.sheetnames[0]] if wb.sheetnames else None
            rows = []
            if ws is not None:
                for row in ws.iter_rows(min_row=1, max_row=20, values_only=True):
                    vals = [str(v).strip() for v in row if v is not None and str(v).strip()]
                    if vals:
                        rows.append(' | '.join(vals))
                    if len(rows) >= 12:
                        break

            return {
                "type": "text",
                "title": "Excel 预览",
                "summary": f"工作表: {(ws.title if ws else 'N/A')}，展示前几行非空数据。",
                "lines": rows,
            }
        finally:
            wb.close()

    return {
        "type": "text",
        "title": "预览",
        "summary": "该文件类型暂不支持预览。",
        "lines": [],
    }


def check_filename_target_language(filename_stem, target_lang):
    """Heuristic QA check for whether translated filename matches target language expectations."""
    stem = (filename_stem or "").strip()
    if not stem:
        return False, "文件名为空，无法判断目标语言一致性。"

    if target_lang == "English":
        if _KANA_RE.search(stem) or _HANZI_RE.search(stem):
            return False, "文件名目标语言为 English，但仍包含中/日文字符。"
    elif target_lang == "Chinese":
        if _KANA_RE.search(stem):
            return False, "文件名目标语言为 Chinese，但仍包含日文假名字符。"
    elif target_lang == "Japanese":
        if _SIMPLIFIED_ONLY_RE.search(stem):
            return False, "文件名目标语言为 Japanese，但仍包含简体中文特征字符。"

    return True, ""


def translate_filename(filename, target_lang):
    """Use LLM to translate the filename (without extension) to target language."""
    if not filename or not filename.strip():
        return filename

    def sanitize_name(text):
        cleaned = (text or "").strip()
        for ch in '/\\:*?"<>|':
            cleaned = cleaned.replace(ch, '_')
        cleaned = cleaned.replace(' ', '_')
        cleaned = re.sub(r'_+', '_', cleaned).strip('._')
        return cleaned

    try:
        api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
        if not api_key:
            return filename
        
        base_url = (os.getenv("OPENAI_BASE_URL") or "").strip()
        model = os.getenv("SMALL_MODEL_NAME", "gpt-4.1-mini")
        
        client_kwargs = {"api_key": api_key, "default_headers": {"api-key": api_key}}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = OpenAI(**client_kwargs)

        system_prompt = (
            f"Translate this filename to {target_lang}. "
            "Output ONLY the translated filename, no quotes or markdown. "
            "Keep version numbers, acronyms, and underscores. "
            "Do not use forbidden filename characters."
        )
        
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Translate to {target_lang}: {filename}"}
            ],
            temperature=0.2,
            max_tokens=120,
        )
        
        translated = sanitize_name(response.choices[0].message.content or "")
        return translated if translated else filename
        
    except Exception as e:
        print(f"[!] Filename translation failed: {e}")
        return filename


def process_task(task_id: str):
    """Process a translation task with structured logging and error handling."""
    task_logger = get_task_logger(task_id)
    
    with tasks_lock:
        task = tasks.get(task_id)
    if not task:
        logger.error(f"Task {task_id} not found in registry")
        return

    task_logger.info("Task processing started")
    
    # Atomically update status to 'processing'
    with tasks_lock:
        task['status'] = 'processing'
        task['started_at'] = time.time()
        task['updated_at'] = task['started_at']
    
    input_path = task['input_path']
    target_lang = task['target_lang']
    speed_mode = task.get('speed_mode', 'balanced')
    lang_code = get_lang_code(target_lang)

    try:
        task_logger.debug(f"Input: {input_path}, Target: {target_lang}, Speed: {speed_mode}")
        
        def progress_callback(phase, current, total, model=None):
            now = time.time()
            with tasks_lock:
                live_task = tasks.get(task_id)
                if not live_task:
                    return
                live_task['progress'] = {
                    'phase': phase,
                    'current': current,
                    'total': total,
                    'updated_at': now,
                }
                live_task['updated_at'] = now
                if model:
                    live_task['progress']['model'] = model
                    live_task['last_model_used'] = model
                    live_task.setdefault('models_used', set()).add(model)
            task_logger.debug(f"Progress: {phase} {current}/{total}")

        process_result = process_single_file(
            input_path,
            target_lang,
            speed_mode=speed_mode,
            progress_callback=progress_callback,
        ) or {}

        actual_output_path = process_result.get('output_path')

        if actual_output_path and os.path.exists(actual_output_path):
            completed_at = time.time()
            elapsed = completed_at - task['started_at']
            
            # Translate the output filename to target language
            output_dir = os.path.dirname(actual_output_path)
            new_ext = os.path.splitext(actual_output_path)[1]
            orig_name = os.path.splitext(task.get('original_filename', ''))[0] or 'translated'
            translated_dl_name = translate_filename(orig_name, target_lang)
            
            # Build the properly translated output filename
            final_output_path = os.path.join(output_dir, f"{lang_code}_{translated_dl_name}{new_ext}")
            
            # Rename the output file if translation produced a different name
            if final_output_path != actual_output_path:
                try:
                    if os.path.exists(final_output_path):
                        os.remove(final_output_path)
                    os.rename(actual_output_path, final_output_path)
                    task_logger.info(f"Renamed output file: {os.path.basename(actual_output_path)} → {os.path.basename(final_output_path)}")
                    actual_output_path = final_output_path
                except Exception as e:
                    task_logger.warning(f"Could not rename output file: {e}, using original path")
            
            with tasks_lock:
                task['output_path'] = actual_output_path
                task['download_name'] = f"{lang_code}_{translated_dl_name}{new_ext}"

                filename_ok, filename_issue = check_filename_target_language(translated_dl_name, target_lang)
                quality = process_result.get('quality')
                if not isinstance(quality, dict):
                    quality = {
                        "passed": True,
                        "summary": "已完成基础检查。",
                        "issues": [],
                        "stats": {},
                        "checks_skipped": ["content_qa"],
                    }

                quality.setdefault('issues', [])
                quality.setdefault('stats', {})
                quality['target_lang'] = target_lang
                quality['filename_translation_ok'] = filename_ok
                quality['stats']['filename_translation_mismatch'] = 0 if filename_ok else 1

                if not filename_ok:
                    quality['passed'] = False
                    if filename_issue not in quality['issues']:
                        quality['issues'].append(filename_issue)
                    summary = quality.get('summary', '')
                    if '文件名检查未通过' not in summary:
                        quality['summary'] = (summary + ' 文件名检查未通过，请人工复核。').strip()

                task['filename_translation_ok'] = filename_ok
                task['filename_translation_issue'] = filename_issue
                task['quality'] = quality
                task['speed_mode'] = speed_mode
                if isinstance(task.get('models_used'), set):
                    task['models_used'] = sorted(task['models_used'])
                task['visual_review_required'] = bool(
                    task.get('quality') and not task['quality'].get('passed', False)
                )
                task['completed_at'] = completed_at
                task['updated_at'] = completed_at
                task['status'] = 'completed'
            
            task_logger.info(f"Translation completed successfully in {elapsed:.1f}s")
            
            # Build preview (non-blocking)
            try:
                with tasks_lock:
                    task['preview'] = _build_output_preview(actual_output_path)
                task_logger.debug("Preview generated successfully")
            except Exception as preview_err:
                task_logger.warning(f"Preview generation failed: {preview_err}")
                with tasks_lock:
                    task['preview'] = {
                        "type": "text",
                        "title": "预览生成失败",
                        "summary": str(preview_err),
                        "lines": [],
                    }
        else:
            with tasks_lock:
                task['status'] = 'failed'
                task['failed_at'] = time.time()
                task['updated_at'] = task['failed_at']
                task['error'] = process_result.get('error') or "Translation completed but output file not found."
            task_logger.error(f"Output file not found: {actual_output_path}")
            
    except FileIOError as e:
        # Handle file I/O errors specifically
        with tasks_lock:
            task['status'] = 'failed'
            task['failed_at'] = time.time()
            task['updated_at'] = task['failed_at']
            task['error'] = error_message_for_user(e)
            task['error_code'] = e.error_code
        task_logger.error(f"File I/O error: {e.message}", exc_info=True)
        
    except ModelCallError as e:
        # Handle model call errors specifically
        with tasks_lock:
            task['status'] = 'failed'
            task['failed_at'] = time.time()
            task['updated_at'] = task['failed_at']
            task['error'] = error_message_for_user(e)
            task['error_code'] = e.error_code
        task_logger.error(f"Model call error: {e.message}", exc_info=True)
        
    except TranslationError as e:
        # Handle other translation-related errors
        with tasks_lock:
            task['status'] = 'failed'
            task['failed_at'] = time.time()
            task['updated_at'] = task['failed_at']
            task['error'] = error_message_for_user(e)
            task['error_code'] = e.error_code
        task_logger.error(f"Translation error ({e.error_code}): {e.message}", exc_info=True)
        
    except Exception as e:
        # Catch unexpected errors
        with tasks_lock:
            task['status'] = 'failed'
            task['failed_at'] = time.time()
            task['updated_at'] = task['failed_at']
            task['error'] = "An unexpected error occurred. Please contact support."
            task['error_code'] = 'INTERNAL_ERROR'
        task_logger.critical(f"Unexpected error: {str(e)}", exc_info=True)


def worker_loop():
    global active_workers
    while True:
        task_id = task_queue.get()
        with _active_workers_lock:
            active_workers += 1
        try:
            process_task(task_id)
        finally:
            with _active_workers_lock:
                active_workers -= 1
            task_queue.task_done()


def init_worker_pool():
    global worker_executor
    if worker_executor is not None:
        return
    worker_executor = ThreadPoolExecutor(
        max_workers=MAX_WORKERS,
        thread_name_prefix="translate-agent-worker"
    )
    for _ in range(MAX_WORKERS):
        worker_executor.submit(worker_loop)


def init_cleanup_worker():
    global cleanup_thread
    if cleanup_thread is not None:
        return

    cleanup_thread = threading.Thread(
        target=cleanup_loop,
        name="translate-agent-cleanup",
        daemon=True,
    )
    cleanup_thread.start()


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/translate', methods=['POST'])
def translate():
    ensure_runtime_services_started()
    if 'file' not in request.files:
         return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    if file.filename == '':
         return jsonify({"error": "No selected file"}), 400
         
    target_lang = request.form.get('target_lang', 'Japanese')
    speed_mode = request.form.get('speed_mode', 'balanced').lower()
    if speed_mode not in ALLOWED_SPEED_MODES:
        speed_mode = 'balanced'
    
    if file and allowed_file(file.filename):
        task_id = str(uuid.uuid4())
        original_filename = file.filename or "uploaded_file"
        ext = os.path.splitext(original_filename)[1]
        
        safe_filename = f"{task_id}{ext}"
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
        file.save(input_path)
        
        with tasks_lock:
            tasks[task_id] = {
                'id': task_id,
                'status': 'pending',
                'input_path': input_path,
                'target_lang': target_lang,
                'speed_mode': speed_mode,
                'original_filename': original_filename,
                'created_at': time.time(),
                'updated_at': time.time(),
            }
        
        task_queue.put(task_id)
        
        return jsonify({"task_id": task_id, "message": "Task queued successfully"})
        
    return jsonify({"error": "Unsupported file format"}), 400

@app.route('/status/<task_id>')
def task_status(task_id):
    with tasks_lock:
        task = tasks.get(task_id)
        if not task:
            return jsonify({"error": "Task not found"}), 404
        task_snapshot = copy.deepcopy(task)

    task = task_snapshot

    with _active_workers_lock:
        active_workers_snapshot = active_workers

    queue_size_snapshot = task_queue.qsize()

    if task['status'] == 'pending':
        try:
            with task_queue.mutex:
                q_list = list(task_queue.queue)
            pending_position = q_list.index(task_id) + 1 if task_id in q_list else 1
        except Exception:
            pending_position = "?"
    else:
        pending_position = None

    now = time.time()

    models_used = task.get('models_used', [])
    if isinstance(models_used, set):
        models_used = sorted(models_used)

    created_at = task.get('created_at')
    started_at = task.get('started_at')
    updated_at = task.get('updated_at')
    completed_at = task.get('completed_at')
    failed_at = task.get('failed_at')
    file_ext = os.path.splitext(task.get('original_filename', ''))[1].lower()
        
    response = {
        "status": task['status'],
        "file_type": file_ext,
        "target_lang": task.get('target_lang', 'Japanese'),
        "speed_mode": task.get('speed_mode', 'balanced'),
        "progress": task.get('progress'),
        "last_model_used": task.get('last_model_used'),
        "models_used": models_used,
        "created_at": created_at,
        "started_at": started_at,
        "updated_at": updated_at,
        "completed_at": completed_at,
        "failed_at": failed_at,
        "queue_wait_seconds": max(0, int((started_at or now) - created_at)) if created_at else None,
        "processing_seconds": max(0, int(now - started_at)) if started_at and task['status'] == 'processing' else None,
        "seconds_since_update": max(0, int(now - updated_at)) if updated_at else None,
        "system": {
            "max_workers": MAX_WORKERS,
            "active_workers": active_workers_snapshot,
            "queue_size": queue_size_snapshot,
        },
    }

    if pending_position is not None:
        response['position'] = pending_position
    elif task['status'] == 'completed':
        response['download_name'] = task.get('download_name') or os.path.basename(task.get('output_path', 'translated'))
        response['quality'] = task.get('quality')
        response['visual_review_required'] = task.get('visual_review_required', False)
        response['filename_translation_ok'] = task.get('filename_translation_ok', True)
        response['filename_translation_issue'] = task.get('filename_translation_issue', '')
        response['preview_ready'] = bool(task.get('preview'))
    elif task['status'] == 'failed':
        response['error'] = task.get('error', 'Unknown error')

    return jsonify(response)

@app.route('/download/<task_id>')
def download(task_id):
    with tasks_lock:
        task = tasks.get(task_id)
    if not task or task['status'] != 'completed' or 'output_path' not in task:
        return jsonify({"error": "File not available"}), 404

    return send_file(task['output_path'], as_attachment=True, download_name=task['download_name'])


@app.route('/preview/<task_id>')
def preview(task_id):
    with tasks_lock:
        task = tasks.get(task_id)
    if not task or task.get('status') != 'completed':
        return jsonify({"error": "Preview not available"}), 404

    pv = task.get('preview')
    if not pv:
        return jsonify({"error": "Preview not generated"}), 404

    return jsonify({"preview": pv})

if __name__ == '__main__':
    ensure_runtime_services_started()
    log_startup_env_check()
    app.run(
        host=config.flask_host,
        port=config.flask_port,
        debug=config.flask_debug,
        use_reloader=False,
    )

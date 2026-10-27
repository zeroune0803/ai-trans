import os
import argparse
import shutil
import subprocess
import tempfile

# 导入刚才写的定制翻译器模块
from translate_docx_custom import translate_docx_document
from translate_ppt_batch import translate_ppt_presentation
from ppt_quality import enforce_title_single_line, run_ppt_quality_checks
from translate_xlsx_custom import translate_excel_workbook
from content_quality import run_docx_quality_checks, run_xlsx_quality_checks
from rules import get_lang_code

ALLOWED_SPEED_MODES = {"fast", "balanced", "strict"}


def _convert_doc_to_docx(input_doc, output_docx):
    """Convert legacy .doc to .docx using Word COM first, then LibreOffice fallback."""
    in_path = os.path.abspath(input_doc)
    out_path = os.path.abspath(output_docx)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    errors = []

    # 1) Prefer Word COM on Windows for better compatibility.
    if os.name == "nt":
        in_ps = in_path.replace("'", "''")
        out_ps = out_path.replace("'", "''")
        ps_script = (
            "$ErrorActionPreference='Stop';"
            f"$in='{in_ps}';"
            f"$out='{out_ps}';"
            "$word=New-Object -ComObject Word.Application;"
            "$word.Visible=$false;"
            "$doc=$word.Documents.Open($in,$false,$true);"
            "$wdFormatXMLDocument=12;"
            "$doc.SaveAs([ref]$out,[ref]$wdFormatXMLDocument);"
            "$doc.Close();"
            "$word.Quit();"
        )
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                capture_output=True,
                text=True,
            )
            if proc.returncode == 0 and os.path.exists(out_path):
                return out_path
            errors.append(f"word-com: {(proc.stderr or proc.stdout or '').strip()}")
        except Exception as e:
            errors.append(f"word-com: {e}")

    # 2) Fallback to LibreOffice CLI if available.
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice:
        try:
            tmp_out_dir = os.path.dirname(out_path)
            proc = subprocess.run(
                [
                    soffice,
                    "--headless",
                    "--convert-to",
                    "docx",
                    "--outdir",
                    tmp_out_dir,
                    in_path,
                ],
                capture_output=True,
                text=True,
            )
            expected = os.path.join(
                tmp_out_dir,
                os.path.splitext(os.path.basename(in_path))[0] + ".docx",
            )
            if proc.returncode == 0 and os.path.exists(expected):
                if os.path.abspath(expected) != os.path.abspath(out_path):
                    if os.path.exists(out_path):
                        os.remove(out_path)
                    os.replace(expected, out_path)
                return out_path
            errors.append(f"libreoffice: {(proc.stderr or proc.stdout or '').strip()}")
        except Exception as e:
            errors.append(f"libreoffice: {e}")

    raise RuntimeError(
        "DOC 转 DOCX 失败。请安装 Microsoft Word(支持COM) 或 LibreOffice(soffice)。 "
        f"details={errors}"
    )

def main():
    parser = argparse.ArgumentParser(description="多格式文档（Word/PPT/Excel）本地翻译工具")
    parser.add_argument(
        "-i", "--input", 
        required=True, 
        help="待翻译的源文件路径或是包含多个文件的文件夹路径"
    )
    parser.add_argument(
        "-t", "--target_lang", 
        required=True, 
        choices=["Chinese", "English", "Japanese"], 
        help="目标语言 (Chinese, English, Japanese)"
    )
    parser.add_argument(
        "-s", "--speed_mode",
        default="balanced",
        choices=["fast", "balanced", "strict"],
        help="速度模式 (fast, balanced, strict)"
    )

    args = parser.parse_args()
    input_path = args.input
    target_lang = args.target_lang
    speed_mode = args.speed_mode
    
    # 检查输入的 API KEY
    if not (os.getenv("OPENAI_API_KEY") or "").strip():
         print("⚠️ 警告：检测到尚未配置真实的环境变量 OPENAI_API_KEY，翻译请求可能会失败！")
         print("Windows 请运行：$env:OPENAI_API_KEY='你的真实key'\n")

    # 判断输入是单个文件还是文件夹
    if os.path.isfile(input_path):
        process_single_file(input_path, target_lang, speed_mode=speed_mode)
    elif os.path.isdir(input_path):
        files = [os.path.join(input_path, f) for f in os.listdir(input_path) if os.path.isfile(os.path.join(input_path, f))]
        print(f"在目录中找到了 {len(files)} 个文件，准备开始批量处理...\n")
        for f in files:
            process_single_file(f, target_lang, speed_mode=speed_mode)
    else:
        print(f"错误: 输入路径 {input_path} 不存在。")

def process_single_file(file_path, target_lang, speed_mode="balanced", progress_callback=None):
    """根据文件后缀自动分发到对应的翻译策略器"""
    if speed_mode not in ALLOWED_SPEED_MODES:
        speed_mode = "balanced"

    file_path = os.path.abspath(file_path)
    dir_name = os.path.dirname(file_path)
    basename = os.path.basename(file_path)
    _name, ext = os.path.splitext(basename)
    ext = ext.lower()
    lang_code = get_lang_code(target_lang)
    
    # 构造输出文件路径：语言代码_原文件名.扩展名
    output_path = os.path.join(dir_name, f"{lang_code}_{_name}{ext}")
    result = {
        "success": False,
        "output_path": output_path,
        "speed_mode": speed_mode,
        "quality": None,
    }
    
    print(f"\n[{ext.upper()}] 正在派发任务: {os.path.basename(file_path)} (speed_mode={speed_mode})")
    
    try:
        if ext == ".docx":
            translate_docx_document(
                file_path,
                output_path,
                target_lang,
                speed_mode=speed_mode,
                progress_callback=progress_callback,
            )
            if speed_mode == "fast":
                result["quality"] = {
                    "passed": True,
                    "summary": "fast 模式已跳过通用内容 QA 以提升速度。",
                    "checks_skipped": ["qa"],
                }
            else:
                result["quality"] = run_docx_quality_checks(file_path, output_path, target_lang)
            result["success"] = True
            return result
        elif ext == ".doc":
            docx_output_path = os.path.join(dir_name, f"{lang_code}_{_name}.docx")
            with tempfile.TemporaryDirectory(prefix="doc2docx_") as tmp_dir:
                converted_docx = os.path.join(tmp_dir, _name + ".docx")
                _convert_doc_to_docx(file_path, converted_docx)
                translate_docx_document(
                    converted_docx,
                    docx_output_path,
                    target_lang,
                    speed_mode=speed_mode,
                    progress_callback=progress_callback,
                )
                if speed_mode == "fast":
                    result["quality"] = {
                        "passed": True,
                        "summary": "fast 模式已跳过通用内容 QA 以提升速度。",
                        "checks_skipped": ["qa"],
                    }
                else:
                    result["quality"] = run_docx_quality_checks(converted_docx, docx_output_path, target_lang)
            result["success"] = True
            result["output_path"] = docx_output_path
            return result
        elif ext == ".pptx":
            translate_ppt_presentation(file_path, output_path, target_lang, speed_mode=speed_mode, progress_callback=progress_callback)
            if speed_mode == "fast":
                result["quality"] = {
                    "passed": True,
                    "summary": "fast 模式已跳过标题修正与质量检查以提升速度。",
                    "checks_skipped": ["title_fix", "qa"],
                }
            else:
                title_fix_stats = enforce_title_single_line(output_path)
                quality = run_ppt_quality_checks(file_path, output_path, target_lang)
                quality_dict = quality.to_dict()
                quality_dict["title_fix"] = title_fix_stats
                result["quality"] = quality_dict
            result["success"] = True
            return result
        elif ext == ".xlsx":
            translate_excel_workbook(
                file_path,
                output_path,
                target_lang,
                speed_mode=speed_mode,
                progress_callback=progress_callback,
            )
            if speed_mode == "fast":
                result["quality"] = {
                    "passed": True,
                    "summary": "fast 模式已跳过通用内容 QA 以提升速度。",
                    "checks_skipped": ["qa"],
                }
            else:
                result["quality"] = run_xlsx_quality_checks(file_path, output_path, target_lang)
            result["success"] = True
            return result
        else:
            print(f"跳过不支持的文件格式: {ext}")
            result["error"] = f"不支持的文件格式: {ext}"
            return result
    except Exception as e:
        print(f"处理文件 {os.path.basename(file_path)} 时发生致命错误: {e}")
        result["error"] = str(e)
        return result

if __name__ == "__main__":
    main()

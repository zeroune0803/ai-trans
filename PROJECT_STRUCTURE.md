# translate_agent 目录整理说明

## 当前主流程（生产链路）
- `app.py`: Flask Web 接口与任务队列
- `main.py`: 文件类型分发入口
- `translate_docx_custom.py`: DOCX 翻译
- `translate_ppt_batch.py`: PPT 批处理翻译主引擎
- `ppt_quality.py`: PPT 质检与标题单行修复
- `translate_xlsx_custom.py`: XLSX 翻译
- `templates/index.html`: 前端上传页面

## 工具脚本目录
- `tools/glossary/sync_project_glossary.py`: 从中日英对照表同步项目词典 JSON
- `tools/glossary/fill_glossary_missing.py`: 批量补全术语表空白译文（支持词典与可选 AI）
- `tools/glossary/check_glossary_consistency.py`: 检查术语一致性冲突（中->日 / 中->英）
- `tools/glossary/apply_glossary_conflicts.py`: 按冲突 CSV 回写统一译法
- `tools/glossary/inspect_glossary_xlsx.py`: 快速查看术语表结构（sheet/表头）
- `tools/glossary/cli.py`: 词典工具统一入口（推荐）

以上工具仅用于词典维护，不参与线上翻译主链路。

## 推荐使用方式
1. Web 模式:
	- 启动命令：`python app.py`
	- 默认访问：`http://127.0.0.1:5000`
2. CLI 模式: 运行 `main.py -i <文件或目录> -t <Chinese|English|Japanese>`
3. 词典工具统一入口: 运行 `python tools/glossary/cli.py <sync|fill|check|apply|inspect> ...`
4. 词典同步（等价旧命令）: 运行 `python tools/glossary/sync_project_glossary.py <xlsx路径>`

## 输出归档目录
- `_archive/outputs/`: 测试输出文件（如 `test_out*.docx`）
- `_archive/logs/`: 运行日志（如 `last_run.log`）

## 说明
- 本次整理将词典维护脚本从根目录归档到 `tools/glossary/`，不影响核心翻译能力。

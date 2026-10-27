import os

html_path = r'e:\Dev\translate_agent\templates\index.html'
with open(html_path, 'r', encoding='utf-8') as f:
    text = f.read()

# We need to replace the form.addEventListener part.
old_js_start = "form.addEventListener('submit', async (e) => {"
# The end of the file is basically the end of that event listener.
js_new = """form.addEventListener('submit', async (e) => {
            e.preventDefault();
            alertBox.style.display = 'none';
            manualDownloadBtn.style.display = 'none';

            if (!fileInput.files || fileInput.files.length === 0) {
                showAlert("请先选择一个文件！", "error");
                return;
            }

            const formData = new FormData();
            formData.append('file', fileInput.files[0]);
            formData.append('target_lang', document.getElementById('targetLang').value);

            submitBtn.disabled = true;
            submitBtn.textContent = '任务已提交...';
            progressContainer.style.display = 'block';
            form.style.opacity = '0.5';

            let currentProgress = 0;
            progressBar.style.width = '0%';
            progressText.textContent = '正在排队进入服务器...';

            if(progressInterval) clearInterval(progressInterval);

            try {
                // 1. Submit task to the backend queue
                const response = await fetch('/translate', {
                    method: 'POST',
                    body: formData
                });

                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.error || '上传失败，服务器错误');
                }

                const data = await response.json();
                const taskId = data.task_id;

                // 2. Poll status
                const pollStatus = async () => {
                    const res = await fetch(/status/);
                    if (!res.ok) throw new Error("获取状态失败");
                    const statusData = await res.json();

                    if (statusData.status === 'pending') {
                        progressBar.style.width = '5%';
                        progressText.innerHTML = 😴 <b>服务繁忙，您排在第  位，请稍候...</b>;
                        setTimeout(pollStatus, 3000);
                    } else if (statusData.status === 'processing') {
                        // Enter processing animation phase
                        currentProgress += (95 - currentProgress) * 0.05;
                        progressBar.style.width = currentProgress.toFixed(1) + '%';
                        
                        let text = '正在调用大模型逐句解析与翻译...';
                        if(currentProgress < 20) text = '文档拆解与预处理中...';
                        else if(currentProgress > 80) text = '深度重组排版以保真样式...';
                        
                        progressText.textContent = ${text} (%);
                        setTimeout(pollStatus, 1500); 
                    } else if (statusData.status === 'completed') {
                        progressBar.style.width = '100%';
                        progressText.textContent = '处理完成，文件生成中... (100%)';

                        const downloadUrl = /download/;
                        const dlName = statusData.download_name || 'Translated_File';
                        
                        // Show download button
                        manualDownloadBtn.href = downloadUrl;
                        manualDownloadBtn.download = dlName;
                        manualDownloadBtn.textContent = '⬇️ 再次下载: ' + dlName;
                        manualDownloadBtn.style.display = 'block';

                        // Auto download
                        const a = document.createElement('a');
                        a.style.display = 'none';
                        a.href = downloadUrl;
                        a.download = dlName;
                        document.body.appendChild(a);
                        a.click();
                        document.body.removeChild(a);

                        showAlert("✅ 翻译完成！文件已开始自动下载。如果您未看到系统提示下载，请点击下方绿色按钮手动下载。", "success");
                        
                        // Reset UI
                        submitBtn.disabled = false;
                        submitBtn.textContent = '立即开始翻译';
                        setTimeout(() => {
                            progressContainer.style.display = 'none';
                            progressBar.style.backgroundColor = 'var(--primary)';
                            form.style.opacity = '1';
                        }, 5000);

                    } else if (statusData.status === 'failed') {
                        throw new Error(statusData.error || "翻译解析失败");
                    }
                };

                // Trigger polling
                pollStatus();

            } catch (error) {
                progressBar.style.backgroundColor = '#EF4444'; // 标红
                progressText.textContent = '任务已中断';
                showAlert("❌ " + error.message, "error");
                
                submitBtn.disabled = false;
                submitBtn.textContent = '立即开始翻译';
                form.style.opacity = '1';
            }
        });
    </script>
</body>
</html>"""

new_text = text[:text.index(old_js_start)] + js_new

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(new_text)


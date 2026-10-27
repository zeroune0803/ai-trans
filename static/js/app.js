/* ===== Translate Agent – Frontend Logic ===== */

(function () {
    'use strict';

    // ===== Constants =====
    const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50 MB
    const THEME_KEY = 'translate_agent_theme';
    const TASK_RECOVERY_KEY = 'translate_agent_last_active_task';
    const TASK_OWNER_KEY = 'translate_agent_active_task_owner';
    const RETRY_BTN_TEXT_DEFAULT = '重新翻译该文档';
    const RETRY_BTN_TEXT_BLOCKED = '返回首页重新选择文件';

    // ===== DOM Elements =====
    const $ = (sel) => document.querySelector(sel);
    const form = $('#translateForm');
    const uploadArea = $('#uploadArea');
    const fileInput = $('#fileInput');
    const fileChip = $('#fileChip');
    const fileNameDisplay = $('#fileName');
    const fileSizeDisplay = $('#fileSize');
    const uploadPlaceholder = $('#uploadPlaceholder');
    const uploadError = $('#uploadError');
    const segmentCards = document.querySelectorAll('.segment-card');
    const submitBtn = $('#submitBtn');
    const submitMeta = $('#submitMeta');
    const submitBtnLoading = $('#submitBtnLoading');
    const progressContainer = $('#progressContainer');
    const progressStagePill = $('#progressStagePill');
    const progressStageIcon = $('#progressStageIcon');
    const progressStageLabel = $('#progressStageLabel');
    const bar = $('#progressBar');
    const txtMain = $('#progressTextMain');
    const txtSub = $('#progressTextSub');
    const detailContent = $('#detailContent');
    const resultCard = $('#resultCard');
    const alertBox = $('#alertError');
    const themeToggle = $('#themeToggle');
    const progressBackHomeBtn = $('#progressBackHomeBtn');
    const progressRetryBtn = $('#progressRetryBtn');
    const confirmOverlay = $('#confirmOverlay');
    const confirmTitle = $('#confirmTitle');
    const confirmMessage = $('#confirmMessage');
    const confirmOkBtn = $('#confirmOkBtn');
    const confirmCancelBtn = $('#confirmCancelBtn');
    const manualDownloadBtn = $('#manualDownloadBtn');

    let activeSubmissionId = 0;
    let activePollTimer = null;
    let confirmResolver = null;
    const TAB_ID = `tab_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    let currentTrackingTaskId = null;
    let isRetryButtonBlocked = false;

    function setSubmitLoading(loading, labelText = '开始翻译') {
        if (!submitBtn) return;

        submitBtn.classList.toggle('is-loading', Boolean(loading));
        submitBtn.disabled = Boolean(loading) || (!fileInput.files || fileInput.files.length === 0);

        const labelEl = submitBtn.querySelector('.btn-label');
        if (labelEl) {
            labelEl.textContent = labelText;
        }
        if (submitBtnLoading) {
            submitBtnLoading.setAttribute('aria-hidden', loading ? 'false' : 'true');
        }
    }

    function updateSubmitMeta() {
        if (!submitMeta) return;
        const hasFile = fileInput.files && fileInput.files.length > 0;
        if (!hasFile) {
            submitMeta.textContent = '选择文件后即可开始翻译';
            return;
        }

        const file = fileInput.files[0];
        const ext = getFileExtension(file.name);
        const fileType = FILE_TYPE_LABELS[ext] || ext.toUpperCase().replace('.', '');
        const mode = form.querySelector('input[name="speed_mode"]:checked')?.value || 'balanced';
        const modeMap = {
            fast: '草稿快速版',
            balanced: '推荐版',
            strict: '正式发布版'
        };
        submitMeta.textContent = `将提交 ${fileType} · ${formatFileSize(file.size)} · ${modeMap[mode] || mode}`;
    }

    function setProgressActionPriority(state) {
        const actionsEl = document.querySelector('.progress-actions');
        if (!actionsEl || !progressRetryBtn || !progressBackHomeBtn) return;

        actionsEl.classList.remove('state-active', 'state-retry-priority');
        progressRetryBtn.classList.remove('btn-primary', 'btn-secondary');
        progressBackHomeBtn.classList.remove('btn-primary', 'btn-secondary');

        if (state === 'failed') {
            actionsEl.classList.add('state-retry-priority');
            progressRetryBtn.classList.add('btn-primary');
            progressBackHomeBtn.classList.add('btn-secondary');
            return;
        }

        actionsEl.classList.add('state-active');
        progressRetryBtn.classList.add('btn-secondary');
        progressBackHomeBtn.classList.add('btn-secondary');
    }

    function setRetryButtonBlockedMode(blocked) {
        if (!progressRetryBtn) return;
        isRetryButtonBlocked = Boolean(blocked);
        progressRetryBtn.textContent = blocked ? RETRY_BTN_TEXT_BLOCKED : RETRY_BTN_TEXT_DEFAULT;
    }

    function saveActiveTaskMeta(meta) {
        try {
            localStorage.setItem(TASK_RECOVERY_KEY, JSON.stringify({ ...(meta || {}), tabId: TAB_ID }));
        } catch (_) {
            // ignore localStorage quota/permission errors
        }
    }

    function loadActiveTaskMeta() {
        try {
            const raw = localStorage.getItem(TASK_RECOVERY_KEY);
            if (!raw) return null;
            const parsed = JSON.parse(raw);
            return parsed && typeof parsed === 'object' ? parsed : null;
        } catch (_) {
            return null;
        }
    }

    function clearActiveTaskMeta() {
        try {
            localStorage.removeItem(TASK_RECOVERY_KEY);
        } catch (_) {
            // ignore localStorage errors
        }
    }

    function loadTaskOwnerMeta() {
        try {
            const raw = localStorage.getItem(TASK_OWNER_KEY);
            if (!raw) return null;
            const parsed = JSON.parse(raw);
            return parsed && typeof parsed === 'object' ? parsed : null;
        } catch (_) {
            return null;
        }
    }

    function claimTaskOwnership(taskId, modeStr) {
        try {
            localStorage.setItem(TASK_OWNER_KEY, JSON.stringify({
                taskId,
                tabId: TAB_ID,
                mode: modeStr,
                updatedAt: Date.now(),
            }));
        } catch (_) {
            // ignore localStorage errors
        }
    }

    function releaseTaskOwnership(taskId) {
        try {
            const owner = loadTaskOwnerMeta();
            if (!owner) return;
            if (owner.tabId === TAB_ID && (!taskId || owner.taskId === taskId)) {
                localStorage.removeItem(TASK_OWNER_KEY);
            }
        } catch (_) {
            // ignore localStorage errors
        }
    }

    function getTaskOwnerConflict(taskId) {
        const owner = loadTaskOwnerMeta();
        if (!owner || owner.taskId !== taskId) return null;
        if (owner.tabId === TAB_ID) return null;
        return owner;
    }

    function blockCrossTabTaskView(taskId, modeStr, ownerMeta) {
        if (activePollTimer) {
            clearTimeout(activePollTimer);
            activePollTimer = null;
        }

        setRetryButtonBlockedMode(true);

        setProgressStage('failed', '⛔', '会话隔离');
        bar.classList.remove('indeterminate');
        txtMain.textContent = '该任务由其他页面提交';
        txtSub.textContent = '当前页面无权限查看，请在原页面操作。';
        setDetailLines([
            `任务ID：${taskId}`,
            `模式：${modeStr}`,
            ownerMeta && ownerMeta.updatedAt ? `最近活动：${new Date(ownerMeta.updatedAt).toLocaleTimeString()}` : '',
            '说明：已禁用跨页面接管与查看。'
        ]);

        hideSection(progressContainer);
        setTimeout(() => {
            showSection(form);
            showAlert('⚠️ 该任务由其他页面提交，当前页面无法查看。请在原页面继续操作。');
        }, 220);
    }

    function ensureTaskOwnershipStrict(taskId, modeStr) {
        const conflict = getTaskOwnerConflict(taskId);
        if (!conflict) {
            setRetryButtonBlockedMode(false);
            claimTaskOwnership(taskId, modeStr);
            currentTrackingTaskId = taskId;
            return true;
        }

        blockCrossTabTaskView(taskId, modeStr, conflict);
        showToast('该任务属于其他页面，当前页不可查看。');
        return false;
    }

    // Allowed extensions (must match backend)
    const ALLOWED_EXTENSIONS = ['.docx', '.pptx', '.xlsx'];
    const FILE_TYPE_LABELS = {
        '.docx': 'Word',
        '.pptx': 'PPT',
        '.xlsx': 'Excel'
    };
    const SUBMIT_TIMEOUT_MS = 20000;
    const STATUS_TIMEOUT_MS = 12000;
    const DOWNLOAD_TIMEOUT_MS = 20000;

    function fetchWithTimeout(url, options = {}, timeoutMs = 15000) {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), timeoutMs);

        return fetch(url, { ...options, signal: controller.signal })
            .finally(() => clearTimeout(timer));
    }

    // ===== Theme Management =====
    function initTheme() {
        const saved = localStorage.getItem(THEME_KEY);
        if (saved === 'dark' || (!saved && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
            document.documentElement.setAttribute('data-theme', 'dark');
        }
    }

    function toggleTheme() {
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        document.documentElement.setAttribute('data-theme', isDark ? 'light' : 'dark');
        localStorage.setItem(THEME_KEY, isDark ? 'light' : 'dark');
    }

    initTheme();
    themeToggle.addEventListener('click', toggleTheme);

    function beginTaskTracking({
        submissionId,
        taskId,
        modeStr,
        originalFileName,
        startTime,
        initialStatusData = null,
    }) {
        const userFileType = getFileExtension(originalFileName || '');
        const MAX_STATUS_SYNC_RETRIES = 12;
        let statusSyncRetryCount = 0;
        let ownershipChecked = false;

        const pollStatus = async (presetData = null) => {
            if (submissionId !== activeSubmissionId) return;

            if (!ownershipChecked) {
                ownershipChecked = true;
                const canTrack = ensureTaskOwnershipStrict(taskId, modeStr);
                if (!canTrack) return;
            }

            const conflict = getTaskOwnerConflict(taskId);
            if (conflict) {
                blockCrossTabTaskView(taskId, modeStr, conflict);
                return;
            }

            const scheduleNext = (delayMs) => {
                activePollTimer = setTimeout(() => {
                    if (submissionId === activeSubmissionId) {
                        pollStatus();
                    }
                }, delayMs);
            };

            let statusData = presetData;
            if (!statusData) {
                try {
                    const res = await fetchWithTimeout(`/status/${taskId}`, {}, STATUS_TIMEOUT_MS);
                    if (!res.ok) {
                        let backendError = '';
                        try {
                            const errPayload = await res.json();
                            backendError = (errPayload && errPayload.error) ? String(errPayload.error) : '';
                        } catch (_) {
                            backendError = '';
                        }
                        const statusErr = new Error(`获取状态失败(${res.status})${backendError ? `: ${backendError}` : ''}`);
                        statusErr.statusCode = res.status;
                        throw statusErr;
                    }
                    statusData = await res.json();
                    statusSyncRetryCount = 0;
                } catch (err) {
                    if (submissionId !== activeSubmissionId) return;

                    statusSyncRetryCount += 1;
                    const timeoutHit = err && err.name === 'AbortError';
                    const errMsg = timeoutHit ? '状态请求超时，服务器可能繁忙' : ((err && err.message) ? String(err.message) : '未知错误');
                    const statusCode = err && typeof err.statusCode === 'number' ? err.statusCode : null;

                    // Task may disappear after service reload/restart; fail fast with clear message.
                    if (statusCode === 404) {
                        if (activePollTimer) {
                            clearTimeout(activePollTimer);
                            activePollTimer = null;
                        }
                        releaseTaskOwnership(taskId);
                        currentTrackingTaskId = null;
                        setProgressStage('failed', '❌', '任务状态丢失');
                        bar.classList.remove('indeterminate');
                        txtMain.textContent = '任务状态不可恢复';
                        txtSub.textContent = '服务可能刚刚重启，当前任务状态已丢失，请重新提交文档。';
                        setDetailLines([
                            `任务ID：${taskId}`,
                            `模式：${modeStr}`,
                            `状态接口返回：404`,
                            '建议：点击“重新翻译该文档”重新发起任务。'
                        ]);
                        showToast('任务状态丢失，请重新提交。');
                        return;
                    }

                    if (statusSyncRetryCount > MAX_STATUS_SYNC_RETRIES) {
                        if (activePollTimer) {
                            clearTimeout(activePollTimer);
                            activePollTimer = null;
                        }
                        releaseTaskOwnership(taskId);
                        currentTrackingTaskId = null;
                        setProgressStage('failed', '❌', '状态同步失败');
                        bar.classList.remove('indeterminate');
                        txtMain.textContent = '状态同步连续失败';
                        txtSub.textContent = '已达到重试上限，为避免误导已停止自动轮询，可直接重试该文档。';
                        setDetailLines([
                            `任务ID：${taskId}`,
                            `模式：${modeStr}`,
                            `连续失败次数：${statusSyncRetryCount}`,
                            `最后错误：${errMsg}`
                        ]);
                        showToast('状态同步失败，请重试该文档。');
                        return;
                    }

                    const nextDelay = Math.min(8000, 2000 + statusSyncRetryCount * 800);
                    setProgressStage('retrying', '🔄', '状态同步中');
                    txtMain.textContent = timeoutHit ? '状态读取超时，正在自动重试...' : '状态同步稍有延迟，正在自动刷新...';
                    txtSub.textContent = `网络抖动或服务繁忙时会出现这个提示，正在第 ${statusSyncRetryCount}/${MAX_STATUS_SYNC_RETRIES} 次重试。`;
                    setDetailLines([
                        `任务ID：${taskId}`,
                        `模式：${modeStr}`,
                        `最近错误：${errMsg}`,
                        `下次重试：${Math.ceil(nextDelay / 1000)}s 后`
                    ]);
                    scheduleNext(nextDelay);
                    return;
                }
            }

            const elapsed = Math.floor((Date.now() - startTime) / 1000);
            const fileTypeLabel = getFileTypeLabel(statusData, originalFileName || userFileType);

            if (statusData.status === 'pending') {
                setProgressStage('pending', '⏳', '排队中');
                bar.classList.add('indeterminate');
                txtMain.textContent = `正在排队，当前第 ${statusData.position} 位`;
                txtSub.textContent = `已等待 ${formatDuration(elapsed)} · 轮到后会自动开始`;
                setDetailLines([
                    `文件类型：${fileTypeLabel}`,
                    `模式：${modeStr}`,
                    '页面会自动刷新，无需手动操作。'
                ]);
                scheduleNext(3000);
                return;
            }

            if (statusData.status === 'processing') {
                bar.classList.remove('indeterminate');

                let phase = '调用大模型深层翻译中...';

                if (statusData.progress) {
                    phase = statusData.progress.phase;
                    if (statusData.progress.total > 0) {
                        const pct = (statusData.progress.current / statusData.progress.total) * 100;
                        bar.style.width = `${pct}%`;
                    }
                } else {
                    let curWidth = parseFloat(bar.style.width) || 5;
                    curWidth += (90 - curWidth) * 0.05;
                    bar.style.width = `${curWidth}%`;
                    if (curWidth < 15) phase = '文档结构解析中...';
                    else if (curWidth > 80) phase = '排版重组与最后检查...';
                }

                const stageMeta = getProcessingStageMeta(phase);
                setProgressStage('processing', stageMeta.icon, stageMeta.label);

                const phaseDisplay = describeProcessingPhase(phase, statusData);
                txtMain.textContent = phaseDisplay.main;
                txtSub.textContent = `已处理 ${formatDuration(statusData.processing_seconds ?? elapsed)} · ${phaseDisplay.hint}`;

                const modelInfo = (statusData.progress && statusData.progress.model) || statusData.last_model_used || null;
                const modelsUsed = Array.isArray(statusData.models_used) ? statusData.models_used : [];
                setDetailLines([
                    `文件类型：${fileTypeLabel}`,
                    `模式：${modeStr}`,
                    modelInfo ? `当前模型：${modelInfo}` : '',
                    modelsUsed.length > 1 ? `已使用模型：${modelsUsed.join(', ')}` : '',
                    statusData.seconds_since_update != null ? `距上次进度更新：${formatDuration(statusData.seconds_since_update)}` : '',
                    '只要页面还在自动刷新，任务就仍在服务器上执行。'
                ]);

                scheduleNext(1500);
                return;
            }

            if (statusData.status === 'completed') {
                if (activePollTimer) {
                    clearTimeout(activePollTimer);
                    activePollTimer = null;
                }
                clearActiveTaskMeta();
                releaseTaskOwnership(taskId);
                currentTrackingTaskId = null;
                setProgressStage('completed', '✅', '已完成');
                bar.classList.remove('indeterminate');
                bar.style.width = '100%';

                const totalTime = Math.floor((Date.now() - startTime) / 1000);

                setTimeout(() => {
                    hideSection(progressContainer);
                    setTimeout(() => {
                        showSection(resultCard);

                        $('#resBadgeMode').textContent = `模式: ${modeStr}`;

                        const sourceBadge = $('#resBadgeSource');
                        const sourceLang = (statusData.quality && statusData.quality.source_lang_detected) || 'Unknown';
                        const sourceLangMap = {
                            Chinese: '中文',
                            English: '英文',
                            Japanese: '日文',
                            Unknown: '未知'
                        };
                        if (sourceBadge) {
                            if (sourceLang && sourceLang !== 'Unknown') {
                                sourceBadge.textContent = `源语言: ${sourceLangMap[sourceLang] || sourceLang}`;
                                sourceBadge.classList.remove('hidden');
                            } else {
                                sourceBadge.classList.add('hidden');
                            }
                        }

                        const qaBadge = $('#resBadgeQA');
                        const qData = statusData.quality;
                        if (qData) {
                            if (qData.checks_skipped && qData.checks_skipped.includes('qa')) {
                                qaBadge.className = 'badge badge-qa-skip';
                                qaBadge.textContent = 'QA 已跳过';
                            } else if (statusData.visual_review_required) {
                                qaBadge.className = 'badge badge-qa-warn';
                                qaBadge.textContent = '建议视觉复核';
                            } else {
                                qaBadge.className = 'badge badge-qa-success';
                                qaBadge.textContent = 'QA 已通过';
                            }
                        } else {
                            qaBadge.className = 'badge badge-qa-skip';
                            qaBadge.textContent = 'QA 不适用';
                        }

                        const statsEl = $('#resultStats');
                        const totalSteps = statusData.progress ? statusData.progress.total : 0;
                        statsEl.textContent = `共耗时 ${formatDuration(totalTime)}${totalSteps ? ` · 处理 ${totalSteps} 条文本` : ''}`;
                        renderQualityMetrics(statusData);

                        const dlBtn = manualDownloadBtn;
                        const downloadName = statusData.download_name || 'Translated';
                        dlBtn.href = `/download/${taskId}`;
                        dlBtn.setAttribute('download', downloadName);
                        dlBtn.title = `下载 ${downloadName}`;
                        dlBtn.classList.remove('disabled');
                        dlBtn.querySelector('.dl-text').textContent = `下载 ${downloadName}`;

                        showToast(`翻译完成！共耗时 ${totalTime}s`);
                    }, 280);
                }, 400);
                return;
            }

            if (statusData.status === 'failed') {
                if (activePollTimer) {
                    clearTimeout(activePollTimer);
                    activePollTimer = null;
                }
                clearActiveTaskMeta();
                releaseTaskOwnership(taskId);
                currentTrackingTaskId = null;
                setProgressStage('failed', '❌', '任务失败');
                bar.classList.remove('indeterminate');
                txtMain.textContent = '任务执行失败';
                txtSub.textContent = buildFriendlyErrorMessage(statusData.error || '翻译失败');
                setDetailLines([
                    `任务ID：${taskId}`,
                    `文件类型：${fileTypeLabel}`,
                    `模式：${modeStr}`,
                    statusData.error ? `失败原因：${statusData.error}` : '失败原因：未返回详细错误。'
                ]);
                showToast('任务失败，可直接点击“重新翻译该文档”重试。');
                return;
            }

            setProgressStage('retrying', '🔄', '状态同步中');
            txtMain.textContent = '收到未识别的任务状态，正在继续同步...';
            txtSub.textContent = '服务返回了非常规状态值，页面会继续自动刷新。';
            setDetailLines([
                `任务ID：${taskId}`,
                `模式：${modeStr}`,
                `未知状态：${String(statusData.status || '空值')}`,
                '建议：若持续 1-2 分钟无变化，可点击“重新翻译该文档”。'
            ]);
            scheduleNext(2000);
        };

        pollStatus(initialStatusData || null);
    }

    async function checkLocalTaskRecoveryHint() {
        const lastTask = loadActiveTaskMeta();
        if (!lastTask || !lastTask.taskId) return;

        // Strict isolation: legacy local states without tabId are treated as untrusted.
        if (!lastTask.tabId) {
            clearActiveTaskMeta();
            showAlert('⚠️ 检测到历史任务状态缺少会话标识，已按安全策略阻断自动恢复。请重新提交文档。');
            return;
        }

        if (lastTask.tabId && lastTask.tabId !== TAB_ID) {
            showAlert('⚠️ 检测到其他页面提交的任务，当前页面无法查看，请在原页面继续操作。');
            return;
        }

        try {
            const res = await fetchWithTimeout(`/status/${lastTask.taskId}`, {}, STATUS_TIMEOUT_MS);
            if (res.status === 404) {
                clearActiveTaskMeta();
                showAlert('⚠️ 检测到上次任务状态已不可恢复（服务可能重启）。请重新提交文档。');
                return;
            }

            if (!res.ok) {
                return;
            }

            const data = await res.json();
            if (data && (data.status === 'completed' || data.status === 'failed')) {
                clearActiveTaskMeta();
                releaseTaskOwnership(lastTask.taskId);
                currentTrackingTaskId = null;
                return;
            }

            if (data && (data.status === 'pending' || data.status === 'processing' || data.status === 'retrying')) {
                activeSubmissionId += 1;
                if (activePollTimer) {
                    clearTimeout(activePollTimer);
                    activePollTimer = null;
                }

                hideAlert();
                form.style.display = 'none';
                resultCard.style.display = 'none';
                showSection(progressContainer);
                bar.classList.add('indeterminate');
                bar.style.width = '';
                setProgressStage('retrying', '🔄', '恢复任务中');
                txtMain.textContent = '已自动恢复上次任务，正在同步最新进度...';
                txtSub.textContent = '';
                setDetailLines([
                    `任务ID：${lastTask.taskId}`,
                    `模式：${String(lastTask.mode || 'BALANCED')}`,
                    '页面已自动续接，无需重新提交。'
                ]);
                showToast('已恢复上次进行中的任务。');

                beginTaskTracking({
                    submissionId: activeSubmissionId,
                    taskId: lastTask.taskId,
                    modeStr: String(lastTask.mode || 'BALANCED'),
                    originalFileName: String(lastTask.fileName || ''),
                    startTime: Number(lastTask.createdAt) || Date.now(),
                    initialStatusData: data,
                });
            }
        } catch (_) {
            showAlert('⚠️ 暂时无法恢复上次任务状态，请检查网络后重试。');
        }
    }

    checkLocalTaskRecoveryHint();

    // ===== Speed Mode Selection =====
    window.selectMode = function (m) {
        segmentCards.forEach(c => c.classList.remove('active'));
        const target = document.querySelector(`.segment-card input[value="${m}"]`);
        if (target) {
            target.checked = true;
            target.parentElement.classList.add('active');
        }
        updateSubmitMeta();
    };

    // ===== File Upload =====
    function formatFileSize(bytes) {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }

    function getFileExtension(filename) {
        const dot = filename.lastIndexOf('.');
        return dot >= 0 ? filename.slice(dot).toLowerCase() : '';
    }

    function showUploadError(msg) {
        uploadError.textContent = msg;
        uploadError.classList.add('visible');
        uploadArea.classList.add('has-error');
        fileChip.style.display = 'none';
        uploadPlaceholder.style.display = 'block';
        uploadArea.style.padding = '2.5rem 1.5rem';
        submitBtn.disabled = true;
    }

    function hideUploadError() {
        uploadError.classList.remove('visible');
        uploadArea.classList.remove('has-error');
    }

    function handleFileSelect() {
        hideUploadError();

        if (fileInput.files && fileInput.files.length > 0) {
            const file = fileInput.files[0];
            const ext = getFileExtension(file.name);

            // Extension check
            if (!ALLOWED_EXTENSIONS.includes(ext)) {
                showUploadError(`不支持的文件格式「${ext || '未知'}」，仅支持 DOCX / PPTX / XLSX`);
                fileInput.value = '';
                return;
            }

            // Size check
            if (file.size > MAX_FILE_SIZE) {
                showUploadError(`文件大小 ${formatFileSize(file.size)} 超过 50MB 限制，请选择更小的文件`);
                fileInput.value = '';
                return;
            }

            // Empty file check
            if (file.size === 0) {
                showUploadError('文件为空（0 字节），请重新选择');
                fileInput.value = '';
                return;
            }

            fileNameDisplay.textContent = file.name;
            fileSizeDisplay.textContent = formatFileSize(file.size);
            fileChip.style.display = 'flex';
            uploadPlaceholder.style.display = 'none';
            uploadArea.style.padding = '1.5rem';
            submitBtn.disabled = false;
            hideAlert();
            updateSubmitMeta();
        } else {
            resetUploadArea();
        }
    }

    fileInput.addEventListener('change', handleFileSelect);

    // Drag & drop
    uploadArea.addEventListener('dragover', (e) => { e.preventDefault(); uploadArea.classList.add('dragover'); });
    uploadArea.addEventListener('dragleave', () => { uploadArea.classList.remove('dragover'); });
    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
            fileInput.files = e.dataTransfer.files;
            handleFileSelect();
        }
    });

    // File chip close button
    const chipCloseBtn = $('#fileChipClose');
    if (chipCloseBtn) {
        chipCloseBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            resetUploadArea();
        });
    }

    function resetUploadArea() {
        fileInput.value = '';
        fileChip.style.display = 'none';
        uploadPlaceholder.style.display = 'block';
        uploadArea.style.padding = '2.5rem 1.5rem';
        hideUploadError();
        setSubmitLoading(false);
        updateSubmitMeta();
    }

    // ===== Section Transitions =====
    function showSection(el) {
        el.classList.remove('fade-hidden', 'fade-out');
        el.style.display = 'block';
        // force reflow
        void el.offsetHeight;
        el.classList.add('fade-section');
    }

    function hideSection(el) {
        el.classList.add('fade-out');
        setTimeout(() => {
            el.style.display = 'none';
            el.classList.remove('fade-out');
        }, 250);
    }

    // ===== Alert =====
    function showAlert(msg) {
        alertBox.textContent = msg;
        alertBox.style.display = 'block';
    }
    function hideAlert() {
        alertBox.style.display = 'none';
    }

    function buildFriendlyErrorMessage(error) {
        const raw = (error && error.message) ? String(error.message) : '提交失败';
        const isNetworkPolicy403 = /\b403\b|access denied|virtual network|firewall/i.test(raw);
        if (!isNetworkPolicy403) {
            return raw;
        }

        return [
            '模型服务访问被策略拦截（403）。',
            '请检查：1) VPN/代理路由是否命中企业白名单出口 2) Clash 是否把 openai.azure.com 走 DIRECT 或企业 VPN 3) Azure 防火墙/VNet 是否已放行当前出口IP。',
            `原始错误: ${raw}`,
        ].join(' ');
    }

    // ===== Toast =====
    function showToast(msg, duration = 4000) {
        const toast = $('#toast');
        toast.textContent = msg;
        toast.classList.add('show');
        setTimeout(() => toast.classList.remove('show'), duration);
    }

    async function handleManualDownloadClick(e) {
        if (!manualDownloadBtn) return;

        if (manualDownloadBtn.classList.contains('disabled')) {
            e.preventDefault();
            showToast('下载链接尚未就绪，请稍后再试。');
            return;
        }

        e.preventDefault();
        hideAlert();

        const downloadUrl = manualDownloadBtn.getAttribute('href');
        const downloadName = manualDownloadBtn.getAttribute('download') || 'translated.docx';
        const labelEl = manualDownloadBtn.querySelector('.dl-text');
        const originalLabel = labelEl ? labelEl.textContent : '';

        if (!downloadUrl || downloadUrl === '#') {
            showAlert('❌ 下载链接无效，请返回首页后重新提交任务。');
            showToast('下载失败：链接无效。');
            return;
        }

        manualDownloadBtn.classList.add('disabled');
        manualDownloadBtn.setAttribute('aria-busy', 'true');
        if (labelEl) {
            labelEl.textContent = '下载中...';
        }

        try {
            const res = await fetchWithTimeout(downloadUrl, { method: 'GET' }, DOWNLOAD_TIMEOUT_MS);
            if (!res.ok) {
                throw new Error(`下载失败(${res.status})`);
            }

            const blob = await res.blob();
            if (!blob || blob.size === 0) {
                throw new Error('下载内容为空');
            }

            const blobUrl = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = blobUrl;
            a.download = downloadName;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(blobUrl);

            showToast('下载已开始。');
        } catch (err) {
            const timeoutHit = err && err.name === 'AbortError';
            const failReason = timeoutHit ? '下载请求超时，服务可能繁忙。' : ((err && err.message) ? String(err.message) : '未知错误');
            showAlert(`❌ ${failReason} 可稍后重试下载；若连续失败，请返回首页重新翻译该文档。`);
            showToast('下载失败，请重试。');
        } finally {
            manualDownloadBtn.classList.remove('disabled');
            manualDownloadBtn.removeAttribute('aria-busy');
            if (labelEl) {
                labelEl.textContent = originalLabel || `下载 ${downloadName}`;
            }
        }
    }

    function formatDuration(sec) {
        const n = Math.max(0, Number(sec) || 0);
        if (n < 60) return `${n}s`;
        const m = Math.floor(n / 60);
        const s = n % 60;
        return s ? `${m}m ${s}s` : `${m}m`;
    }

    function getFileTypeLabel(statusData, originalFileName) {
        const ext = (statusData && statusData.file_type) || getFileExtension(originalFileName || '');
        return FILE_TYPE_LABELS[ext] || (ext ? ext.toUpperCase().replace('.', '') : '文档');
    }

    function setDetailLines(lines) {
        if (!detailContent) return;
        const safeLines = (lines || []).filter(Boolean);
        detailContent.innerHTML = safeLines.map(line => `<div>${line}</div>`).join('');
    }

    function describeProcessingPhase(phase, statusData) {
        const current = statusData?.progress?.current || 0;
        const total = statusData?.progress?.total || 0;
        const stagnantSeconds = statusData?.seconds_since_update || 0;

        let main = phase || '服务器处理中';
        let hint = '文档正在处理中，请保持页面打开。';

        if (/排版|回填|最后检查|质量|预览/i.test(main)) {
            main = '正在还原原文排版';
            hint = '正在把译文套回原始版式，复杂文档会慢一些。';
        } else if (/调用模型|翻译|批次/i.test(main)) {
            main = '正在请求模型翻译';
            hint = '这一步由大模型负责，PPT 与大文件会耗时较长，属于正常现象。';
        } else if (/解析|结构/i.test(main)) {
            main = '正在拆分文档内容';
            hint = '这一步会识别文本、表格、图片区域，通常很快完成。';
        }

        if (stagnantSeconds >= 60) {
            hint = `当前阶段已连续 ${formatDuration(stagnantSeconds)} 没有新进度，大文件是正常现象；若持续数分钟仍不变，可考虑重试。`;
        } else if (stagnantSeconds >= 25) {
            hint = `当前阶段已持续 ${formatDuration(stagnantSeconds)}，仍在预期范围内，请耐心等待。`;
        }

        if (total > 0) {
            main += ` （${current}/${total}）`;
        }

        return { main, hint };
    }

    function renderQualityMetrics(statusData) {
        const summaryEl = $('#resultQualitySummary');
        const wrapEl = $('#resultQualityWrap');
        const panel = $('#resultQualityDetails');
        if (!panel || !summaryEl || !wrapEl) return;

        // reset
        summaryEl.style.display = 'none';
        summaryEl.className = 'qa-summary-line';
        summaryEl.textContent = '';
        wrapEl.style.display = 'none';
        wrapEl.open = false;
        panel.innerHTML = '';

        const qData = statusData && statusData.quality;
        if (!qData || typeof qData !== 'object') return;

        const stats = qData.stats || {};
        const targetLang = qData.target_lang || statusData.target_lang || '';
        const sourceLang = qData.source_lang_detected || 'Unknown';

        const langLabel = (lang) => {
            const map = {
                Chinese: '中文',
                English: '英文',
                Japanese: '日文',
                Unknown: '未知语言',
            };
            return map[lang] || lang;
        };
        const skipped = Array.isArray(qData.checks_skipped) && qData.checks_skipped.includes('qa');
        const visualReview = Boolean(statusData.visual_review_required);
        const issueCount = Array.isArray(qData.issues) ? qData.issues.length : 0;

        // 一句话结论
        let tone = 'success';
        let summaryText = '';
        if (skipped) {
            tone = 'skip';
            summaryText = '快速模式已跳过质量检查，文件可直接下载。';
        } else if (issueCount > 0) {
            tone = 'danger';
            summaryText = `检测发现 ${issueCount} 项明确问题，建议打开详细查看。`;
        } else if (visualReview) {
            tone = 'warn';
            summaryText = '主要检测已通过，但建议人工快速复看一眼。';
        } else {
            tone = 'success';
            summaryText = '所有质检项均已通过，可直接使用。';
        }
        summaryEl.className = `qa-summary-line qa-tone-${tone}`;
        summaryEl.textContent = summaryText;
        summaryEl.style.display = 'block';

        // 详细指标（可折叠）
        const lines = [];
        if (qData.summary && qData.summary !== summaryText) {
            lines.push(`内部结论：${qData.summary}`);
        }
        if (stats.cjk_source_segments != null && stats.unchanged_segments != null) {
            const total = Number(stats.cjk_source_segments) || 0;
            const unchanged = Number(stats.unchanged_segments) || 0;
            const ratio = total > 0 ? `${((unchanged / total) * 100).toFixed(1)}%` : '0.0%';
            lines.push(`未翻译比：${unchanged}/${total} (${ratio})`);
        }
        if (sourceLang !== 'Unknown' && sourceLang !== targetLang && stats.source_residual_segments != null && stats.output_segments != null) {
            const residual = Number(stats.source_residual_segments) || 0;
            const outSeg = Number(stats.output_segments) || 0;
            const ratio = outSeg > 0 ? `${((residual / outSeg) * 100).toFixed(1)}%` : '0.0%';
            lines.push(`源语言残留（${langLabel(sourceLang)}）：${residual}/${outSeg} (${ratio})`);
        }
        if (typeof qData.filename_translation_ok === 'boolean') {
            lines.push(`文件名翻译检查：${qData.filename_translation_ok ? '通过' : '未通过'}`);
        }
        if (issueCount > 0) {
            lines.push(`问题条目数：${issueCount}`);
        }

        if (lines.length > 0) {
            panel.innerHTML = lines.map((line) => `<div class="qa-line">${line}</div>`).join('');
            wrapEl.style.display = 'block';
            // 默认只在有问题时展开
            wrapEl.open = (tone === 'danger');
        }
    }

    function setProgressStage(state, icon, label) {
        if (!progressContainer) return;

        progressContainer.classList.remove(
            'progress-state-pending',
            'progress-state-processing',
            'progress-state-completed',
            'progress-state-retrying',
            'progress-state-failed'
        );
        progressContainer.classList.add(`progress-state-${state}`);

        if (progressStagePill) {
            progressStagePill.className = `progress-stage-pill progress-state-${state}`;
        }
        if (progressStageIcon) {
            progressStageIcon.textContent = icon;
        }
        if (progressStageLabel) {
            progressStageLabel.textContent = label;
        }

        setProgressActionPriority(state);
    }

    function getProcessingStageMeta(phase) {
        const text = String(phase || '').trim();

        if (/解析|结构|拆分|读取|提取/i.test(text)) {
            return { icon: '🧩', label: '解析中' };
        }
        if (/翻译|调用模型|批次|术语|润色/i.test(text)) {
            return { icon: '🌐', label: '翻译中' };
        }
        if (/回填|重组|排版|还原|写回|合并/i.test(text)) {
            return { icon: '🧱', label: '回填中' };
        }
        if (/质量|质检|检查|校验|验证|预览|检查点/i.test(text)) {
            return { icon: '🔎', label: '质检中' };
        }

        return { icon: '⚙️', label: '处理中' };
    }

    function isProgressVisible() {
        return progressContainer && progressContainer.style.display !== 'none';
    }

    function closeConfirmDialog(result) {
        if (!confirmOverlay) return;
        confirmOverlay.classList.remove('active');
        confirmOverlay.setAttribute('aria-hidden', 'true');
        const resolver = confirmResolver;
        confirmResolver = null;
        if (typeof resolver === 'function') {
            resolver(Boolean(result));
        }
    }

    function openConfirmDialog({
        title = '请确认操作',
        message = '确认继续吗？',
        okText = '确定',
        cancelText = '取消'
    } = {}) {
        if (!confirmOverlay || !confirmOkBtn || !confirmCancelBtn || !confirmMessage || !confirmTitle) {
            return Promise.resolve(window.confirm(message));
        }

        if (confirmResolver) {
            closeConfirmDialog(false);
        }

        confirmTitle.textContent = title;
        confirmMessage.textContent = message;
        confirmOkBtn.textContent = okText;
        confirmCancelBtn.textContent = cancelText;

        confirmOverlay.classList.add('active');
        confirmOverlay.setAttribute('aria-hidden', 'false');

        return new Promise((resolve) => {
            confirmResolver = resolve;
            confirmCancelBtn.focus();
        });
    }



    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && confirmOverlay?.classList.contains('active')) {
            closeConfirmDialog(false);
        }
    });

    confirmOverlay?.addEventListener('click', (e) => {
        if (e.target === confirmOverlay) {
            closeConfirmDialog(false);
        }
    });

    confirmCancelBtn?.addEventListener('click', () => closeConfirmDialog(false));
    confirmOkBtn?.addEventListener('click', () => closeConfirmDialog(true));
    manualDownloadBtn?.addEventListener('click', handleManualDownloadClick);

    window.addEventListener('storage', (e) => {
        if (e.key !== TASK_OWNER_KEY) return;
        if (!currentTrackingTaskId) return;

        const owner = loadTaskOwnerMeta();
        if (!owner || owner.taskId !== currentTrackingTaskId || owner.tabId === TAB_ID) {
            return;
        }

        blockCrossTabTaskView(currentTrackingTaskId, String(owner.mode || 'BALANCED'), owner);
        showToast('该任务已在其他页面操作，当前页不可查看。');
    });

    // ===== Form Submission =====
    window.resetForm = function () {
        setRetryButtonBlockedMode(false);
        activeSubmissionId += 1;
        if (activePollTimer) {
            clearTimeout(activePollTimer);
            activePollTimer = null;
        }
        clearActiveTaskMeta();
        releaseTaskOwnership(currentTrackingTaskId || undefined);
        currentTrackingTaskId = null;
        resetUploadArea();
        progressContainer.style.display = 'none';
        resultCard.style.display = 'none';
        form.style.display = 'block';
        form.classList.remove('fade-out');
        hideAlert();
        setSubmitLoading(false);
        updateSubmitMeta();
    };

    progressBackHomeBtn?.addEventListener('click', async () => {
        if (isProgressVisible()) {
            const confirmed = await openConfirmDialog({
                title: '返回首页确认',
                message: '当前任务可能仍在执行，返回首页会停止当前页面轮询。确定返回首页吗？',
                okText: '确定返回',
                cancelText: '继续查看进度'
            });
            if (!confirmed) return;
        }
        window.resetForm();
    });

    progressRetryBtn?.addEventListener('click', async () => {
        if (isRetryButtonBlocked) {
            window.resetForm();
            return;
        }

        if (!fileInput.files || fileInput.files.length === 0) {
            showToast('未找到可重试的文件，请返回首页重新选择文件。');
            return;
        }

        if (isProgressVisible()) {
            const confirmed = await openConfirmDialog({
                title: '重新翻译确认',
                message: '将重新提交同一文档并开启新的任务追踪，当前页面的旧进度将被替换。确定继续吗？',
                okText: '确定重试',
                cancelText: '取消'
            });
            if (!confirmed) return;
        }

        activeSubmissionId += 1;
        if (activePollTimer) {
            clearTimeout(activePollTimer);
            activePollTimer = null;
        }

        showToast('正在重新提交该文档...');
        form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
    });

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        hideAlert();

        const submissionId = ++activeSubmissionId;
        if (activePollTimer) {
            clearTimeout(activePollTimer);
            activePollTimer = null;
        }

        if (!fileInput.files || fileInput.files.length === 0) {
            showUploadError('请先选择一个需要翻译的文件');
            return;
        }

        const formData = new FormData(form);
        const startTime = Date.now();
        const originalFileName = fileInput.files[0].name;
        setSubmitLoading(true, '开始翻译');

        // Transition: form → progress
        hideSection(form);
        setTimeout(() => {
            showSection(progressContainer);
            bar.classList.add('indeterminate');
            bar.style.width = '';
            setProgressStage('pending', '⏳', '任务排队');
            txtMain.textContent = '任务提交中...';
            txtSub.textContent = '';
            if (detailContent) detailContent.textContent = '';
        }, 260);

        try {
            const response = await fetchWithTimeout('/translate', { method: 'POST', body: formData }, SUBMIT_TIMEOUT_MS);
            if (!response.ok) {
                const errData = await response.json().catch(() => ({}));
                throw new Error(errData.error || '提交失败');
            }
            const { task_id } = await response.json();
            const modeStr = (formData.get('speed_mode') || 'balanced').toUpperCase();

            saveActiveTaskMeta({
                taskId: task_id,
                mode: modeStr,
                fileName: originalFileName,
                createdAt: Date.now(),
                tabId: TAB_ID,
            });

            beginTaskTracking({
                submissionId,
                taskId: task_id,
                modeStr,
                originalFileName,
                startTime,
            });

        } catch (error) {
            if (submissionId !== activeSubmissionId) return;
            if (activePollTimer) {
                clearTimeout(activePollTimer);
                activePollTimer = null;
            }
            clearActiveTaskMeta();
            releaseTaskOwnership(currentTrackingTaskId || undefined);
            currentTrackingTaskId = null;
            setProgressStage('failed', '❌', '提交失败');
            hideSection(progressContainer);
            const timeoutHit = error && error.name === 'AbortError';
            const message = timeoutHit
                ? '提交请求超时，服务可能繁忙。已保留已选文件，可直接再次点击“开始翻译”。'
                : (buildFriendlyErrorMessage(error) + ' 已保留已选文件，可直接再次点击“开始翻译”。');
            setTimeout(() => {
                showSection(form);
                updateSubmitMeta();
                showAlert('❌ ' + message);
            }, 280);
        } finally {
            setSubmitLoading(false);
        }
    });

    // Ensure initial footer meta and disabled state are correct.
    setRetryButtonBlockedMode(false);
    setSubmitLoading(false);
    updateSubmitMeta();

})();

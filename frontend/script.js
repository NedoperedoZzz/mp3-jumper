// Базовый URL бэкенда. Задаётся в index.html (window.MP3_API_BASE).
// GitHub Pages умеет отдавать только статику, поэтому реальный FastAPI
// должен жить на другом хостинге (Render/Fly/Railway/VPS) и быть
// разрешён в CORS. Пустая строка = тот же источник (локальная разработка).
const API_BASE = (window.MP3_API_BASE ?? "").replace(/\/+$/, "");
const apiUrl = (path) => `${API_BASE}${path}`;

// --- Состояние бэкенда -------------------------------------------------
// Страница умеет жить отдельно от API (GitHub Pages), поэтому честно
// сообщаем, есть ли рядом FastAPI: /api/health отвечает за склейку и за то,
// настроена ли LLM (Render/Fly локальный Ollama иметь не может в принципе).
let backendOnline = null;
let llmReady = false;

function setBackendStatus(text, kind) {
    const badge = document.getElementById('backendStatus');
    if (!badge) return;
    badge.textContent = text;
    badge.className = `backend-status backend-status--${kind}`;
}

async function checkBackend() {
    setBackendStatus('Проверяю соединение с бэкендом\u2026', 'checking');
    try {
        const res = await fetch(apiUrl('/api/health'), { method: 'GET' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const info = await res.json();
        backendOnline = true;
        llmReady = !!(info.llm && info.llm.configured);
        if (!info.ffmpeg) {
            setBackendStatus('Бэкенд на связи, но на сервере нет FFmpeg — склейка невозможна.', 'warn');
        } else if (llmReady) {
            setBackendStatus(`Бэкенд на связи. ИИ: ${info.llm.provider}/${info.llm.model}.`, 'ok');
        } else {
            setBackendStatus(`Склейка работает. ИИ выключен: ${info.llm.reason || 'модель не настроена'}.`, 'warn');
        }
    } catch (err) {
        backendOnline = false;
        llmReady = false;
        const reason = API_BASE
            ? `Бэкенд ${API_BASE} не отвечает (${err.message}). Это может быть сон бесплатного тарифа после простоя или запрет CORS. Повторите проверку.`
            : 'Бэкенд не подключён (window.MP3_API_BASE пуст): страница работает как витрина. Склейка и ИИ требуют запущенного FastAPI — см. docs/BACKEND.md.';
        setBackendStatus(reason + ' Нажмите на строку, чтобы проверить снова.', 'off');
    }
}

async function errorFromResponse(res) {
    try {
        const body = await res.json();
        if (body && (body.error || body.detail)) {
            return typeof body.detail === 'string' ? body.detail : body.error;
        }
    } catch (e) { /* тело не JSON (например, 404 от GitHub Pages) */ }
    return `ошибка сервера (${res.status})`;
}

let currentSessionId = null;
let selectedFiles = [];

// 1. Загрузка файлов
document.getElementById('fileInput').addEventListener('change', (e) => {
    const newFiles = Array.from(e.target.files);
    selectedFiles = selectedFiles.concat(newFiles);
    e.target.value = '';
    renderFileList();
});

// 2. Отрисовка списка с Drag-and-Drop
function renderFileList() {
    const list = document.getElementById('fileList');
    list.innerHTML = '';
    selectedFiles.forEach((file, index) => {
        const li = document.createElement('li');
        li.draggable = true;
        li.dataset.index = index;
        li.innerHTML = `
            <span class="drag-icon">≡</span>
            <span class="track-title"><b>${index + 1}.</b> ${file.name}</span>
            <span class="delete-btn" title="Удалить трек" onclick="removeFile(event, ${index})">🗑️</span>
        `;
        li.addEventListener('dragstart', handleDragStart);
        li.addEventListener('dragover', handleDragOver);
        li.addEventListener('drop', handleDrop);
        li.addEventListener('dragend', handleDragEnd);
        list.appendChild(li);
    });
    document.getElementById('mergeBtn').disabled = selectedFiles.length < 2;
}

function removeFile(event, index) {
    event.stopPropagation();
    selectedFiles.splice(index, 1);
    renderFileList();
    if (selectedFiles.length === 0) {
        document.getElementById('fileInput').value = '';
    }
}

let dragSrcEl = null;
function handleDragStart(e) {
    dragSrcEl = this;
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/html', this.innerHTML);
    this.classList.add('dragging');
}
function handleDragOver(e) {
    if (e.preventDefault) e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    return false;
}
function handleDrop(e) {
    if (e.stopPropagation) e.stopPropagation();
    if (dragSrcEl !== this) {
        const oldIndex = parseInt(dragSrcEl.dataset.index);
        const newIndex = parseInt(this.dataset.index);
        const movedItem = selectedFiles.splice(oldIndex, 1)[0];
        selectedFiles.splice(newIndex, 0, movedItem);
        renderFileList();
    }
    return false;
}
function handleDragEnd(e) {
    this.classList.remove('dragging');
}

// 3. Отправка на сервер
document.getElementById('mergeBtn').addEventListener('click', async () => {
    const btn = document.getElementById('mergeBtn');
    const progress = document.getElementById('progressContainer');
    const smartMode = document.getElementById('smartMode').checked;
    const formData = new FormData();

    selectedFiles.forEach(file => formData.append('files', file));
    formData.append('use_smart', smartMode ? 'true' : 'false');

    btn.style.display = 'none';
    progress.style.display = 'block';

    try {
        const res = await fetch(apiUrl('/api/merge'), { method: 'POST', body: formData });
        if (!res.ok) throw new Error(await errorFromResponse(res));
        const data = await res.json();
        currentSessionId = data.session_id;
        progress.style.display = 'none';

        document.getElementById('resultSection').style.display = 'block';
        document.getElementById('audioPlayer').src = apiUrl(`/api/download/${currentSessionId}`);

        const tsRes = await fetch(apiUrl(`/api/timestamps/${currentSessionId}`));
        if (tsRes.ok) {
            const tsData = await tsRes.json();
            const tsDiv = document.getElementById('timestamps');
            const tsList = document.getElementById('tsList');
            tsList.innerHTML = '';
            tsData.forEach((ts, i) => {
                const formatTime = (sec) => {
                    const m = Math.floor(sec / 60);
                    const s = Math.floor(sec % 60);
                    return `${m}:${s < 10 ? '0' : ''}${s}`;
                };
                tsList.innerHTML += `<li style="margin-bottom:5px;">Трек ${i+1} (<span style="color:#fff">${ts.track}</span>): конец в <b>${formatTime(ts.end)}</b></li>`;
            });
            tsDiv.style.display = 'block';
        }
    } catch (err) {
        alert(`Не получилось склеить: ${err.message}`);
        progress.style.display = 'none';
        btn.style.display = 'block';
    }
});

// ИИ-название
document.getElementById('generateTitleBtn').addEventListener('click', async () => {
    const btn = document.getElementById('generateTitleBtn');
    if (!currentSessionId) {
        alert("Сначала склейте треки: сервер предлагает название по метаданным готового микса.");
        return;
    }
    const formData = new FormData();
    formData.append('session_id', currentSessionId);
    btn.textContent = "Генерация...";
    try {
        const res = await fetch(apiUrl('/api/generate-title'), { method: 'POST', body: formData });
        if (!res.ok) throw new Error(await errorFromResponse(res));
        const data = await res.json();
        document.getElementById('mixTitle').value = data.title;
    } catch (err) {
        alert(`ИИ не сгенерировал название: ${err.message}`);
    } finally {
        btn.textContent = "✨ Сгенерировать ИИ";
    }
});

// Скачивание
document.getElementById('downloadBtn').addEventListener('click', () => {
    let title = document.getElementById('mixTitle').value.trim();
    if (!title) title = "my_mix";
    if (!title.toLowerCase().endsWith("(mix)")) title += " (Mix)";
    window.location.href = apiUrl(`/api/download/${currentSessionId}?filename=${encodeURIComponent(title)}.mp3`);
});

// Сброс
document.getElementById('resetBtn').addEventListener('click', () => {
    selectedFiles = [];
    currentSessionId = null;
    document.getElementById('fileInput').value = '';
    renderFileList();
    const audio = document.getElementById('audioPlayer');
    audio.pause();
    audio.src = '';
    document.getElementById('resultSection').style.display = 'none';
    document.getElementById('timestamps').style.display = 'none';
    document.getElementById('mixTitle').value = 'my_mix';
    document.getElementById('mergeBtn').style.display = 'block';
    document.getElementById('mergeBtn').disabled = true;
});

// Проверка бэкенда при загрузке и по клику на плашку
checkBackend();
document.getElementById('backendStatus')?.addEventListener('click', checkBackend);
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
let backendOnline = null; // null = ещё не проверяли
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
            setBackendStatus('Бэкенд на связи, но на сервере нет FFmpeg \u2014 склейка невозможна.', 'warn');
        } else if (llmReady) {
            setBackendStatus(`Бэкенд на связи. ИИ: ${info.llm.provider}/${info.llm.model}.`, 'ok');
        } else {
            setBackendStatus(`Склейка работает. ИИ выключен: ${info.llm.reason || 'модель не настроена'}.`, 'warn');
        }
    } catch (err) {
        backendOnline = false;
        llmReady = false;
        // Разные причины по-разному и объясняем: адрес не задан (витрина)
        // или задан, но сервер молчит (CORS, сон бесплатного тарифа, неверный URL).
        const reason = API_BASE
            ? `Бэкенд ${API_BASE} не отвечает (${err.message}). Это может быть сон бесплатного тарифа после простоя или запрет CORS. Повторите проверку.`
            : 'Бэкенд не подключён (window.MP3_API_BASE пуст): страница работает как витрина. Склейка и ИИ требуют запущенного FastAPI \u2014 см. docs/BACKEND.md.';
        setBackendStatus(reason + ' Нажмите на строку, чтобы проверить снова.', 'off');
    }
}

// Описание ошибок для alert: без него пользователь видит «Произошла ошибка»,
// а настоящих причин три: нет бэкенда (404/CORS), упал ffmpeg (500), не настроена LLM (503).
async function errorFromResponse(res) {
    try {
        const body = await res.json();
        if (body && (body.error || body.detail)) {
            return typeof body.detail === 'string' ? body.detail : body.error;
        }
    } catch (e) {
        /* тело не JSON (например, 404 от GitHub Pages) */
    }
    return `ошибка сервера (${res.status})`;
}


let currentSessionId = null;
let selectedFiles = []; // Массив для хранения файлов в правильном порядке

// 1. Загрузка файлов
document.getElementById('fileInput').addEventListener('change', (e) => {
    // Добавляем новые файлы к уже существующим
    const newFiles = Array.from(e.target.files);
    selectedFiles = selectedFiles.concat(newFiles);

    // Очищаем нативный инпут, чтобы можно было выбрать те же файлы снова,
    // и чтобы счетчик "N files" не путал
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
                // Добавляем span с корзиной в конец
        li.innerHTML = `
            <span class="drag-icon">≡</span>
            <span class="track-title"><b>${index + 1}.</b> ${file.name}</span>
            <span class="delete-btn" title="Удалить трек" onclick="removeFile(event, ${index})">🗑️</span>
        `;
        // Логика перетаскивания
        li.addEventListener('dragstart', handleDragStart);
        li.addEventListener('dragover', handleDragOver);
        li.addEventListener('drop', handleDrop);
        li.addEventListener('dragend', handleDragEnd);

        list.appendChild(li);
    });

    document.getElementById('mergeBtn').disabled = selectedFiles.length < 2;
}

// Функция удаления файла из списка
function removeFile(event, index) {
    event.stopPropagation(); // Чтобы не срабатывал drag-and-drop
    selectedFiles.splice(index, 1);
    renderFileList();

    // Если файлов не осталось, сбрасываем input
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

        // Меняем элементы в массиве местами
        const movedItem = selectedFiles.splice(oldIndex, 1)[0];
        selectedFiles.splice(newIndex, 0, movedItem);

        renderFileList(); // Перерисовываем нумерацию
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
    // ВАЖНО: Отправляем файлы строго в том порядке, в котором они в массиве!
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
                // Загружаем тайм-коды
        const tsRes = await fetch(apiUrl(`/api/timestamps/${currentSessionId}`));
        if (tsRes.ok) {
            const tsData = await tsRes.json();
            const tsDiv = document.getElementById('timestamps');
            const tsList = document.getElementById('tsList');
            tsList.innerHTML = '';
            tsData.forEach((ts, i) => {
                // Красиво форматируем время (например, 03:45)
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

// Остальные функции (generateTitleBtn, downloadBtn) остаются без изменений
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
        // 503 = бэкенд жив, но модель недоступна (на Render её обычно нет)
        alert(`ИИ не сгенерировал название: ${err.message}`);
    } finally {
        btn.textContent = "✨ Сгенерировать ИИ";
    }
});

document.getElementById('downloadBtn').addEventListener('click', () => {
    let title = document.getElementById('mixTitle').value.trim();

    // Если пользователь ничего не ввел, используем дефолтное
    if (!title) {
        title = "my_mix";
    }

    // Проверяем, нет ли уже "(Mix)" в конце названия, чтобы не дублировать
    if (!title.toLowerCase().endsWith("(mix)")) {
        title += " (Mix)";
    }

    // Формируем URL с правильным названием
    window.location.href = apiUrl(`/api/download/${currentSessionId}?filename=${encodeURIComponent(title)}.mp3`);
});

// Логика кнопки "Создать новый микс"
document.getElementById('resetBtn').addEventListener('click', () => {
    // 1. Очищаем данные
    selectedFiles = [];
    currentSessionId = null;

    // 2. Очищаем поле ввода файлов
    document.getElementById('fileInput').value = '';

    // 3. Обновляем список (он станет пустым)
    renderFileList();

    // 4. Останавливаем и сбрасываем плеер
    const audio = document.getElementById('audioPlayer');
    audio.pause();
    audio.src = '';

    // 5. Прячем секцию с результатом и тайм-кодами
    document.getElementById('resultSection').style.display = 'none';
    document.getElementById('timestamps').style.display = 'none';
    document.getElementById('mixTitle').value = 'my_mix'; // Сброс названия

    // 6. Возвращаем кнопку "Объединить в микс" на место
    document.getElementById('mergeBtn').style.display = 'block';
    document.getElementById('mergeBtn').disabled = true;
});

// Проверка бэкенда при загрузке и по клику на плашку (повторная попытка).
checkBackend();
document.getElementById('backendStatus')?.addEventListener('click', checkBackend);

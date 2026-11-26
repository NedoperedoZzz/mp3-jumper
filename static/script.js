// MixMaster, браузерная версия v2.1.
// Исправление v2.1: оба режима декодируют звук в PCM и кодируют заново.
// Сырая склейка MP3-кадров из v2 оказалась ненадёжной: разные sample rate,
// битрейты и Xing-заголовки заставляли плееры играть результат с артефактами
// (вплоть до повторов первого трека). Декодирование нормализует всё в
// стерео 44.1 кГц, и стыки становятся чистыми.
// ИИ-кнопка отключена: ей нужен сервер с секретным ключом, а ключ в коде
// страницы стал бы публичным.

const CROSSFADE_SEC = 3;      // максимальная длина перехода в «умном» режиме
const LIMIT_MIN = 20;         // предупреждение о памяти для длинных миксов
const MP3_BITRATE_KBPS = 192;
const SAMPLE_RATE = 44100;

let selectedFiles = [];
let mixUrl = null;

function setStatus(text, kind) {
  const badge = document.getElementById('backendStatus');
  if (!badge) return;
  badge.textContent = text;
  badge.className = `backend-status backend-status--${kind}`;
}

// Длительность из метаданных — для предварительной проверки объёма памяти.
function readDuration(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const audio = document.createElement('audio');
    audio.preload = 'metadata';
    audio.onloadedmetadata = () => {
      const d = audio.duration;
      URL.revokeObjectURL(url);
      if (isFinite(d) && d > 0) resolve(d);
      else reject(new Error(`Не удалось определить длительность: ${file.name}`));
    };
    audio.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error(`${file.name}: не читается как аудио`));
    };
    audio.src = url;
  });
}

async function guardLength(files) {
  let total = 0;
  for (const f of files) total += await readDuration(f);
  const min = total / 60;
  if (min > LIMIT_MIN &&
      !confirm(`Микс ~${min.toFixed(0)} мин: обработка в браузере декодирует всё в память (~20 МБ/мин). Продолжить?`)) {
    throw new Error('склейка отменена: микс слишком длинный для обработки в браузере');
  }
}

// --- Декодирование: единый формат для всех треков ------------------------
async function decodeTracks(files, onProgress) {
  const decodeCtx = new OfflineAudioContext(2, 1, SAMPLE_RATE);
  const buffers = [];
  for (let i = 0; i < files.length; i++) {
    onProgress(`Декодирование трека ${i + 1} из ${files.length}…`);
    try {
      buffers.push(await decodeCtx.decodeAudioData(await files[i].arrayBuffer()));
    } catch (e) {
      throw new Error(`${files[i].name}: браузер не смог декодировать этот файл как аудио`);
    }
  }
  return buffers;
}

// --- Кодирование PCM -> MP3 (lamejs) --------------------------------------
function floatTo16pcm(channel) {
  const out = new Int16Array(channel.length);
  for (let i = 0; i < channel.length; i++) {
    const s = Math.max(-1, Math.min(1, channel[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}

function encodeMp3(audioBuffer, onProgress) {
  if (typeof lamejs === 'undefined') {
    throw new Error('Библиотека lamejs не загрузилась. Проверь, что lame.min.js лежит рядом и подключён в index.html.');
  }
  const encoder = new lamejs.Mp3Encoder(2, audioBuffer.sampleRate, MP3_BITRATE_KBPS);
  const left = floatTo16pcm(audioBuffer.getChannelData(0));
  const right = floatTo16pcm(audioBuffer.getChannelData(1));
  const chunk = 1152 * 32;
  const parts = [];
  for (let i = 0; i < left.length; i += chunk) {
    const encoded = encoder.encodeBuffer(left.subarray(i, i + chunk), right.subarray(i, i + chunk));
    if (encoded.length) parts.push(encoded);
    if ((i / chunk) % 16 === 0) {
      onProgress(`Кодирование в MP3: ${Math.min(100, Math.round((100 * i) / left.length))}%`);
    }
  }
  const tail = encoder.flush();
  if (tail.length) parts.push(tail);
  return new Blob(parts, { type: 'audio/mpeg' });
}

// --- Быстрый режим: склейка без переходов ---------------------------------
function concatBuffers(buffers) {
  const total = buffers.reduce((n, b) => n + b.length, 0);
  const ctx = new OfflineAudioContext(2, total, SAMPLE_RATE);
  const out = ctx.createBuffer(2, total, SAMPLE_RATE);
  let offset = 0;
  for (const b of buffers) {
    for (let ch = 0; ch < 2; ch++) {
      out.getChannelData(ch).set(b.getChannelData(ch), offset);
    }
    offset += b.length;
  }
  return out;
}

async function mergeFast(files, onProgress) {
  await guardLength(files);
  const buffers = await decodeTracks(files, onProgress);
  onProgress('Склейка без переходов…');
  const mixed = concatBuffers(buffers);
  onProgress('Кодирование в MP3: 0%');
  const blob = encodeMp3(mixed, onProgress);
  let acc = 0;
  const timestamps = buffers.map((b, i) => {
    acc += b.duration;
    return { track: files[i].name, end: acc };
  });
  return { blob, timestamps };
}

// --- Умный режим: кроссфейды ----------------------------------------------
function equalPowerCurve(steps, fadeIn) {
  const curve = new Float32Array(steps);
  for (let i = 0; i < steps; i++) {
    const t = steps === 1 ? 1 : i / (steps - 1);
    curve[i] = fadeIn ? Math.sqrt(t) : Math.sqrt(1 - t);
  }
  return curve;
}

async function mergeSmart(files, onProgress) {
  await guardLength(files);
  const buffers = await decodeTracks(files, onProgress);
  const xf = [];
  for (let i = 0; i < buffers.length - 1; i++) {
    xf.push(Math.min(CROSSFADE_SEC, buffers[i].duration / 2, buffers[i + 1].duration / 2));
  }
  const starts = [0];
  for (let i = 1; i < buffers.length; i++) {
    starts.push(starts[i - 1] + buffers[i - 1].duration - xf[i - 1]);
  }
  const total = starts[starts.length - 1] + buffers[buffers.length - 1].duration;
  const offline = new OfflineAudioContext(2, Math.ceil(total * SAMPLE_RATE), SAMPLE_RATE);
  buffers.forEach((buf, i) => {
    const src = offline.createBufferSource();
    src.buffer = buf;
    const gain = offline.createGain();
    const g = gain.gain;
    const t0 = starts[i];
    const d = buf.duration;
    const inXf = i > 0 ? xf[i - 1] : 0;
    const outXf = i < buffers.length - 1 ? xf[i] : 0;
    if (inXf > 0) {
      g.setValueCurveAtTime(equalPowerCurve(Math.max(2, Math.round(inXf * SAMPLE_RATE)), true), t0, inXf);
      g.setValueAtTime(1, t0 + inXf);
    } else {
      g.setValueAtTime(1, t0);
    }
    if (outXf > 0) {
      g.setValueAtTime(1, t0 + d - outXf);
      g.setValueCurveAtTime(equalPowerCurve(Math.max(2, Math.round(outXf * SAMPLE_RATE)), false), t0 + d - outXf, outXf);
    }
    src.connect(gain).connect(offline.destination);
    src.start(t0);
  });
  onProgress('Сведение переходов…');
  const rendered = await offline.startRendering();
  onProgress('Кодирование в MP3: 0%');
  const blob = encodeMp3(rendered, onProgress);
  const timestamps = buffers.map((buf, i) => ({ track: files[i].name, end: starts[i] + buf.duration }));
  return { blob, timestamps };
}

// --- Загрузка файлов и список с drag-and-drop -----------------------------
document.getElementById('fileInput').addEventListener('change', (e) => {
  selectedFiles = selectedFiles.concat(Array.from(e.target.files));
  e.target.value = '';
  renderFileList();
});

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
  if (selectedFiles.length === 0) document.getElementById('fileInput').value = '';
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
function handleDragEnd() {
  this.classList.remove('dragging');
}

// --- Склейка ----------------------------------------------------------------
document.getElementById('mergeBtn').addEventListener('click', async () => {
  const btn = document.getElementById('mergeBtn');
  const progress = document.getElementById('progressContainer');
  const smart = document.getElementById('smartMode').checked;
  // Диагностика: видно, какие именно файлы ушли в склейку (F12 → Console).
  console.log('merge:', selectedFiles.map((f) => `${f.name} (${f.size} байт)`));
  btn.style.display = 'none';
  progress.style.display = 'block';
  progress.textContent = 'Обработка…';
  try {
    const result = smart
      ? await mergeSmart(selectedFiles, (msg) => { progress.textContent = msg; })
      : await mergeFast(selectedFiles, (msg) => { progress.textContent = msg; });
    if (mixUrl) URL.revokeObjectURL(mixUrl);
    mixUrl = URL.createObjectURL(result.blob);
    document.getElementById('audioPlayer').src = mixUrl;
    const tsList = document.getElementById('tsList');
    tsList.innerHTML = '';
    const formatTime = (sec) => {
      const m = Math.floor(sec / 60);
      const s = Math.floor(sec % 60);
      return `${m}:${s < 10 ? '0' : ''}${s}`;
    };
    result.timestamps.forEach((ts, i) => {
      tsList.innerHTML += `<li style="margin-bottom:5px;">Трек ${i + 1} (<span style="color:#fff">${ts.track}</span>): конец в <b>${formatTime(ts.end)}</b></li>`;
    });
    document.getElementById('timestamps').style.display = 'block';
    document.getElementById('resultSection').style.display = 'block';
    progress.style.display = 'none';
  } catch (err) {
    alert(`Не получилось склеить: ${err.message}`);
    progress.style.display = 'none';
    btn.style.display = 'block';
  }
});

// --- ИИ-кнопка: честно отключена --------------------------------------------
const genBtn = document.getElementById('generateTitleBtn');
genBtn.disabled = true;
genBtn.title = 'ИИ-название требует сервера с секретным ключом модели. В бессерверной версии отключено, чтобы не публиковать ключ в коде страницы.';

// --- Скачивание ---------------------------------------------------------------
document.getElementById('downloadBtn').addEventListener('click', () => {
  if (!mixUrl) { alert('Сначала склей треки.'); return; }
  let title = document.getElementById('mixTitle').value.trim() || 'my_mix';
  if (!title.toLowerCase().endsWith('(mix)')) title += ' (Mix)';
  const a = document.createElement('a');
  a.href = mixUrl;
  a.download = `${title}.mp3`;
  document.body.appendChild(a);
  a.click();
  a.remove();
});

// --- Сброс -----------------------------------------------------------------------
document.getElementById('resetBtn').addEventListener('click', () => {
  selectedFiles = [];
  if (mixUrl) { URL.revokeObjectURL(mixUrl); mixUrl = null; }
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

setStatus('Бессерверный режим: склейка и скачивание выполняются в твоём браузере. ИИ-кнопка отключена (ей нужен сервер с ключом).', 'ok');
/* ─── YTDown App — Frontend Logic ───────────────────────────── */

'use strict';

// ── State ─────────────────────────────────────────────────────

const state = {
  videoInfo:         null,
  selectedQuality:   null,
  activeJobId:       null,
  progressSource:    null,

  // Playlist
  playlistInfo:      null,   // { playlist_id, title, entries, … }
  selectedVideoIds:  new Set(),
  batchJobIds:       [],
};

// ── DOM shortcuts ─────────────────────────────────────────────

const $ = id => document.getElementById(id);

// ── Init ──────────────────────────────────────────────────────

window.addEventListener('DOMContentLoaded', () => {
  checkStatus();
  loadHistory();

  // Allow pressing Enter in URL input
  $('urlInput').addEventListener('keydown', e => {
    if (e.key === 'Enter') fetchInfo();
  });

  // Auto-fetch when pasting
  $('urlInput').addEventListener('paste', () => {
    setTimeout(() => {
      const v = $('urlInput').value.trim();
      if (v.length > 10) fetchInfo();
    }, 80);
  });
});

// ── Server Status ─────────────────────────────────────────────

async function checkStatus() {
  try {
    const res  = await fetch('/api/status');
    const data = await res.json();
    const badge = $('ffmpegBadge');
    if (data.ffmpeg?.available) {
      badge.textContent  = `FFmpeg ${data.ffmpeg.version}`;
      badge.className    = 'badge badge-green';
    } else {
      badge.textContent  = 'FFmpeg: not found';
      badge.className    = 'badge badge-yellow';
    }
  } catch (_) {
    $('ffmpegBadge').textContent = 'Server error';
    $('ffmpegBadge').className   = 'badge badge-dim';
  }
}

// ── Fetch Video Info ──────────────────────────────────────────

async function fetchInfo() {
  const url = $('urlInput').value.trim();
  if (!url) return;

  setFetchLoading(true);
  hide('inputError');
  hide('playlistSection');
  hide('videoSection');
  hide('qualitySection');
  hide('progressSection');
  hide('doneSection');
  hide('errorSection');
  state.playlistInfo = null;
  state.videoInfo    = null;

  try {
    // Auto-detect playlist URL
    if (url.includes('list=')) {
      const res  = await fetch('/api/playlist-info', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
      });
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      state.playlistInfo = data;
      renderPlaylist(data);
      show('playlistSection');
    } else {
      const res  = await fetch('/api/info', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
      });
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      state.videoInfo = data;
      renderVideoPreview(data);
      renderQualityGrid(data);
      show('videoSection');
      show('qualitySection');
    }
  } catch (err) {
    showInputError(err.message);
  } finally {
    setFetchLoading(false);
  }
}

// ── Playlist rendering ────────────────────────────────────────

function renderPlaylist(playlist) {
  $('playlistTitle').textContent   = playlist.title || 'Untitled Playlist';
  $('playlistChannel').textContent = playlist.channel || '';
  $('playlistCount').textContent   = `${playlist.video_count} videos`;

  state.selectedVideoIds = new Set(playlist.entries.map(e => e.video_id));

  const container = $('playlistEntries');
  container.innerHTML = playlist.entries.map(e => {
    const dur = e.duration ? formatTime(e.duration) : '?';
    return `
      <div class="pl-entry checked" id="ple-${e.video_id}" onclick="togglePlaylistEntry('${e.video_id}')">
        <span class="pl-check">✓</span>
        <img class="pl-thumb" src="${escHtml(e.thumbnail)}" alt="" loading="lazy" />
        <div class="pl-info">
          <div class="pl-title">${escHtml(e.title)}</div>
          <div class="pl-dur">${dur}</div>
        </div>
        <span class="pl-idx">${e.index}</span>
      </div>
    `;
  }).join('');

  updateSelectedCount();
  show('plDownloadBtn');
}

function togglePlaylistEntry(videoId) {
  if (state.selectedVideoIds.has(videoId)) {
    state.selectedVideoIds.delete(videoId);
    $(`ple-${videoId}`)?.classList.remove('checked');
  } else {
    state.selectedVideoIds.add(videoId);
    $(`ple-${videoId}`)?.classList.add('checked');
  }
  updateSelectedCount();
}

function selectAllPlaylist(select) {
  if (!state.playlistInfo) return;
  state.playlistInfo.entries.forEach(e => {
    if (select) state.selectedVideoIds.add(e.video_id);
    else state.selectedVideoIds.delete(e.video_id);
    $(`ple-${e.video_id}`)?.classList.toggle('checked', select);
  });
  updateSelectedCount();
}

function updateSelectedCount() {
  const n = state.selectedVideoIds.size;
  $('selectedCount').textContent = `${n} selected`;
  $('plDownloadBtnText').textContent = n
    ? `Download ${n} video${n > 1 ? 's' : ''}`
    : 'Download Selected';
  $('plDownloadBtn').classList.toggle('hidden', n === 0);
}

function onPlAudioChange() {
  const on = $('plAudioToggle').checked;
  $('plAudioFormatRow').classList.toggle('hidden', !on);
  $('plQualityRow').classList.toggle('hidden', on);
}

async function startPlaylistDownload() {
  if (!state.playlistInfo || state.selectedVideoIds.size === 0) return;

  const quality     = $('plAudioToggle').checked ? 'best' : ($('plQualitySelect').value || 'best');
  const audio_only  = $('plAudioToggle').checked;
  const audio_format= document.querySelector('input[name="plaf"]:checked')?.value || 'm4a';

  try {
    const res = await fetch('/api/playlist-download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        video_ids:    [...state.selectedVideoIds],
        playlist_id:  state.playlistInfo.playlist_id,
        quality,
        audio_only,
        audio_format,
      }),
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    state.batchJobIds = data.job_ids || [];
    // Show feedback in history pane
    hide('playlistSection');
    showPlaylistQueued(data.total);
    refreshHistory();
  } catch (err) {
    alert('Failed to start download: ' + err.message);
  }
}

function showPlaylistQueued(total) {
  hide('doneSection');
  hide('errorSection');
  // Show a simple progress card
  show('progressSection');
  $('progressTitle').textContent = state.playlistInfo?.title || 'Playlist';
  $('progressStep').textContent  = `Queued ${total} video${total > 1 ? 's' : ''} — see history below`;
  setProgress(0);
}



function setFetchLoading(on) {
  $('fetchBtn').disabled   = on;
  $('fetchBtnText').classList.toggle('hidden', on);
  $('fetchSpinner').classList.toggle('hidden', !on);
}

function showInputError(msg) {
  const el = $('inputError');
  el.textContent = msg;
  show('inputError');
}

// ── Render Video Preview ──────────────────────────────────────

function renderVideoPreview(info) {
  $('thumbnail').src       = info.thumbnail;
  $('videoTitle').textContent   = info.title;
  $('videoChannel').textContent = info.channel;
  $('durationBadge').textContent = info.duration_str;

  const sc = info.stream_counts;
  $('streamCounts').innerHTML = `
    <span class="count-pill">${sc.video} video streams</span>
    <span class="count-pill">${sc.audio} audio streams</span>
  `;
}

// ── Render Quality Grid ───────────────────────────────────────

function renderQualityGrid(info) {
  const grid      = $('qualityGrid');
  const audioOnly = $('audioOnlyToggle').checked;
  grid.innerHTML  = '';
  $('downloadBtn').classList.add('hidden');
  state.selectedQuality = null;

  if (audioOnly) {
    // Audio streams only
    const audioStreams = info.streams.filter(s => s.stream_type === 'audio');
    const seen = new Set();
    audioStreams.forEach(s => {
      const key = `${s.quality}|${s.ext}`;
      if (seen.has(key)) return;
      seen.add(key);
      grid.appendChild(makeQualityTile({
        quality:    s.quality,
        ext:        s.ext,
        filesize:   s.filesize,
        audio_only: true,
        isAudio:    true,
      }));
    });

    // Default: best audio
    if (audioStreams.length > 0) {
      const best = audioStreams[0];
      selectQuality(best.quality, true);
    }
  } else {
    // Video streams — deduplicate by quality+ext, prioritise mp4
    const videoStreams = info.streams.filter(s => s.stream_type === 'video' || s.stream_type === 'muxed');
    const byQuality   = {};
    videoStreams.forEach(s => {
      const q = s.quality;
      if (!byQuality[q] || s.ext === 'mp4') byQuality[q] = s;
    });

    const sorted = Object.values(byQuality).sort((a, b) =>
      qualityOrder(a.quality) - qualityOrder(b.quality)
    );

    sorted.forEach(s => {
      grid.appendChild(makeQualityTile({
        quality:    s.quality,
        ext:        s.ext,
        filesize:   s.filesize,
        audio_only: false,
        isAudio:    false,
      }));
    });

    // Default: best
    if (sorted.length > 0) selectQuality(sorted[0].quality, false);
  }

  $('noStreams').classList.toggle('hidden', grid.children.length > 0);
}

function makeQualityTile({ quality, ext, filesize, audio_only, isAudio }) {
  const tile = document.createElement('div');
  tile.className = `quality-tile${isAudio ? ' audio-tile' : ''}`;
  tile.dataset.quality    = quality;
  tile.dataset.audio_only = audio_only;
  tile.onclick = () => selectQuality(quality, audio_only);

  const size = filesize ? formatBytes(filesize) : '';
  tile.innerHTML = `
    <span class="qt-label">${quality}</span>
    <span class="qt-sub">${ext}${size ? ' · ~' + size : ''}</span>
  `;
  return tile;
}

function selectQuality(quality, audioOnly) {
  state.selectedQuality = { quality, audio_only: audioOnly };
  document.querySelectorAll('.quality-tile').forEach(t => {
    t.classList.toggle('selected',
      t.dataset.quality === quality && t.dataset.audio_only === String(audioOnly)
    );
  });
  show('downloadBtn');
  $('downloadBtnText').textContent = audioOnly
    ? `Download Audio (${quality})`
    : `Download ${quality}`;
}

function onAudioOnlyChange() {
  const audioOnly = $('audioOnlyToggle').checked;
  $('audioFormatRow').classList.toggle('hidden', !audioOnly);
  if (state.videoInfo) renderQualityGrid(state.videoInfo);
}

// ── Start Download ─────────────────────────────────────────────

async function startDownload() {
  if (!state.videoInfo || !state.selectedQuality) return;

  const { quality, audio_only } = state.selectedQuality;
  const af = document.querySelector('input[name="af"]:checked')?.value || 'm4a';

  hide('qualitySection');
  hide('videoSection');
  show('progressSection');
  $('progressTitle').textContent = state.videoInfo.title;
  $('progressStep').textContent  = 'Starting...';
  setProgress(0);

  try {
    const res  = await fetch('/api/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url:          $('urlInput').value.trim(),
        quality,
        audio_only,
        audio_format: af,
      }),
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    state.activeJobId = data.job_id;
    listenProgress(data.job_id);
  } catch (err) {
    showDownloadError(err.message);
  }
}

// ── SSE Progress ───────────────────────────────────────────────

function listenProgress(jobId) {
  if (state.progressSource) state.progressSource.close();

  const es = new EventSource(`/api/progress/${jobId}`);
  state.progressSource = es;

  es.onmessage = e => {
    const ev = JSON.parse(e.data);

    if (ev.type === 'progress') {
      setProgress(ev.progress);
      $('progressStep').textContent = stepLabel(ev.step);

      const dl    = formatBytes(ev.downloaded);
      const total = ev.total > 0 ? formatBytes(ev.total) : '?';
      const spd   = formatBytes(ev.speed) + '/s';
      $('progressDl').textContent    = `${dl} / ${total}`;
      $('progressSpeed').textContent = spd;

      if (ev.total > 0 && ev.speed > 0) {
        const eta = Math.round((ev.total - ev.downloaded) / ev.speed);
        $('progressEta').textContent = `ETA ${formatTime(eta)}`;
      }
    }

    if (ev.type === 'done') {
      es.close();
      setProgress(100);
      setTimeout(() => showDone(ev.output_file), 300);
      refreshHistory();
    }

    if (ev.type === 'error') {
      es.close();
      showDownloadError(ev.message);
    }
  };

  es.onerror = () => {
    es.close();
    // Check job status manually
    setTimeout(() => pollJobStatus(jobId), 1000);
  };
}

async function pollJobStatus(jobId) {
  try {
    const res  = await fetch('/api/jobs');
    const data = await res.json();
    const job  = data.jobs.find(j => j.job_id === jobId);
    if (!job) return;
    if (job.status === 'done') {
      setProgress(100);
      showDone(job.output_file);
      refreshHistory();
    } else if (job.status === 'error') {
      showDownloadError(job.error);
    }
  } catch (_) {}
}

// ── UI State Transitions ──────────────────────────────────────

function setProgress(pct) {
  $('progressBar').style.width    = pct + '%';
  $('progressPct').textContent    = Math.round(pct) + '%';
}

function showDone(filename) {
  hide('progressSection');
  show('doneSection');
  $('doneFilename').textContent = filename;
  $('doneDownloadLink').href    = `/downloads/${encodeURIComponent(filename)}`;
}

function showDownloadError(msg) {
  hide('progressSection');
  hide('qualitySection');
  show('errorSection');
  $('errorMsg').textContent = msg;
}

function resetUI() {
  $('urlInput').value        = '';
  state.videoInfo            = null;
  state.selectedQuality      = null;
  state.activeJobId          = null;
  $('audioOnlyToggle').checked = false;
  $('audioFormatRow').classList.add('hidden');
  hide('videoSection');
  hide('qualitySection');
  hide('progressSection');
  hide('doneSection');
  hide('errorSection');
}

function resetToQuality() {
  hide('errorSection');
  if (state.videoInfo) {
    show('videoSection');
    show('qualitySection');
  }
}

// ── History ────────────────────────────────────────────────────

async function refreshHistory() {
  try {
    const res  = await fetch('/api/jobs');
    const data = await res.json();
    renderHistory(data.jobs);
  } catch (_) {}
}

function loadHistory() {
  refreshHistory();
  // Refresh every 3s while page open
  setInterval(refreshHistory, 3000);
}

function renderHistory(jobs) {
  const list = $('historyList');
  if (!jobs || jobs.length === 0) {
    $('historySection').classList.add('hidden');
    return;
  }
  $('historySection').classList.remove('hidden');

  list.innerHTML = jobs.slice(0, 20).map(j => {
    const isDone    = j.status === 'done';
    const isRunning = j.status === 'running' || j.status === 'pending';
    const isError   = j.status === 'error';

    const dlLink = isDone && j.output_file
      ? `<a class="hi-dl-link" href="/downloads/${encodeURIComponent(j.output_file)}" title="Save to disk">⬇</a>`
      : isRunning
        ? `<span style="font-size:12px;color:var(--text-dim)">${Math.round(j.progress)}%</span>`
        : '';

    // Playlist batch label
    const plLabel = j.playlist_total > 0
      ? `<span style="font-size:10px;color:var(--purple);font-weight:600">[${j.playlist_index}/${j.playlist_total}]</span> `
      : '';

    return `
      <div class="history-item">
        <span class="hi-status ${j.status}"></span>
        <span class="hi-title" title="${escHtml(j.title)}">${plLabel}${escHtml(j.title)}</span>
        <span class="hi-quality">${j.quality}${j.audio_only ? ' 🎵' : ''}</span>
        ${dlLink}
      </div>
    `;
  }).join('');
}

// ── Helpers ────────────────────────────────────────────────────

function show(id) { $(id).classList.remove('hidden'); }
function hide(id) { $(id).classList.add('hidden'); }

function formatBytes(bytes) {
  if (!bytes || bytes <= 0) return '0 B';
  const units = ['B','KB','MB','GB'];
  let i = 0;
  while (bytes >= 1024 && i < units.length - 1) { bytes /= 1024; i++; }
  return bytes.toFixed(1) + ' ' + units[i];
}

function formatTime(sec) {
  sec = Math.max(0, Math.round(sec));
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function stepLabel(raw) {
  if (!raw) return 'Downloading...';
  const map = { 'Video': '⬇ Downloading video...', 'Audio': '⬇ Downloading audio...' };
  return map[raw] || raw;
}

const QUALITY_ORDER = ['4320p','2160p','1440p','1080p','720p','480p','360p','240p','144p'];
function qualityOrder(q) {
  const i = QUALITY_ORDER.indexOf(q);
  return i === -1 ? 99 : i;
}

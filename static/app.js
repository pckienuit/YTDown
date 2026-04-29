/* ─── YTDown App — Frontend Logic ───────────────────────────── */

'use strict';

// ── State ─────────────────────────────────────────────────────

const state = {
  videoInfo:         null,
  selectedQuality:   null,
  selectedStreamUrl: null,

  // Playlist
  playlistInfo:      null,   // { playlist_id, title, entries, … }
  selectedVideoIds:  new Set(),
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

function checkStatus() {
  // Client-side only on Vercel, no FFmpeg available for merging.
  const badge  = $('ffmpegBadge');
  const notice = $('ffmpegNotice');
  badge.textContent  = 'Client-side Download Mode';
  badge.className    = 'badge badge-green';
  notice.classList.add('hidden');
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
      let res, data;
      try {
        res = await fetch('/api/playlist-info-edge', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url }),
        });
        data = await res.json();
      } catch (e) {
        res = await fetch('/api/playlist-info', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url }),
        });
        data = await res.json();
      }
      if (data.error) throw new Error(data.error);
      state.playlistInfo = data;
      renderPlaylist(data);
      show('playlistSection');
    } else {
      // Try Edge Function first (serverless-friendly), fallback to Flask
      let res, data;
      try {
        res = await fetch('/api/video-info', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url }),
        });
        data = await res.json();
      } catch (e) {
        // Edge function not available (local dev), fall back to Flask
        res = await fetch('/api/info', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url }),
        });
        data = await res.json();
      }
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

  const audio_only  = $('plAudioToggle').checked;
  // For playlists, we have to fetch info for each video to get the download URL.
  // We will do this sequentially to avoid rate limits.
  
  hide('playlistSection');
  show('progressSection');
  $('progressTitle').textContent = state.playlistInfo?.title || 'Playlist';
  $('progressStep').textContent  = `Processing ${state.selectedVideoIds.size} videos...`;
  setProgress(0);

  const videoIds = [...state.selectedVideoIds];
  
  for (let i = 0; i < videoIds.length; i++) {
    const vid = videoIds[i];
    $('progressStep').textContent  = `Fetching video ${i + 1}/${videoIds.length}...`;
    setProgress((i / videoIds.length) * 100);
    
    try {
      const res = await fetch('/api/info', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: `https://youtube.com/watch?v=${vid}` }),
      });
      const data = await res.json();
      if (!data.error && data.streams && data.streams.length > 0) {
        let stream;
        if (audio_only) {
          stream = data.streams.find(s => s.stream_type === 'audio') || data.streams[0];
        } else {
          // Muxed stream (video + audio) since we can't merge client-side
          stream = data.streams.find(s => s.stream_type === 'muxed') || data.streams.find(s => s.stream_type === 'audio');
        }
        
        if (stream) {
          triggerBrowserDownload(stream.url, `${data.title}.${stream.ext}`);
          saveJobToHistory({
            job_id: Math.random().toString(36).substring(7),
            title: data.title,
            quality: stream.quality,
            audio_only: audio_only,
            status: 'done',
            output_file: `${data.title}.${stream.ext}`
          });
        }
      }
    } catch (e) {
      console.error(`Failed to download video ${vid}:`, e);
    }
    
    // Slight delay between videos
    await new Promise(r => setTimeout(r, 1000));
  }

  setProgress(100);
  $('progressStep').textContent  = `Finished queuing downloads!`;
  setTimeout(() => showDone('Batch Download Complete'), 1500);
  refreshHistory();
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
    <span class="count-pill">${sc.muxed || 0} muxed streams</span>
    <span class="count-pill">${sc.audio || 0} audio streams</span>
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
        url:        s.url
      }));
    });

    if (audioStreams.length > 0) {
      const best = audioStreams[0];
      selectQuality(best.quality, true, best.url, best.ext);
    }
  } else {
    // Muxed streams only (we cannot merge video+audio on client safely)
    const videoStreams = info.streams.filter(s => s.stream_type === 'muxed');
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
        url:        s.url
      }));
    });

    if (sorted.length > 0) selectQuality(sorted[0].quality, false, sorted[0].url, sorted[0].ext);
  }

  $('noStreams').classList.toggle('hidden', grid.children.length > 0);
}

function makeQualityTile({ quality, ext, filesize, audio_only, isAudio, url }) {
  const tile = document.createElement('div');
  tile.className = `quality-tile${isAudio ? ' audio-tile' : ''}`;
  tile.dataset.quality    = quality;
  tile.dataset.audio_only = audio_only;
  tile.onclick = () => selectQuality(quality, audio_only, url, ext);

  const size = filesize ? formatBytes(filesize) : '';
  tile.innerHTML = `
    <span class="qt-label">${quality}</span>
    <span class="qt-sub">${ext}${size ? ' · ~' + size : ''}</span>
  `;
  return tile;
}

function selectQuality(quality, audioOnly, url, ext) {
  state.selectedQuality = { quality, audio_only: audioOnly, ext };
  state.selectedStreamUrl = url;
  
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

function triggerBrowserDownload(streamUrl, filename) {
  const proxyUrl = `/api/proxy?url=${encodeURIComponent(streamUrl)}&title=${encodeURIComponent(filename)}`;
  
  // Create an invisible anchor element and trigger download
  const a = document.createElement('a');
  a.style.display = 'none';
  a.href = proxyUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  
  // Cleanup
  setTimeout(() => {
    document.body.removeChild(a);
  }, 1000);
}

async function startDownload() {
  if (!state.videoInfo || !state.selectedQuality || !state.selectedStreamUrl) return;

  const { quality, audio_only, ext } = state.selectedQuality;
  const title = state.videoInfo.title;
  const filename = `${sanitizeFilename(title)}.${ext}`;

  hide('qualitySection');
  hide('videoSection');
  show('progressSection');
  $('progressTitle').textContent = title;
  $('progressStep').textContent  = 'Starting download via browser...';
  setProgress(50);

  try {
    triggerBrowserDownload(state.selectedStreamUrl, filename);
    
    // Save to local storage history
    saveJobToHistory({
      job_id: Math.random().toString(36).substring(7),
      title: title,
      quality: quality,
      audio_only: audio_only,
      status: 'done',
      output_file: filename,
      timestamp: Date.now()
    });

    setProgress(100);
    $('progressStep').textContent  = 'Download sent to browser!';
    setTimeout(() => showDone(filename), 1000);
    refreshHistory();
  } catch (err) {
    showDownloadError(err.message);
  }
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
  // For client downloads, we don't have a server-hosted file to link back to,
  // the browser already downloaded it. Just display the name.
  $('doneDownloadLink').href = '#';
  $('doneDownloadLink').onclick = (e) => { e.preventDefault(); alert('File was downloaded via your browser!'); };
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
  state.selectedStreamUrl    = null;
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

function getHistory() {
  try {
    const raw = localStorage.getItem('ytdown_history');
    return raw ? JSON.parse(raw) : [];
  } catch (e) {
    return [];
  }
}

function saveJobToHistory(job) {
  const jobs = getHistory();
  jobs.unshift(job);
  // Keep only last 20
  if (jobs.length > 20) jobs.pop();
  localStorage.setItem('ytdown_history', JSON.stringify(jobs));
}

function refreshHistory() {
  const jobs = getHistory();
  renderHistory(jobs);
}

function loadHistory() {
  refreshHistory();
}

function renderHistory(jobs) {
  const list = $('historyList');
  if (!jobs || jobs.length === 0) {
    $('historySection').classList.add('hidden');
    return;
  }
  $('historySection').classList.remove('hidden');

  list.innerHTML = jobs.slice(0, 20).map(j => {
    // All client-initiated jobs are considered 'done' from app perspective since browser manages them
    return `
      <div class="history-item">
        <span class="hi-status done"></span>
        <span class="hi-title" title="${escHtml(j.title)}">${escHtml(j.title)}</span>
        <span class="hi-quality">${j.quality}${j.audio_only ? ' 🎵' : ''}</span>
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

function sanitizeFilename(name) {
  return name.replace(/[<>:"/\\|?*]+/g, '_');
}

const QUALITY_ORDER = ['4320p','2160p','1440p','1080p','720p','480p','360p','240p','144p'];
function qualityOrder(q) {
  const i = QUALITY_ORDER.indexOf(q);
  return i === -1 ? 99 : i;
}

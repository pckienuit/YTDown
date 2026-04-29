export const config = {
  runtime: 'nodejs',
};

const INNERTUBE_KEY = 'AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8';
const INNERTUBE_URL = 'https://www.youtube.com/youtubei/v1/player';

function formatDuration(seconds) {
  seconds = Math.max(0, Math.round(seconds));
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

function extractPlaylistId(url) {
  const patterns = [
    /[?&]list=([A-Za-z0-9_-]+)/,
    /youtube\.com\/playlist\?.*list=([A-Za-z0-9_-]+)/,
  ];
  for (const pattern of patterns) {
    const m = url.match(pattern);
    if (m) return m[1];
  }
  return null;
}

async function getVisitorData() {
  try {
    const response = await fetch('https://www.youtube.com/', {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
      },
    });

    if (!response.ok) return null;

    const html = await response.text();
    const patterns = [
      /"VISITOR_DATA"\s*:\s*"([^"]{10,})"/,
      /"visitorData"\s*:\s*"([^"]{10,})"/,
    ];

    for (const pattern of patterns) {
      const m = html.match(pattern);
      if (m) return m[1];
    }
  } catch (e) {
    // Failed
  }
  return null;
}

async function fetchPlaylistInfo(playlistId, visitorData = null) {
  const payload = {
    playlistId,
    context: {
      client: {
        clientName: 'WEB',
        clientVersion: '2.20240726.00.00',
      },
    },
  };

  if (visitorData) {
    payload.context.client.visitorData = visitorData;
  }

  const headers = {
    'Content-Type': 'application/json',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': '*/*',
    'Accept-Language': 'en-US,en;q=0.9',
  };

  if (visitorData) {
    headers['X-Goog-Visitor-Id'] = visitorData;
  }

  try {
    const response = await fetch(`${INNERTUBE_URL}?key=${INNERTUBE_KEY}&prettyPrint=false`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    });

    if (!response.ok) return null;

    const data = await response.json();

    const details = data.playlist?.playlist?.listBuilder || data.playlist || {};
    const playlistDetails = data.playlist?.playlist || details;

    if (!playlistDetails || !playlistDetails.title) return null;

    const thumbnails = playlistDetails.thumbnail?.thumbnails || [];
    const thumbnail = thumbnails[thumbnails.length - 1]?.url || '';

    const entries = [];
    let index = 0;

    const rawEntries = playlistDetails.tracks || playlistDetails.videos || [];
    for (const entry of rawEntries) {
      const video = entry.playlistVideo || entry;
      if (!video.videoId) continue;

      const entryThumbnails = video.thumbnail?.thumbnails || [];
      const entryThumbnail = entryThumbnails[entryThumbnails.length - 1]?.url || '';

      entries.push({
        video_id: video.videoId,
        title: video.title?.runs?.[0]?.text || video.title || 'Unknown',
        duration: video.lengthSeconds ? parseInt(video.lengthSeconds, 10) : 0,
        duration_str: video.lengthSeconds ? formatDuration(parseInt(video.lengthSeconds, 10)) : '0:00',
        thumbnail: entryThumbnail,
        channel: video.shortBylineText?.runs?.[0]?.text || '',
        index: index++,
      });
    }

    return {
      playlist_id: playlistId,
      title: playlistDetails.title || 'Unknown Playlist',
      channel: playlistDetails.shortBylineText?.runs?.[0]?.text || '',
      video_count: entries.length,
      thumbnail,
      url: `https://www.youtube.com/playlist?list=${playlistId}`,
      entries,
    };
  } catch (e) {
    return null;
  }
}

export default async function handler(req) {
  try {
    let body = {};
    try {
      body = await req.json();
    } catch (e) {
      return new Response(JSON.stringify({ error: 'Invalid JSON body' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    const url = (body.url || '').trim();
    if (!url) {
      return new Response(JSON.stringify({ error: "Missing 'url' field" }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    const playlistId = extractPlaylistId(url);
    if (!playlistId) {
      return new Response(JSON.stringify({ error: 'Invalid playlist URL' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    let visitorData = null;
    try {
      visitorData = await getVisitorData();
    } catch (e) {
      // Continue without visitorData
    }

    if (!visitorData && body.visitor_data) {
      visitorData = body.visitor_data;
    }

    const info = await fetchPlaylistInfo(playlistId, visitorData);

    if (!info) {
      return new Response(JSON.stringify({
        error: 'Could not fetch playlist info. The playlist may be private, region-locked, or unavailable.',
      }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    return new Response(JSON.stringify(info), {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
      },
    });
  } catch (err) {
    return new Response(JSON.stringify({ error: err.message || 'Internal error' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}

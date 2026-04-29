export const config = {
  runtime: 'nodejs18.x',
};

const INNERTUBE_KEY = 'AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8';
const INNERTUBE_URL = 'https://www.youtube.com/youtubei/v1/player';

const ITAG_MAP = {
  18:  { quality: '360p',  type: 'muxed',  ext: 'mp4' },
  22:  { quality: '720p',  type: 'muxed',  ext: 'mp4' },
  37:  { quality: '1080p', type: 'muxed',  ext: 'mp4' },
  43:  { quality: '360p',  type: 'muxed',  ext: 'webm' },
  44:  { quality: '480p',  type: 'muxed',  ext: 'webm' },
  45:  { quality: '720p',  type: 'muxed',  ext: 'webm' },
  137: { quality: '1080p', type: 'video',  ext: 'mp4' },
  248: { quality: '1080p', type: 'video',  ext: 'webm' },
  136: { quality: '720p',  type: 'video',  ext: 'mp4' },
  247: { quality: '720p',  type: 'video',  ext: 'webm' },
  135: { quality: '480p',  type: 'video',  ext: 'mp4' },
  244: { quality: '480p',  type: 'video',  ext: 'webm' },
  134: { quality: '360p',  type: 'video',  ext: 'mp4' },
  243: { quality: '360p',  type: 'video',  ext: 'webm' },
  133: { quality: '240p',  type: 'video',  ext: 'mp4' },
  242: { quality: '240p',  type: 'video',  ext: 'webm' },
  160: { quality: '144p',  type: 'video',  ext: 'mp4' },
  278: { quality: '144p',  type: 'video',  ext: 'webm' },
  271: { quality: '1440p', type: 'video',  ext: 'webm' },
  264: { quality: '1440p', type: 'video',  ext: 'mp4' },
  272: { quality: '4320p', type: 'video',  ext: 'webm' },
  313: { quality: '2160p', type: 'video',  ext: 'webm' },
  140: { quality: '128kbps', type: 'audio', ext: 'm4a' },
  141: { quality: '256kbps', type: 'audio', ext: 'm4a' },
  251: { quality: '160kbps', type: 'audio', ext: 'webm' },
  250: { quality: '70kbps',  type: 'audio', ext: 'webm' },
  249: { quality: '50kbps',  type: 'audio', ext: 'webm' },
  139: { quality: '48kbps',  type: 'audio', ext: 'm4a' },
};

const QUALITY_ORDER = ['4320p', '2160p', '1440p', '1080p', '720p', '480p', '360p', '240p', '144p', '256kbps', '160kbps', '128kbps', '70kbps', '50kbps', '48kbps'];

function qualitySortKey(quality) {
  const i = QUALITY_ORDER.indexOf(quality);
  return i === -1 ? 999 : i;
}

function formatDuration(seconds) {
  seconds = Math.max(0, Math.round(seconds));
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

function parseStreams(streamingData) {
  const rawFormats = [
    ...(streamingData.formats || []),
    ...(streamingData.adaptiveFormats || []),
  ];

  const streams = [];
  for (const fmt of rawFormats) {
    const url = fmt.url;
    if (!url) continue;

    const itag = parseInt(fmt.itag, 10);
    const mimeType = fmt.mimeType || '';
    const vcodec = fmt.vcodec || 'none';
    const acodec = fmt.acodec || 'none';

    let streamType = 'muxed';
    if (vcodec !== 'none' && acodec !== 'none') streamType = 'muxed';
    else if (vcodec !== 'none') streamType = 'video';
    else streamType = 'audio';

    const extMatch = mimeType.match(/(?:video|audio)\/(\w+)/);
    const ext = extMatch ? extMatch[1] : (ITAG_MAP[itag]?.ext || 'mp4');

    let streamQuality = fmt.qualityLabel || fmt.quality || ITAG_MAP[itag]?.quality || 'unknown';

    streams.push({
      itag,
      url,
      mime_type: mimeType,
      quality: streamQuality,
      stream_type: streamType,
      codec: (vcodec !== 'none' ? vcodec : acodec).split('.')[0],
      bitrate: parseInt(fmt.bitrate, 10) || 0,
      filesize: fmt.contentLength ? parseInt(fmt.contentLength, 10) : null,
      width: fmt.width ? parseInt(fmt.width, 10) : null,
      height: fmt.height ? parseInt(fmt.height, 10) : null,
      fps: fmt.fps ? parseInt(fmt.fps, 10) : null,
      ext,
      label: streamType === 'audio'
        ? `Audio ${streamQuality} [${ext}]`
        : `${streamQuality}${fmt.fps && fmt.fps > 30 ? ` ${fmt.fps}fps` : ''} [${streamType}] [${ext}]`,
    });
  }

  streams.sort((a, b) => {
    const typeOrder = { muxed: 0, video: 1, audio: 2 };
    const ta = typeOrder[a.stream_type] ?? 3;
    const tb = typeOrder[b.stream_type] ?? 3;
    if (ta !== tb) return ta - tb;
    return qualitySortKey(a.quality) - qualitySortKey(b.quality);
  });

  return streams;
}

const CLIENTS = [
  {
    name: 'ANDROID',
    payload: (videoId, visitorData) => ({
      videoId,
      context: {
        client: {
          clientName: 'ANDROID',
          clientVersion: '19.30.36',
          androidSdkVersion: 34,
          visitorData,
        },
      },
    }),
  },
  {
    name: 'IOS',
    payload: (videoId, visitorData) => ({
      videoId,
      context: {
        client: {
          clientName: 'IOS',
          clientVersion: '19.29.1',
          deviceMake: 'Apple',
          deviceModel: 'iPhone16,2',
          visitorData,
        },
      },
    }),
  },
  {
    name: 'WEB',
    payload: (videoId) => ({
      videoId,
      context: {
        client: {
          clientName: 'WEB',
          clientVersion: '2.20240726.00.00',
        },
      },
    }),
  },
  {
    name: 'ANDROID_VR',
    payload: (videoId, visitorData) => ({
      videoId,
      context: {
        client: {
          clientName: 'ANDROID_VR',
          clientVersion: '1.50.34',
          visitorData,
        },
      },
    }),
  },
];

async function fetchVideoInfo(videoId, visitorData = null) {
  for (const client of CLIENTS) {
    try {
      const payload = client.payload(videoId, visitorData);

      const headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9',
      };

      if (visitorData) {
        headers['X-Goog-Visitor-Id'] = visitorData;
      }

      const url = `${INNERTUBE_URL}?key=${INNERTUBE_KEY}&prettyPrint=false`;
      const response = await fetch(url, {
        method: 'POST',
        headers,
        body: JSON.stringify(payload),
      });

      if (response.status === 429) {
        continue;
      }

      if (response.status !== 200) {
        continue;
      }

      const data = await response.json();
      const status = data.playabilityStatus || {};

      if (status.status !== 'OK') {
        const msg = status.reason || (status.messages || [])[0] || status.status;
        continue;
      }

      const details = data.videoDetails || {};
      const streamingData = data.streamingData || {};

      const thumbnails = details.thumbnail?.thumbnails || [];
      const thumbnail = thumbnails[thumbnails.length - 1]?.url || '';

      const streams = parseStreams(streamingData);

      return {
        video_id: videoId,
        title: details.title || 'Unknown Title',
        channel: details.author || 'Unknown Channel',
        duration: parseInt(details.lengthSeconds, 10) || 0,
        duration_str: formatDuration(parseInt(details.lengthSeconds, 10) || 0),
        thumbnail,
        url: `https://www.youtube.com/watch?v=${videoId}`,
        streams,
        stream_counts: {
          muxed: streams.filter(s => s.stream_type === 'muxed').length,
          audio: streams.filter(s => s.stream_type === 'audio').length,
          total: streams.length,
        },
      };
    } catch (e) {
      // Try next client
    }
  }

  return null;
}

async function getVisitorData() {
  try {
    const response = await fetch('https://www.youtube.com/', {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
      },
    });

    if (!response.ok) return null;

    const html = await response.text();

    const patterns = [
      /"VISITOR_DATA"\s*:\s*"([^"]{10,})"/,
      /"visitorData"\s*:\s*"([^"]{10,})"/,
      /ytcfg\.set\s*\(\s*"VISITOR_DATA"\s*,\s*"([^"]{10,})"/,
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

function extractVideoId(url) {
  const patterns = [
    /(?:youtube\.com/watch\?(?:.*&)?v=|youtu\.be\/|youtube\.com\/embed\/)([A-Za-z0-9_-]{11})/,
    /^([A-Za-z0-9_-]{11})$/,
  ];
  for (const pattern of patterns) {
    const m = url.match(pattern);
    if (m) return m[1];
  }
  return null;
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

    const videoId = extractVideoId(url);
    if (!videoId) {
      return new Response(JSON.stringify({ error: 'Invalid YouTube URL' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // Try to get visitorData from YouTube homepage
    let visitorData = null;
    try {
      visitorData = await getVisitorData();
    } catch (e) {
      // Continue without visitorData
    }

    // Try to use visitorData from request body (extracted client-side)
    if (!visitorData && body.visitor_data) {
      visitorData = body.visitor_data;
    }

    const info = await fetchVideoInfo(videoId, visitorData);

    if (!info) {
      return new Response(JSON.stringify({
        error: 'Could not fetch video info. The video may be private, region-locked, or requires authentication.',
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

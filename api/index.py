import os
import sys
from flask import Flask, request, jsonify, send_from_directory

# Ensure core module can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.extractor import get_video_info
from core.client_extractor import get_video_info_from_client_data, parse_player_response
from core.playlist import get_playlist_info, is_playlist_url

app = Flask(__name__)

@app.route('/api/info', methods=['POST'])
def api_info():
    try:
        body = request.get_json() or {}
        url = body.get("url", "").strip()
        if not url:
            return jsonify({"error": "Missing 'url' field"}), 400

        info = get_video_info(url)

        streams = []
        # We only return muxed and audio streams because serverless can't merge video+audio easily
        for s in info.muxed_streams() + info.audio_streams():
            streams.append({
                "itag":        s.itag,
                "quality":     s.quality,
                "stream_type": s.stream_type,
                "codec":       s.codec,
                "ext":         s.ext,
                "mime_type":   s.mime_type,
                "bitrate":     s.bitrate,
                "filesize":    s.filesize,
                "width":       s.width,
                "height":      s.height,
                "fps":         s.fps,
                "url":         s.url,  # Explicitly returning url to frontend for direct download
                "label":       s.label(),
            })

        return jsonify({
            "video_id":        info.video_id,
            "title":           info.title,
            "channel":         info.channel,
            "duration":        info.duration_seconds,
            "duration_str":    info.duration_str,
            "thumbnail":       info.thumbnail,
            "url":             info.url,
            "streams":         streams,
            "stream_counts": {
                "muxed":  len(info.muxed_streams()),
                "audio":  len(info.audio_streams()),
                "total":  len(streams),
            },
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/api/info-client', methods=['POST'])
def api_info_client():
    """
    Alternative endpoint: receives pre-fetched video data from client-side extraction.
    This bypasses serverless outbound HTTP restrictions.
    
    Expected body:
    {
        "url": "https://youtube.com/watch?v=...",
        "player_response": { ... },  # Full player response from YouTube
        "extracted_data": {           # Simplified extracted data
            "video_id": "...",
            "title": "...",
            "channel": "...",
            "duration": 123,
            "thumbnail": "...",
            "streamingData": {
                "formats": [...],
                "adaptiveFormats": [...]
            }
        }
    }
    """
    try:
        body = request.get_json() or {}
        url = body.get("url", "").strip()
        player_response = body.get("player_response", {})
        extracted_data = body.get("extracted_data", {})

        # Use player_response if available, otherwise use extracted_data
        if player_response:
            video_id_match = __import__('re').search(r'[?&]v=([A-Za-z0-9_-]{11})', url)
            video_id = video_id_match.group(1) if video_id_match else extracted_data.get("video_id", "")
            info = parse_player_response(player_response, video_id)
        elif extracted_data:
            info = get_video_info_from_client_data(extracted_data)
        else:
            return jsonify({"error": "Missing 'player_response' or 'extracted_data'"}), 400

        streams = []
        for s in info.muxed_streams() + info.audio_streams():
            streams.append({
                "itag":        s.itag,
                "quality":     s.quality,
                "stream_type": s.stream_type,
                "codec":       s.codec,
                "ext":         s.ext,
                "mime_type":   s.mime_type,
                "bitrate":     s.bitrate,
                "filesize":    s.filesize,
                "width":       s.width,
                "height":      s.height,
                "fps":         s.fps,
                "url":         s.url,
                "label":       s.label(),
            })

        return jsonify({
            "video_id":        info.video_id,
            "title":           info.title,
            "channel":         info.channel,
            "duration":        info.duration_seconds,
            "duration_str":    info.duration_str,
            "thumbnail":       info.thumbnail,
            "url":             info.url,
            "streams":         streams,
            "stream_counts": {
                "muxed":  len(info.muxed_streams()),
                "audio":  len(info.audio_streams()),
                "total":  len(streams),
            },
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/playlist-info', methods=['POST'])
def api_playlist_info():
    try:
        body = request.get_json() or {}
        url = body.get("url", "").strip()
        if not url:
            return jsonify({"error": "Missing 'url' field"}), 400
        if not is_playlist_url(url):
            return jsonify({"error": "URL does not contain a playlist ID"}), 400

        playlist = get_playlist_info(url)
        entries = [
            {
                "video_id":  e.video_id,
                "title":     e.title,
                "duration":  e.duration,
                "thumbnail": e.thumbnail,
                "channel":   e.channel,
                "index":     e.index,
            }
            for e in playlist.entries
        ]
        return jsonify({
            "playlist_id": playlist.playlist_id,
            "title":       playlist.title,
            "channel":     playlist.channel,
            "video_count": playlist.video_count,
            "thumbnail":   playlist.thumbnail,
            "url":         playlist.url,
            "entries":     entries,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# Optional fallback for static files if testing locally via this script
@app.route('/', defaults={'path': 'index.html'})
@app.route('/<path:path>')
def serve_static(path):
    static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static')
    if not os.path.exists(os.path.join(static_dir, path)):
        return "Not Found", 404
    return send_from_directory(static_dir, path)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)

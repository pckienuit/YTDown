import os
import core.utils
from core.extractor import _innertube_player, _parse_streams
os.environ.pop("YOUTUBE_COOKIES", None)
core.utils.HEADERS.pop("Cookie", None)

try:
    resp = _innertube_player('CPkGTSW34_I', 'ANDROID_VR')
    streams = _parse_streams(resp)
    if streams:
        print("URL:")
        print(streams[0].url)
        if "ipbits=0" in streams[0].url:
            print("IPBITS IS 0! IP LOCKING IS DISABLED!")
        else:
            print("IPBITS IS NOT 0! IP IS LOCKED!")
except Exception as e:
    print(f"ERROR: {e}")

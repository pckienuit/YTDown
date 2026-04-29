import os
import importlib
import core.utils
from core.extractor import _innertube_player, _check_playability

os.environ.pop("YOUTUBE_COOKIES", None)
core.utils.HEADERS.pop("Cookie", None)

try:
    resp = _innertube_player('CPkGTSW34_I', 'WEB')
    ok, err = _check_playability(resp)
    print(f"WEB Without Cookie: OK={ok} ERR={err}")
except Exception as e:
    print(f"WEB Without Cookie: ERROR={e}")

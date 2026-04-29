import os
import json
import urllib.request
import urllib.error

import importlib
import core.utils
from core.extractor import _innertube_player, _check_playability, _CLIENT_ORDER

def patched_get_visitor_data():
    return ""

import core.extractor
core.extractor._get_visitor_data = patched_get_visitor_data

for client in ["IOS", "ANDROID"]:
    try:
        resp = _innertube_player('CPkGTSW34_I', client)
        print(f"Client {client}: OK")
        #print(resp)
    except Exception as e:
        print(f"Client {client}: ERROR: {e}")

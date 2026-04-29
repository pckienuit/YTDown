import os
import json
import urllib.request
import urllib.error

# Mock the environment variable
os.environ["YOUTUBE_COOKIES"] = "SID=g.a0008wiFmIYG8K5tWSfccO11akXDCTgDjIuK2Iaz7e0ih71dXi9fGGUGOgATIiX6OTuza1moJQACgYKAUkSARMSFQHGX2MibEWeddCD7XqVm7cYVWTTXhoVAUF8yKop0JFX8mepsbcgC9kIIj7-0076; __Secure-1PSID=g.a0008wiFmIYG8K5tWSfccO11akXDCTgDjIuK2Iaz7e0ih71dXi9flGaVKyNB1VW33FOSTqrlpAACgYKAXASARMSFQHGX2MixjHaSELjWF2v0-YVBxulqxoVAUF8yKqTEl1db128HMF25mQ5rzW20076; __Secure-3PSID=g.a0008wiFmIYG8K5tWSfccO11akXDCTgDjIuK2Iaz7e0ih71dXi9fXBmP_fu0YpBIV8niK9idPgACgYKAU0SARMSFQHGX2Mij1jfiBBm_I7NErYjHixSBBoVAUF8yKqZ_mRkZ-KqRcdFdkC9llre0076; HSID=AYnXn8QmFvi5Jc1lE; SSID=A_zglhpXaA_BH_2gy; APISID=A9_AitXutz2r4Cfv/AV-rFOluiAr6tayMC; SAPISID=wh4wHS8cYndOxZ_M/AelgUJHyownJs6wy4; __Secure-1PAPISID=wh4wHS8cYndOxZ_M/AelgUJHyownJs6wy4; __Secure-3PAPISID=wh4wHS8cYndOxZ_M/AelgUJHyownJs6wy4; __Secure-BUCKET=CKoF; LOGIN_INFO=AFmmF2swRQIgI0dHEqGg5xTJbCbOsl1vV4KdbU8bsA-6ChY8uv8xUSECIQDg2dZvPM71kriX5SQvmIn1lExnGePRf6-v8CbsSwfwFQ:QUQ3MjNmek9acDFRRldYWFE2clQ5d21BSnhObURzN3hWSlQ4dnBpVU5JaXlLUUFGQmJoaVFLYmtDRHBDVFVSQlc0V2s3Q2E1eGJzRHIyOWRVdHNRX1cwVU5ob3E0djNnaWxET1Z3OFh0MVdMNHRXdGxLOVNBc00xTHR1RDh4am5JYjlhalFjSFBnN2JyNUY0TkdxRzBld0xPeXRmNEdPWjlR; PREF=f6=40000080&tz=Asia.Saigon&f7=100&repeat=NONE; __Secure-1PSIDTS=sidts-CjQBhkeRd7wZaYlUJBvvXKH4-OhoZ1DkAoNKtaMAqc4_6vVnXJqP51KQRkSqIlEwGIRZVUEYEAA; __Secure-3PSIDTS=sidts-CjQBhkeRd7wZaYlUJBvvXKH4-OhoZ1DkAoNKtaMAqc4_6vVnXJqP51KQRkSqIlEwGIRZVUEYEAA; SIDCC=AKEyXzWtN1oTuWJRsek2UilgKwz-hsvJlFWvH7Uw4M3meg1hZUYJdwJ3hVmc-scFI4G1ehVIjw; __Secure-1PSIDCC=AKEyXzXaQBmbXASR6Fi2_2qUQ2A0kRQXaxlYNCmWIFD6BONNqkLCMrshE5UuVfbzkWRvlq3Asw; __Secure-3PSIDCC=AKEyXzWzw0mMfhN_qLRddiHDp6GMqngkjZS5SFIj5qlg30Kg-FejRBxl_1zgxWKfOKYS00qX_UA"

# Reload HEADERS from core.utils after setting the env var
import importlib
import core.utils
importlib.reload(core.utils)
from core.extractor import _innertube_player, _check_playability, _CLIENT_ORDER

video_id = 'CPkGTSW34_I'

for client in _CLIENT_ORDER:
    try:
        resp = _innertube_player(video_id, client)
        ok, err = _check_playability(resp)
        print(f"Client {client}: Playable: {ok}, Err: {err}")
    except Exception as e:
        print(f"Client {client}: ERROR: {e}")

"""Download GloVe vectors next to server.py (works around Windows SSL issues)."""
import os
import ssl
import sys
import urllib.request

import certifi

NAME = sys.argv[1] if len(sys.argv) > 1 else "glove-wiki-gigaword-100"
URL = f"https://github.com/piskvorky/gensim-data/releases/download/{NAME}/{NAME}.gz"
DEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), NAME + ".gz")

ctx = ssl.create_default_context(cafile=certifi.where())
print(f"Downloading {URL}")
with urllib.request.urlopen(URL, context=ctx) as r, open(DEST, "wb") as f:
    while chunk := r.read(1 << 20):
        f.write(chunk)
print(f"Saved {DEST}")

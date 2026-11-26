# Hidden Word (LAN)

## Setup
```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```
1. Create `words.csv` next to `server.py` (one word per row, optional `word` header, no proper nouns).
   The server refuses to start if it is missing or empty.
2. First run downloads the sentence model (~90 MB). Fetch the GloVe vectors (~130 MB) with
   `python download_vectors.py` (also fixes the Windows "CERTIFICATE_VERIFY_FAILED" error); the server
   refuses to start without them unless `REQUIRE_ASSOC_MODEL = False`.

## Run
```bash
python server.py
```
The terminal prints `http://<lan-ip>:8000`; everyone on the same Wi-Fi opens that in a browser.
The first player to join is the host and starts the game. Reconnecting after a refresh resumes your seat.

## Tune similarity
```bash
python test_similarity.py     # raw + calibrated scores for benchmark pairs
```
Adjust `EMBEDDING_ALPHA` and `CALIBRATION_ANCHORS` (or `CALIBRATION_MODE = "sigmoid"`) in `config.py`.

## Tests
```bash
pytest          # no model downloads needed; uses a fake scorer
```

"""Print raw and calibrated scores for benchmark pairs.  Usage: python test_similarity.py"""
import config as cfg
from embeddings import SimilarityScorer

PAIRS = [
    ("death", "taxes", "related"), ("sun", "burn", "related"), ("key", "lock", "related"),
    ("animal", "mouse", "related"), ("warm", "hot", "intensity"),
    ("cold", "freezing", "intensity"), ("hard", "tough", "synonym"),
    ("banana", "tractor", "control"), ("piano", "cement", "control"),
    ("ocean", "spreadsheet", "control"), ("dragon", "fork", "control"),
]

if __name__ == "__main__":
    sc = SimilarityScorer([])
    print(f"alpha={cfg.EMBEDDING_ALPHA}  mode={cfg.CALIBRATION_MODE}  "
          f"threshold={cfg.SIMILARITY_THRESHOLD}\n")
    print(f"{'pair':<24}{'kind':<11}{'sem':>7}{'assoc':>8}{'raw':>8}{'score':>8}  hit")
    for a, b, kind in PAIRS:
        r = sc.score(a, b)
        hit = "YES" if r["score"] >= cfg.SIMILARITY_THRESHOLD else "-"
        print(f"{a + '/' + b:<24}{kind:<11}{r['sem']:>7.3f}{r['assoc']:>8.3f}"
              f"{r['raw']:>8.3f}{r['score']:>8.3f}  {hit}")
    print("\nTune CALIBRATION_ANCHORS / EMBEDDING_ALPHA in config.py: related pairs "
          "should be YES, controls should stay well below.")

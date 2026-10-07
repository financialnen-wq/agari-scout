"""검증: 타석 코드로 다시 센 타수·안타가 박스스코어 합계(게임원 집계)와 맞는지."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify import split_cell, classify  # noqa: E402

P = json.loads((Path(__file__).resolve().parent.parent / "data/raw/players.json").read_text())
n = ok_ab = ok_h = 0
bad = []
for p in P:
    for g in p["games"]:
        for b in g["bat"][:1]:
            ab = h = 0
            for _, cell in b["pa"]:
                for tok in split_cell(cell):
                    c = classify(tok)
                    if not c:
                        continue
                    if c["res"] in ("1B", "2B", "3B", "HR"):
                        h += 1
                    if c["res"] not in ("BB", "IBB", "HBP", "SF", "SH", "CI"):
                        ab += 1
            n += 1
            ok_ab += str(ab) == b["ab"]
            ok_h += str(h) == b["h"]
            if str(ab) != b["ab"] or str(h) != b["h"]:
                bad.append((p["name"], g["date"], b["ab"], ab, b["h"], h, [c for _, c in b["pa"]]))
print(f"경기 {n} · 타수 일치 {ok_ab / n:.1%} · 안타 일치 {ok_h / n:.1%}")
for x in bad[:25]:
    print(x)

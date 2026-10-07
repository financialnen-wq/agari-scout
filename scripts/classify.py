"""게임원 타석 결과 코드 → 표준 이벤트.

게임원 박스스코어의 이닝 칸 예: "중플", "유내안,도루", "좌월2", "4구/삼진"(타자일순)
- "/" 는 같은 이닝의 다른 타석, "," 는 같은 타석 뒤의 주루 이벤트(도루 등)
- 수비 위치: 투 포 1 2 3 유 좌 중 우 (+ 좌중·우중 = 외야 사이)
- 대괄호 [..] 는 부가정보(타점·시각·송구 경로) → 제거하되 실책 번호(E6)는 위치로 사용
"""
import re

POS = {"투": "P", "포": "C", "1": "1B", "2": "2B", "3": "3B", "유": "SS",
       "좌": "LF", "중": "CF", "우": "RF", "좌중": "LC", "우중": "RC"}
ENUM = {"1": "P", "2": "C", "3": "1B", "4": "2B", "5": "3B", "6": "SS", "7": "LF", "8": "CF", "9": "RF"}
INFIELD = {"P", "C", "1B", "2B", "3B", "SS"}
# 타구 방향(포수 시점 좌·중·우)
SIDE = {"3B": "L", "SS": "L", "LF": "L", "LC": "L",
        "P": "C", "C": "C", "CF": "C",
        "2B": "R", "1B": "R", "RF": "R", "RC": "R"}

NON_PA = ("도루", "도루자", "주자아웃", "폭투", "포일", "보크", "견제사", "대타", "대주자", "대수비",
          "런다운", "리터치", "아웃", "포구실책[도루", "실책[")
BATTED = re.compile(r"^(인)?(좌중|우중|투|포|유|좌|중|우|1|2|3)(선|월|전|G)?(.*)$")


def split_cell(cell):
    """이닝 칸 → [타석 결과 문자열]"""
    out = []
    for chunk in cell.split("/"):
        for tok in chunk.split(","):
            tok = tok.strip()
            if tok and not tok.startswith(NON_PA):
                out.append(tok)
                break  # 한 덩어리의 첫 결과만 타석, 나머지는 주루
    return out


def classify(raw):
    """→ dict(res, bb, pos) 또는 None(타석 아님)
    res: 1B 2B 3B HR OUT ROE FC SF SH K BB IBB HBP CI
    bb : GB(땅볼) FB(뜬공) LD(라이너) BU(번트) None(타구 아님/불명)
    """
    s = raw.strip()
    err = re.search(r"E(\d)", s)
    s = re.sub(r"\[.*?\]", "", s).strip()
    if not s:
        return None
    if s.startswith(("삼진", "낫아웃", "쓰리번트", "부정타격")):
        return {"res": "K", "bb": None, "pos": None}
    if s == "고의4구":
        return {"res": "IBB", "bb": None, "pos": None}
    if s == "4구":
        return {"res": "BB", "bb": None, "pos": None}
    if s == "사구":
        return {"res": "HBP", "bb": None, "pos": None}
    if s == "타격방해":
        return {"res": "CI", "bb": None, "pos": None}
    if s == "1루타":
        return {"res": "1B", "bb": None, "pos": None}
    if s.startswith(("송구실책", "포구실책", "실책")):
        pos = ENUM.get(err.group(1)) if err else None
        return {"res": "ROE", "bb": ("GB" if pos in INFIELD else "FB") if pos else None, "pos": pos}
    m = BATTED.match(s)
    if not m:
        return None
    inside, p, mod, suf = m.groups()
    pos = POS[p]
    inf = pos in INFIELD
    # 결과
    if suf in ("2", "3", "홈") or (mod == "G" and suf == "홈"):
        res = {"2": "2B", "3": "3B", "홈": "HR"}[suf]
        bb = "LD" if mod == "선" else ("FB" if mod == "월" or suf == "홈" else None)
        return {"res": res, "bb": bb, "pos": pos}
    if suf.startswith("내안"):
        return {"res": "1B", "bb": "GB", "pos": pos}
    if suf.startswith("번안"):
        return {"res": "1B", "bb": "BU", "pos": pos}
    if suf.startswith("안"):
        # 내야수 쪽 안타는 땅볼, 외야 안타는 궤적 불명(선상=라이너, 월=뜬공)
        bb = "GB" if inf else ("LD" if mod == "선" else ("FB" if mod == "월" else None))
        return {"res": "1B", "bb": bb, "pos": pos}
    if suf.startswith("희번") or suf.startswith("번"):
        return {"res": "SH", "bb": "BU", "pos": pos}
    if suf.startswith("희플"):
        return {"res": "SF", "bb": "FB", "pos": pos}
    if suf.startswith("야선"):
        return {"res": "FC", "bb": "GB", "pos": pos}
    if suf.startswith("땅"):
        return {"res": "ROE" if suf.endswith("실") else "OUT", "bb": "GB", "pos": pos}
    if suf.startswith(("플", "파플", "인플")):
        return {"res": "ROE" if suf.endswith("실") else "OUT", "bb": "FB", "pos": pos}
    if suf.startswith("직"):
        return {"res": "OUT", "bb": "LD", "pos": pos}
    if suf.startswith("실"):
        return {"res": "ROE", "bb": "GB" if inf else "FB", "pos": pos}
    return None


if __name__ == "__main__":
    import json, sys
    from collections import Counter
    from pathlib import Path
    db = json.loads((Path(__file__).resolve().parent.parent / "data/raw/gameone_games.json").read_text())
    miss, ok = Counter(), Counter()
    for g in db.values():
        for b in g["bat"]:
            for _, cell in b["pa"]:
                for tok in split_cell(cell):
                    c = classify(tok)
                    (ok if c else miss)[tok if not c else c["res"]] += 1
    print("분류됨", sum(ok.values()), dict(ok.most_common()))
    print("미분류", sum(miss.values()), miss.most_common(40))

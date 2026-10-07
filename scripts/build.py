"""수집 원자료 → 선수별 집계 + 대시보드 데이터(docs/data.js) + CSV(data/*.csv).

사용: python3 scripts/build.py
집계 범위: 시즌(전체·2025·2026) × 경기(전체 경기·S리그만)
"""
import csv, json, re, sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify import split_cell, classify, SIDE, INFIELD  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
SLEAGUE_WORDS = ("시민리그", "S-리그", "S리그")
ZONES = ["P", "C", "1B", "2B", "3B", "SS", "LF", "LC", "CF", "RC", "RF"]
SEASONS = ["전체", "2025", "2026"]
SCOPES = ["all", "team", "sl"]  # 전체 경기 / 이 팀 소속 경기만 / S리그만
TEAM_NAMES = {"AGARI": {"아가리 OB", "아가리OB 2"}, "디펜스원": {"디펜스원"}}


def is_sl(league):
    return any(w in (league or "") for w in SLEAGUE_WORDS)


def num(x):
    try:
        return int(str(x).strip())
    except ValueError:
        return 0


def outs_of(ip):
    """'2 ⅔' → 8 아웃"""
    ip = (ip or "").strip()
    frac = 1 if "⅓" in ip else 2 if "⅔" in ip else 0
    whole = re.sub(r"[⅓⅔]", "", ip).strip()
    return num(whole) * 3 + frac if whole else frac


def ip_str(outs):
    return f"{outs // 3}" + ("" if outs % 3 == 0 else f" {outs % 3}/3")


def pull_side(hand):
    """타자 손: '우투좌타' → 좌타 → 당겨치기 = 우측"""
    if hand.endswith("좌타"):
        return "R"
    if hand.endswith("우타"):
        return "L"
    return None  # 양타·미등록


def hit_agg(games, hand):
    a = {k: 0 for k in ["G", "PA", "AB", "H", "1B", "2B", "3B", "HR", "BB", "HBP", "K", "SF", "SH",
                        "ROE", "FC", "R", "RBI", "SB", "GB", "FB", "LD", "BU", "BIPunk", "GO", "AO"]}
    zone = {z: 0 for z in ZONES}
    zone_hit = {z: 0 for z in ZONES}
    side = {"L": 0, "C": 0, "R": 0}
    for g in games:
        a["G"] += 1
        a["R"] += g["r"]; a["RBI"] += g["rbi"]; a["SB"] += g["sb"]
        for e in g["pa"]:
            res, bb, pos = e["res"], e["bb"], e["pos"]
            a["PA"] += 1
            if res in ("BB", "IBB"):
                a["BB"] += 1
            elif res == "HBP":
                a["HBP"] += 1
            elif res == "K":
                a["K"] += 1; a["AB"] += 1
            elif res == "SF":
                a["SF"] += 1
            elif res == "SH":
                a["SH"] += 1
            elif res == "CI":
                pass
            else:
                a["AB"] += 1
                if res in ("1B", "2B", "3B", "HR"):
                    a["H"] += 1; a[res] += 1
                elif res in ("ROE", "FC"):
                    a[res] += 1
            if bb:
                a[bb] += 1
            elif pos or res in ("1B", "2B", "3B", "HR", "OUT", "ROE", "FC"):
                a["BIPunk"] += 1
            if res in ("OUT", "FC") and bb == "GB":
                a["GO"] += 1
            if res in ("OUT", "SF") and bb in ("FB", "LD"):
                a["AO"] += 1
            if pos:
                zone[pos] += 1
                side[SIDE[pos]] += 1
                if res in ("1B", "2B", "3B", "HR"):
                    zone_hit[pos] += 1
    ab, pa = a["AB"], a["PA"]
    tb = a["1B"] + 2 * a["2B"] + 3 * a["3B"] + 4 * a["HR"]
    obp_d = ab + a["BB"] + a["HBP"] + a["SF"]
    known = a["GB"] + a["FB"] + a["LD"]
    dirn = sum(side.values())
    ps = pull_side(hand)
    r = lambda x, d, n=3: round(x / d, n) if d else None  # noqa: E731
    a.update({
        "AVG": r(a["H"], ab), "OBP": r(a["H"] + a["BB"] + a["HBP"], obp_d), "SLG": r(tb, ab),
        "TB": tb, "K%": r(a["K"], pa), "BB%": r(a["BB"], pa),
        "GB%": r(a["GB"], known), "FB%": r(a["FB"], known), "LD%": r(a["LD"], known),
        "GO/AO": r(a["GO"], a["AO"], 2),
        "zone": zone, "zone_hit": zone_hit, "side": side, "dir_n": dirn,
        "IF%": r(sum(zone[z] for z in INFIELD), dirn),
        "pull%": r(side[ps], dirn) if ps else None,
        "oppo%": r(side["R" if ps == "L" else "L"], dirn) if ps else None,
        "cent%": r(side["C"], dirn),
    })
    a["OPS"] = round(a["OBP"] + a["SLG"], 3) if a["OBP"] is not None and a["SLG"] is not None else None
    return a


def pit_agg(games):
    a = {k: 0 for k in ["G", "W", "L", "S", "HLD", "outs", "BF", "AB", "H", "HR", "BB", "HBP", "K",
                        "WP", "BK", "R", "ER", "NP", "SH", "SF"]}
    for g in games:
        p = g["line"]
        a["G"] += 1
        res = p.get("결과", "")
        a["W"] += res == "승"; a["L"] += res == "패"; a["S"] += res == "세"; a["HLD"] += res == "홀"
        a["outs"] += outs_of(p.get("이닝"))
        for k, col in [("BF", "타자"), ("AB", "타수"), ("H", "피안타"), ("HR", "피홈런"), ("BB", "볼넷"),
                       ("HBP", "사구"), ("K", "삼진"), ("WP", "폭투"), ("BK", "보크"), ("R", "실점"),
                       ("ER", "자책점"), ("NP", "투구수"), ("SH", "희타"), ("SF", "희비")]:
            a[k] += num(p.get(col))
    o = a["outs"]
    r = lambda x, d, n=2: round(x / d, n) if d else None  # noqa: E731
    a.update({"IP": ip_str(o),
              "ERA": r(a["ER"] * 21, o),           # 7이닝 기준(게임원·S리그 방식)
              "WHIP": r((a["BB"] + a["H"]) * 3, o),
              "K7": r(a["K"] * 21, o, 1), "BB7": r(a["BB"] * 21, o, 1),
              "K%": r(a["K"], a["BF"], 3), "BB%": r(a["BB"] + a["HBP"], a["BF"], 3),
              "K/BB": r(a["K"], a["BB"]), "OAVG": r(a["H"], a["AB"], 3),
              "IP/G": r(o / 3, a["G"], 1), "NP/G": r(a["NP"], a["G"], 0)})
    return a


def main():
    players = json.loads((RAW / "players.json").read_text())
    sl = json.loads((RAW / "sleague_2026.json").read_text())
    sl_hit = {(r["team"], r["name"]): r for r in sl["hitters"]}
    sl_pit = {(r["team"], r["name"]): r for r in sl["pitchers"]}
    out = []
    for p in players:
        hand = p.get("hand", "")
        bat_games, pit_games = [], []
        for g in p["games"]:
            base = {"gid": g["game_idx"], "date": g.get("date", ""), "season": str(g["season"]),
                    "league": g.get("league", ""), "opp": g.get("opp", ""), "sl": is_sl(g.get("league")),
                    "url": "https://www.gameone.kr" + g["url"]}
            mine = TEAM_NAMES[p["team"]]
            base["own"] = any(r.get("team") in mine for r in g["bat"][:1] + g["pit"][:1])
            for b in g["bat"][:1]:
                pas = []
                for inn, cell in b["pa"]:
                    for tok in split_cell(cell):
                        c = classify(tok)
                        if c:
                            pas.append({**c, "inn": inn, "raw": tok})
                bat_games.append({**base, "pa": pas, "r": num(b.get("r")), "rbi": num(b.get("rbi")),
                                  "sb": num(b.get("sb")), "fpos": b.get("pos", ""), "order": b.get("order", ""),
                                  "team": b.get("team", "")})
            for pl in g["pit"][:1]:
                pit_games.append({**base, "line": pl, "team": pl.get("team", "")})
        hit, pit = {}, {}
        for s in SEASONS:
            for sc in SCOPES:
                f = lambda g: (s == "전체" or g["season"] == s) and (  # noqa: E731
                    sc == "all" or (sc == "sl" and g["sl"]) or (sc == "team" and g["own"]))
                hit[f"{s}|{sc}"] = hit_agg([g for g in bat_games if f(g)], hand)
                pit[f"{s}|{sc}"] = pit_agg([g for g in pit_games if f(g)])
        out.append({
            "id": p.get("group_code") or p["name"], "team": p["team"], "name": p["name"],
            "no": p.get("no", ""), "pos": p.get("pos", ""), "hand": hand, "sources": p["sources"],
            "locker": f"https://www.gameone.kr/locker/record/main?group_code={p['group_code']}" if p.get("group_code") else "",
            "sl26_hit": sl_hit.get((p["team"], p["name"])), "sl26_pit": sl_pit.get((p["team"], p["name"])),
            "hit": hit, "pit": pit,
            "bat_games": sorted(bat_games, key=lambda g: g["date"], reverse=True),
            "pit_games": sorted(pit_games, key=lambda g: g["date"], reverse=True),
        })
    meta = {"built": datetime.now().strftime("%Y-%m-%d %H:%M"), "seasons": SEASONS}
    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "data.js").write_text("window.SCOUT = " + json.dumps({"meta": meta, "players": out}, ensure_ascii=False) + ";\n")
    write_csv(out)
    print("선수", len(out), "→ docs/data.js, data/hitters.csv, data/pitchers.csv")


def write_csv(out):
    hcols = ["G", "PA", "AB", "H", "2B", "3B", "HR", "R", "RBI", "SB", "BB", "HBP", "K", "SF", "SH",
             "AVG", "OBP", "SLG", "OPS", "K%", "BB%", "GB", "FB", "LD", "GB%", "FB%", "LD%", "GO/AO",
             "pull%", "cent%", "oppo%", "IF%"] + [f"zone_{z}" for z in ZONES]
    pcols = ["G", "W", "L", "S", "IP", "BF", "H", "HR", "BB", "HBP", "K", "WP", "R", "ER", "NP",
             "ERA", "WHIP", "K7", "BB7", "K%", "BB%", "K/BB", "OAVG"]
    data = ROOT / "data"
    with open(data / "hitters.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["팀", "선수", "번호", "투타", "시즌", "범위"] + hcols)
        for p in out:
            for key, a in p["hit"].items():
                if a["PA"]:
                    s, sc = key.split("|")
                    w.writerow([p["team"], p["name"], p["no"], p["hand"], s, {"sl": "S리그", "team": "소속팀경기", "all": "전체경기"}[sc]]
                               + [a["zone"][c[5:]] if c.startswith("zone_") else a.get(c) for c in hcols])
    with open(data / "pitchers.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["팀", "선수", "번호", "투타", "시즌", "범위"] + pcols)
        for p in out:
            for key, a in p["pit"].items():
                if a["G"]:
                    s, sc = key.split("|")
                    w.writerow([p["team"], p["name"], p["no"], p["hand"], s, {"sl": "S리그", "team": "소속팀경기", "all": "전체경기"}[sc]]
                               + [a.get(c) for c in pcols])


if __name__ == "__main__":
    main()

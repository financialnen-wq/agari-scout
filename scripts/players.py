"""선수 단위 수집: S리그 출전 선수 → 게임원 라커룸의 '게임별기록'(소속 팀 전부) → 박스스코어 타석·투수 기록.

사용: python3 scripts/players.py
입력: data/raw/sleague_2026.json(S리그 기록실), data/raw/gameone_games.json(팀 일정 박스스코어)
산출: data/raw/players.json  (선수 메타 + 경기별 타석/투수 줄)
      data/raw/box_cache/<game_idx>.json (박스스코어 캐시, 재실행 시 재사용)
"""
import json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gameone import get, clean, parse_box, CLUBS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
CACHE = RAW / "box_cache"
SEASONS = [2025, 2026]
SLEAGUE_WORDS = ("시민리그", "S-리그", "S리그")


def roster(club):
    out, page = [], 1
    while True:
        t = get(f"/club/info/player?club_idx={club}&page={page}")
        body = t.split('class="player_list"', 1)[-1].split("</ul>\n</div>", 1)[0]
        new = 0
        for li in body.split("<li>")[1:]:
            gc = re.search(r'name="group_code" value="([0-9A-Z]+)"', li)
            info = re.search(r'<dl class="info">(.*?)</dl>', li, re.S)
            if not (gc and info):
                continue
            dt = re.search(r"<dt>(\d*)\.(.*?)</dt>", info.group(1))
            dd = re.search(r"</dt>\s*<dd>(.*?)</dd>", info.group(1), re.S)
            pos, _, hand = clean(dd.group(1)).partition("|") if dd else ("", "", "")
            if any(p["group_code"] == gc.group(1) for p in out):
                continue
            out.append({"name": clean(dt.group(2)), "no": dt.group(1), "pos": pos.strip(),
                        "hand": hand.strip(), "group_code": gc.group(1), "club": club})
            new += 1
        if not new or f"page={page + 1}" not in t:
            return out
        page += 1


def locker_links(gc, season):
    """선수의 시즌 내 모든 소속 팀 경기 → {game_idx: url}"""
    first = get(f"/locker/record/game?group_code={gc}&season={season}")
    clubs = re.findall(r'<select name="club_idx">(.*?)</select>', first, re.S)
    clubs = re.findall(r'<option value="(\d+)"', clubs[0]) if clubs else []
    links = {}
    for i, club in enumerate(clubs):
        t = first if i == 0 else get(f"/locker/record/game?group_code={gc}&season={season}&club_idx={club}&section=0")
        ligs = {v: clean(n) for v, n in re.findall(r'<option value="(\d+)"[^>]*>(.*?)</option>', t, re.S)}
        for li in re.findall(r"<li><dl>(.*?)</dl></li>", t, re.S):
            m = re.search(r'href="(/(?:league|club)/[^"]*game_idx=(\d+)[^"]*)"', li)
            if not m:
                continue
            url = html_unescape(m.group(1)).replace("/league/schedule/all", "/league/schedule/content/boxscore")
            md = re.search(r"<strong>(\d+)\.(\d+)</strong>", li)
            lig = re.search(r"lig_idx=(\d+)", url)
            opp = re.search(r'class="team">(.*?)</span>', li, re.S)
            links.setdefault(int(m.group(2)), {
                "url": url, "club": int(club),
                "date": f"{season}-{md.group(1)}-{md.group(2)}" if md else "",
                "league": ligs.get(lig.group(1), "") if lig else "",
                "opp": clean(opp.group(1)) if opp else ""})
    return links


def html_unescape(s):
    return s.replace("&amp;", "&")


def box(game_idx, url):
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{game_idx}.json"
    if f.exists():
        return json.loads(f.read_text())
    t = get(url)
    bat, pit = parse_box(t)
    d = {"game_idx": game_idx, "url": url, "bat": bat, "pit": pit}
    f.write_text(json.dumps(d, ensure_ascii=False))
    return d


def targets():
    """S리그 출전 확인 선수: S리그 기록실 + 게임원 S리그 박스스코어"""
    s = json.loads((RAW / "sleague_2026.json").read_text())
    want = {}
    for kind in ("hitters", "pitchers"):
        for r in s[kind]:
            want.setdefault((r["team"], r["name"]), set()).add("S리그 기록실 2026")
    games = json.loads((RAW / "gameone_games.json").read_text())
    for g in games.values():
        if not any(w in g["league"] for w in SLEAGUE_WORDS):
            continue
        label = CLUBS[g["club"]]
        mine = {"디펜스원"} if label == "디펜스원" else {"아가리 OB", "아가리OB 2"}
        for row in g["bat"] + g["pit"]:
            if row["team"] in mine:
                want.setdefault((label, row["name"]), set()).add(f"게임원 S리그 {g['date']}")
    return want


def main():
    rosters = {}
    for club, label in CLUBS.items():
        for p in roster(club):
            rosters.setdefault((label, p["name"]), p)  # 아가리 OB 우선(먼저 등록)
    want = targets()
    print("S리그 출전 선수", len(want))
    players = []
    for (label, name), src in sorted(want.items()):
        meta = rosters.get((label, name))
        if not meta:
            print("  ! 게임원 명단에 없음:", label, name)
            players.append({"team": label, "name": name, "sources": sorted(src), "games": []})
            continue
        gc = meta["group_code"]
        links = {}
        for season in SEASONS:
            for k, v in locker_links(gc, season).items():
                links.setdefault(k, {**v, "season": season})
        rows = []
        for gi, v in sorted(links.items()):
            b = box(gi, v["url"])
            me_bat = [r for r in b["bat"] if r.get("group_code") == gc]
            me_pit = [r for r in b["pit"] if r.get("group_code") == gc]
            if not (me_bat or me_pit):  # 클럽 박스스코어는 코드가 없을 수 있어 이름+번호로 보조 매칭
                me_bat = [r for r in b["bat"] if r["name"] == name]
                me_pit = [r for r in b["pit"] if r["name"] == name]
            rows.append({"game_idx": gi, "season": v["season"], "club": v["club"], "date": v["date"],
                         "league": v["league"], "opp": v["opp"],
                         "bat": me_bat, "pit": me_pit, "url": v["url"]})
        players.append({"team": label, "name": name, "no": meta["no"], "pos": meta["pos"],
                        "hand": meta["hand"], "group_code": gc, "sources": sorted(src), "games": rows})
        print(f"  {label} {name}: 경기 {len(rows)}")
        (RAW / "players.json").write_text(json.dumps(players, ensure_ascii=False))
    fill_missing(players)
    (RAW / "players.json").write_text(json.dumps(players, ensure_ascii=False))


def fill_missing(players):
    """게임원 현재 명단에 없는 선수(이적·휴면): 우리 두 팀 박스스코어에서 이름으로 찾는다."""
    games = json.loads((RAW / "gameone_games.json").read_text())
    for p in players:
        if p.get("group_code") or p["games"]:
            continue
        mine = {"디펜스원"} if p["team"] == "디펜스원" else {"아가리 OB", "아가리OB 2"}
        for g in games.values():
            if g["season"] not in SEASONS:
                continue
            bat = [r for r in g["bat"] if r["team"] in mine and r["name"] == p["name"]]
            pit = [r for r in g["pit"] if r["team"] in mine and r["name"] == p["name"]]
            if bat or pit:
                opp = [t for t in g["teams"] if t not in mine]
                p["games"].append({"game_idx": g["game_idx"], "season": g["season"], "club": g["club"],
                                   "date": g["date"], "league": g["league"], "opp": opp[0] if opp else "",
                                   "bat": bat, "pit": pit,
                                   "url": f"/club/info/schedule/boxscore?club_idx={g['club']}&game_idx={g['game_idx']}"})
        p["no"] = next((r["no"] for g in p["games"] for r in g["bat"] + g["pit"]), "")
        print("  보완(팀 박스스코어):", p["team"], p["name"], len(p["games"]), "경기")


if __name__ == "__main__":
    main()

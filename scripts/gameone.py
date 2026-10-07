"""게임원(gameone.kr) 팀 일정 → 박스스코어를 돌며 타석별 결과·투수 기록을 수집한다.

사용: python3 scripts/gameone.py            # config의 팀·시즌 전부
산출: data/raw/gameone_games.json (경기별 원자료, 재실행 시 이미 받은 경기는 건너뜀)
"""
import json, re, html, time, random, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "gameone_games.json"
BASE = "https://www.gameone.kr"

# 우리 팀 AGARI = 게임원 '아가리 OB'·'아가리OB 2'(같은 선수단), 상대 디펜스원 = 31183
CLUBS = {
    19129: "AGARI",   # 아가리 OB
    43281: "AGARI",   # 아가리OB 2
    31183: "디펜스원",
}
SEASONS = [2024, 2025, 2026]


def get(path):
    time.sleep(0.4 + random.random() * 0.4)  # 서버 부담 최소화
    # 게임원 서버 DH 키가 작아 파이썬 ssl이 거부 → curl 사용
    out = subprocess.run(["curl", "-sL", "--max-time", "30", "-A", "Mozilla/5.0", BASE + path],
                         capture_output=True, check=True)
    return out.stdout.decode("utf-8", "ignore")


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def schedule(club, season):
    """시즌 일정표 전 페이지 → [{game_idx,date,league,park,teams,scores}]"""
    games, page = [], 1
    while True:
        t = get(f"/club/info/schedule/table?season={season}&club_idx={club}&game_type=0"
                f"&lig_idx=0&group=0&month=0&page={page}")
        body = t.split('class="game_table"', 1)[-1].split("</table>", 1)[0]
        rows = re.findall(r"<tr>(.*?)</tr>", body, re.S)[1:]
        new = 0
        for r in rows:
            m = re.search(r"boxscore\?club_idx=\d+&(?:amp;)?game_idx=(\d+)", r)
            if not m:
                continue  # 게임대기(기록 없음)
            tds = re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)
            md = re.search(r"(\d+)월(\d+)일", tds[0])
            names = [clean(x) for x in re.findall(r'class="team_name">(.*?)</span>', r, re.S)]
            scores = [clean(x) for x in re.findall(r'class="score">(.*?)</span>', r, re.S)]
            g = {"game_idx": int(m.group(1)), "club": club, "season": season,
                 "date": f"{season}-{int(md.group(1)):02d}-{int(md.group(2)):02d}" if md else "",
                 "league": clean(tds[1]), "park": clean(tds[2]), "teams": names, "scores": scores}
            if all(x["game_idx"] != g["game_idx"] for x in games):
                games.append(g)
                new += 1
        if new == 0 or f"page={page + 1}" not in t:
            break
        page += 1
    return games


def split_team_tables(t, summary):
    """박스스코어에서 '<h3>팀명</h3><table summary=...>' 쌍을 뽑는다."""
    out = []
    for m in re.finditer(r'<h3[^>]*>((?:(?!<h3).)*?)</h3>\s*<table[^>]*summary="' + summary + r'">(.*?)</table>', t, re.S):
        out.append((clean(m.group(1)), m.group(2)))
    return out


def parse_box(t):
    bat, pit = [], []
    for team, tb in split_team_tables(t, "타자기록"):
        body = tb.split("<tbody>", 1)[-1].split("</tbody>", 1)[0]
        for tr in re.findall(r"<tr>(.*?)</tr>", body, re.S):
            th = re.search(r"<th>(.*?)</th>", tr, re.S)
            if not th:
                continue
            name = re.search(r'class="name">(?:<a[^>]*>)?<strong>(.*?)</strong>(?:</a>)?\((\d*)\)', th.group(1))
            if not name:
                continue
            gc = re.search(r"group_code=([0-9A-Z]+)", th.group(1))
            order = clean((re.search(r'class="num">(.*?)</span>', th.group(1)) or [None, ""])[1]) if 'class="num"' in th.group(1) else ""
            pos = clean(re.search(r'class="position">(.*?)</span>', th.group(1)).group(1)) if 'class="position"' in th.group(1) else ""
            rounds = [clean(x) for x in re.findall(r'<td class="round[^"]*">(.*?)</td>', tr, re.S)]
            nums = [clean(x) for x in re.findall(r"<td>(.*?)</td>", tr, re.S)]
            # 이닝 칸 원문 보존("4구,도루" / "좌안/삼진") — 해석은 classify.split_cell
            pas = [[inn, cell] for inn, cell in enumerate(rounds, 1) if cell]
            bat.append({"team": team, "name": name.group(1).strip(), "no": name.group(2),
                        "group_code": gc.group(1) if gc else "",
                        "order": order, "pos": pos, "pa": pas,
                        "ab": nums[0] if nums else "", "h": nums[1] if len(nums) > 1 else "",
                        "rbi": nums[2] if len(nums) > 2 else "", "r": nums[3] if len(nums) > 3 else "",
                        "sb": nums[4] if len(nums) > 4 else ""})
    cols = ["결과", "이닝", "타자", "타수", "피안타", "피홈런", "희타", "희비", "볼넷", "사구",
            "삼진", "폭투", "보크", "실점", "자책점", "투구수"]
    for team, tb in split_team_tables(t, "투수기록"):
        body = tb.split("<tbody>", 1)[-1].split("</tbody>", 1)[0]
        for tr in re.findall(r"<tr>(.*?)</tr>", body, re.S):
            name = re.search(r"<strong>(.*?)</strong>(?:</a>)?\((\d*)\)", tr)
            if not name:
                continue
            gc = re.search(r"group_code=([0-9A-Z]+)", tr)
            tds = [clean(x) for x in re.findall(r"<td>(.*?)</td>", tr, re.S)]
            rec = {"team": team, "name": name.group(1).strip(), "no": name.group(2),
                   "group_code": gc.group(1) if gc else ""}
            rec.update(dict(zip(cols, tds)))
            pit.append(rec)
    return bat, pit


def main():
    db = json.loads(RAW.read_text()) if RAW.exists() else {}
    for club, label in CLUBS.items():
        for season in SEASONS:
            sched = schedule(club, season)
            print(f"[{label} {club}] {season}: 기록 있는 경기 {len(sched)}")
            for g in sched:
                key = str(g["game_idx"])
                if key in db and db[key].get("bat") is not None:
                    db[key]["clubs"] = sorted(set(db[key].get("clubs", []) + [club]))
                    continue
                t = get(f"/club/info/schedule/boxscore?club_idx={club}&game_idx={g['game_idx']}")
                bat, pit = parse_box(t)
                g.update({"bat": bat, "pit": pit, "clubs": [club]})
                db[key] = g
            RAW.parent.mkdir(parents=True, exist_ok=True)
            RAW.write_text(json.dumps(db, ensure_ascii=False))
    print("총 경기", len(db))


if __name__ == "__main__":
    main()

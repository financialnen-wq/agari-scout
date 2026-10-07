"""S리그(서울시민리그) 2026 야구 기록실에서 지정 팀 선수의 타자·투수 기록을 수집한다."""
import json, re, html, sys, urllib.request
from pathlib import Path

BASE = "https://www.sleague.or.kr/2026/baseball/result/"
TEAMS = {"AGARI": 1473, "디펜스원": 1410}
OUT = Path(__file__).resolve().parent.parent / "data"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def parse(page):
    t = get(BASE + page)
    # 좌측 고정 영역: 선수별 <ul class="team-match-result-tbl-tbody player">
    people = []
    for ul in re.findall(r'<ul class="team-match-result-tbl-tbody player">(.*?)</ul>', t, re.S):
        name = clean(re.search(r'class="td name">(.*?)</li>', ul, re.S).group(1))
        idx = re.search(r"team_popup_view\.php\?idx=(\d+)", ul)
        team = clean(re.search(r"<strong>(.*?)</strong>", ul, re.S).group(1))
        league = clean(re.search(r'class="td league">(.*?)</li>', ul, re.S).group(1))
        people.append({"name": name, "team": team, "team_idx": int(idx.group(1)) if idx else None, "league": league})
    # 우측 스크롤 영역: 앞의 두 표(열 반반)를 이어 붙인다
    tabs = re.findall(r"<table.*?</table>", t, re.S)[:2]
    cols, rows = [], None
    for tb in tabs:
        cols += [clean(x) for x in re.findall(r"<th[^>]*>(.*?)</th>", tb, re.S)]
        body = [[clean(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
                for tr in re.findall(r"<tr>(.*?)</tr>", tb.split("<tbody>")[1], re.S)]
        rows = body if rows is None else [a + b for a, b in zip(rows, body)]
    # 투수표는 두 표 모두에 '피홈런'이 있어 중복 열 제거
    out = []
    for p, r in zip(people, rows):
        rec = dict(p)
        for c, v in zip(cols, r):
            rec.setdefault(c, v)
        out.append(rec)
    return out


def main():
    idxs = set(TEAMS.values())
    res = {}
    for kind, page in [("hitters", "player_attack_ranking.php"), ("pitchers", "player_ranking.php")]:
        # 전체 순위는 100명 상한이라 조별 필터(일요리그 2·3조)로도 받아 합친다
        seen = {}
        for q in ["", "?yoil=2&jo=2", "?yoil=2&jo=3"]:
            for r in parse(page + q):
                if r["team_idx"] in idxs:
                    seen.setdefault((r["team"], r["name"]), r)
        res[kind] = list(seen.values())
        print(kind, "두 팀", len(res[kind]))
    (OUT / "raw").mkdir(parents=True, exist_ok=True)
    (OUT / "raw" / "sleague_2026.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    for k, v in res.items():
        for r in v:
            print(k, r["team"], r["name"], r.get("타율") or r.get("방어율"), r.get("타석") or r.get("이닝"))


if __name__ == "__main__":
    main()

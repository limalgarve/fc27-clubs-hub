
from __future__ import annotations
import io, json, math, sqlite3, time, os, hmac
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Header
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from fc27_api import FC27API, FC27APIError

BASE = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB = DATA_DIR / "fc27.db"
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()
MATCH_TYPES = {
    "leagueMatch": "Liga",
    "friendlyMatch": "Amistoso",
    "playoffMatch": "Playoff",
}
api = FC27API(timezone="America/Sao_Paulo", timeout=20)

app = FastAPI(title="FC27 Clubs Hub")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")

def clean(v):
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, pd.Timestamp):
        if v.tzinfo is not None:
            v = v.tz_convert("America/Sao_Paulo").tz_localize(None)
        return v.isoformat(sep=" ", timespec="seconds")
    if hasattr(v, "item"):
        try: return v.item()
        except Exception: pass
    return v

def records(df):
    if df is None or getattr(df, "empty", True):
        return []
    return [{k: clean(v) for k, v in row.items()} for row in df.to_dict("records")]

@contextmanager
def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    try:
        yield c
        c.commit()
    finally:
        c.close()

def init_db():
    DB.parent.mkdir(exist_ok=True)
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS clubs(
            club_id TEXT PRIMARY KEY, name TEXT, stadium TEXT, region_id TEXT, team_id TEXT,
            games_played INTEGER, wins INTEGER, ties INTEGER, losses INTEGER,
            goals INTEGER, goals_against INTEGER, skill_rating REAL,
            win_streak INTEGER, unbeaten_streak INTEGER, promotions INTEGER,
            relegations INTEGER, best_division INTEGER, updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS members(
            club_id TEXT, name TEXT, player_name TEXT, position TEXT, overall REAL,
            games_played INTEGER, win_rate REAL, goals INTEGER, assists INTEGER,
            average_rating REAL, motm INTEGER, shot_success_rate REAL,
            passes_made INTEGER, pass_success_rate REAL, tackles_made INTEGER,
            tackle_success_rate REAL, clean_sheets_def INTEGER, clean_sheets_gk INTEGER,
            red_cards INTEGER, updated_at TEXT,
            PRIMARY KEY(club_id, name)
        );
        CREATE TABLE IF NOT EXISTS matches(
            club_id TEXT, match_id TEXT, match_type TEXT, timestamp TEXT,
            club_name TEXT, opponent_id TEXT, opponent_name TEXT,
            goals INTEGER, goals_against INTEGER, result TEXT, dnf INTEGER,
            PRIMARY KEY(club_id, match_id)
        );
        CREATE TABLE IF NOT EXISTS player_matches(
            club_id TEXT, match_id TEXT, match_type TEXT, timestamp TEXT,
            player_id TEXT, name TEXT, position TEXT, rating REAL, goals INTEGER,
            assists INTEGER, shots INTEGER, passes_made INTEGER, pass_attempts INTEGER,
            tackles_made INTEGER, tackle_attempts INTEGER, saves INTEGER,
            clean_sheet INTEGER, motm INTEGER, red_cards INTEGER, seconds_played INTEGER,
            PRIMARY KEY(club_id, match_id, player_id, name)
        );
        """)

init_db()

def rowval(row, key, default=None):
    v = row.get(key, default)
    return default if v is None or (isinstance(v, float) and math.isnan(v)) else clean(v)

def safe_matches(club_id: str, match_type: str):
    """Parse raw EA matches defensively; tolerates null clubs/details/players."""
    raw = api._get_matches(str(club_id), match_type, 10) or []
    out = []
    for m in raw:
        if not isinstance(m, dict): continue
        clubs = m.get("clubs") or {}
        if not isinstance(clubs, dict): continue
        us = clubs.get(str(club_id)) or {}
        if not isinstance(us, dict): us = {}
        opp_id, them = None, {}
        for oid, oval in clubs.items():
            if str(oid) != str(club_id):
                opp_id = str(oid)
                them = oval if isinstance(oval, dict) else {}
                break
        def i(v):
            try: return int(float(v or 0))
            except Exception: return 0
        gp = i(us.get("goals")); gc = i(us.get("goalsAgainst"))
        if str(us.get("wins")) == "1": result = "win"
        elif str(us.get("losses")) == "1": result = "loss"
        elif str(us.get("ties")) == "1": result = "draw"
        else: result = "win" if gp > gc else "loss" if gp < gc else "draw"
        ud = us.get("details") or {}; td = them.get("details") or {}
        if not isinstance(ud, dict): ud = {}
        if not isinstance(td, dict): td = {}
        out.append({
            "matchId": str(m.get("matchId") or ""),
            "timestamp": m.get("timestamp"),
            "matchType": match_type,
            "clubId": str(club_id),
            "clubName": ud.get("name"),
            "opponentId": opp_id,
            "opponentName": td.get("name") or "Adversário",
            "goals": gp, "goalsAgainst": gc, "result": result,
            "dnf": str(us.get("winnerByDnf")) == "1" or str(them.get("winnerByDnf")) == "1",
            "_raw": m,
        })
    # normalize timestamps through pandas
    for x in out:
        try:
            t = pd.to_datetime(x["timestamp"], unit="s", utc=True).tz_convert("America/Sao_Paulo").tz_localize(None)
            x["timestamp"] = t.isoformat(sep=" ", timespec="seconds")
        except Exception:
            try:
                t = pd.to_datetime(x["timestamp"], utc=True).tz_convert("America/Sao_Paulo").tz_localize(None)
                x["timestamp"] = t.isoformat(sep=" ", timespec="seconds")
            except Exception:
                x["timestamp"] = str(x["timestamp"] or "")
    return out

def update_club(club_name: str):
    club_id = str(api.find_club_id(club_name))
    details = records(api.get_club_details(club_id))
    overall = records(api.get_club_overall_stats(club_id))
    members = records(api.get_member_stats(club_id))
    d = details[0] if details else {}
    o = overall[0] if overall else {}
    official_name = d.get("clubName") or club_name
    now = datetime.now().isoformat(sep=" ", timespec="seconds")

    with conn() as c:
        c.execute("""INSERT INTO clubs(club_id,name,stadium,region_id,team_id,games_played,wins,ties,losses,goals,goals_against,
        skill_rating,win_streak,unbeaten_streak,promotions,relegations,best_division,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(club_id) DO UPDATE SET
        name=excluded.name,stadium=excluded.stadium,region_id=excluded.region_id,team_id=excluded.team_id,
        games_played=excluded.games_played,wins=excluded.wins,ties=excluded.ties,losses=excluded.losses,
        goals=excluded.goals,goals_against=excluded.goals_against,skill_rating=excluded.skill_rating,
        win_streak=excluded.win_streak,unbeaten_streak=excluded.unbeaten_streak,promotions=excluded.promotions,
        relegations=excluded.relegations,best_division=excluded.best_division,updated_at=excluded.updated_at""",
        (club_id, official_name, d.get("stadium"), str(d.get("regionId") or ""), str(d.get("teamId") or ""),
         o.get("gamesPlayed"), o.get("wins"), o.get("ties"), o.get("losses"), o.get("goals"), o.get("goalsAgainst"),
         o.get("skillRating"), o.get("winStreak"), o.get("unbeatenStreak"), o.get("promotions"), o.get("relegations"),
         o.get("bestDivision"), now))

        c.execute("DELETE FROM members WHERE club_id=?", (club_id,))
        for m in members:
            c.execute("""INSERT OR REPLACE INTO members VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                club_id, str(m.get("name") or m.get("playerName") or "Jogador"), str(m.get("playerName") or ""),
                str(m.get("position") or ""), m.get("overall"), m.get("gamesPlayed"), m.get("winRate"),
                m.get("goals"), m.get("assists"), m.get("averageRating"), m.get("manOfTheMatch"),
                m.get("shotSuccessRate"), m.get("passesMade"), m.get("passSuccessRate"), m.get("tacklesMade"),
                m.get("tackleSuccessRate"), m.get("cleanSheetsDef"), m.get("cleanSheetsGK"), m.get("redCards"), now
            ))

    new_matches = 0
    new_player_rows = 0
    for mt in MATCH_TYPES:
        ms = safe_matches(club_id, mt)
        with conn() as c:
            for m in ms:
                mid = m["matchId"]
                if not mid: continue
                exists = c.execute("SELECT 1 FROM matches WHERE club_id=? AND match_id=?", (club_id, mid)).fetchone()
                c.execute("""INSERT OR REPLACE INTO matches VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (
                    club_id, mid, mt, m["timestamp"], m.get("clubName") or official_name,
                    m.get("opponentId"), m.get("opponentName"), m["goals"], m["goalsAgainst"],
                    m["result"], int(bool(m["dnf"]))
                ))
                if not exists: new_matches += 1

                raw = m.get("_raw") or {}
                pclubs = raw.get("players") or {}
                if not isinstance(pclubs, dict): continue
                players = pclubs.get(str(club_id)) or {}
                if not isinstance(players, dict): continue
                for pid, s in players.items():
                    if not isinstance(s, dict): continue
                    name = str(s.get("playername") or s.get("name") or pid or "Jogador")
                    existed = c.execute("""SELECT 1 FROM player_matches WHERE club_id=? AND match_id=? AND player_id=? AND name=?""",
                                        (club_id, mid, str(pid), name)).fetchone()
                    def num(key, default=0):
                        try: return float(s.get(key, default) or default)
                        except Exception: return default
                    c.execute("""INSERT OR REPLACE INTO player_matches VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                        club_id, mid, mt, m["timestamp"], str(pid), name, str(s.get("pos") or ""),
                        num("rating"), int(num("goals")), int(num("assists")), int(num("shots")),
                        int(num("passesmade")), int(num("passattempts")), int(num("tacklesmade")),
                        int(num("tackleattempts")), int(num("saves")), int(num("cleansheetsany")),
                        int(num("mom")), int(num("redcards")), int(num("secondsPlayed"))
                    ))
                    if not existed: new_player_rows += 1

    with conn() as c:
        total = c.execute("SELECT COUNT(*) n FROM matches WHERE club_id=?", (club_id,)).fetchone()["n"]
    return {"club_id": club_id, "name": official_name, "new_matches": new_matches,
            "new_player_rows": new_player_rows, "total_matches": total}


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    from fastapi import Response
    return Response(status_code=204)

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={})

@app.get("/api/clubs")
def clubs():
    with conn() as c:
        return [dict(r) for r in c.execute("""SELECT c.*,
          (SELECT COUNT(*) FROM matches m WHERE m.club_id=c.club_id) total_matches
          FROM clubs c ORDER BY updated_at DESC""")]

@app.get("/api/search")
def search(q: str = Query(min_length=2)):
    try:
        return records(api.search_club_by_name(q))
    except Exception as e:
        raise HTTPException(502, str(e))

@app.get("/health")
def health():
    return {"status": "ok", "database": str(DB)}

@app.post("/api/update")
def update(q: str = Query(min_length=2), x_admin_token: str | None = Header(default=None)):
    if ADMIN_TOKEN and not x_admin_token:
        raise HTTPException(401, "Senha de atualização necessária.")
    if ADMIN_TOKEN and not hmac.compare_digest(x_admin_token or "", ADMIN_TOKEN):
        raise HTTPException(403, "Senha de atualização incorreta.")
    log_path = DATA_DIR / "LOG_ATUALIZACAO_CLUBE.txt"
    def ulog(msg):
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(sep=' ', timespec='seconds')} | {msg}\n")
    ulog(f"INICIO | clube={q}")
    try:
        result = update_club(q)
        ulog(f"SUCESSO | clube={q} | {result}")
        return result
    except (FC27APIError, ValueError) as e:
        ulog(f"ERRO API | clube={q} | {type(e).__name__}: {e}")
        raise HTTPException(502, str(e))
    except Exception as e:
        import traceback
        ulog(f"ERRO INTERNO | clube={q} | {type(e).__name__}: {e}\n{traceback.format_exc()}")
        raise HTTPException(500, f"Falha ao atualizar: {e}")

@app.get("/api/club/{club_id}")
def club(club_id: str, limit: int = 20):
    with conn() as c:
        cr = c.execute("SELECT * FROM clubs WHERE club_id=?", (club_id,)).fetchone()
        if not cr: raise HTTPException(404, "Clube não salvo.")
        members = [dict(r) for r in c.execute("""SELECT * FROM members WHERE club_id=?
            ORDER BY goals DESC, assists DESC, average_rating DESC""", (club_id,))]
        matches = [dict(r) for r in c.execute("""SELECT * FROM matches WHERE club_id=?
            ORDER BY timestamp DESC LIMIT ?""", (club_id, max(1, min(limit, 1000))))]
        return {"club": dict(cr), "members": members, "matches": matches}

@app.get("/api/club/{club_id}/matches")
def matches(club_id: str, limit: int = 50, match_type: str = "all"):
    sql = "SELECT * FROM matches WHERE club_id=?"
    args = [club_id]
    if match_type != "all":
        sql += " AND match_type=?"; args.append(match_type)
    sql += " ORDER BY timestamp DESC LIMIT ?"; args.append(max(1, min(limit, 2000)))
    with conn() as c:
        return [dict(r) for r in c.execute(sql, args)]

@app.get("/api/club/{club_id}/match/{match_id}")
def match_detail(club_id: str, match_id: str):
    with conn() as c:
        m = c.execute("SELECT * FROM matches WHERE club_id=? AND match_id=?", (club_id, match_id)).fetchone()
        if not m: raise HTTPException(404, "Partida não encontrada.")
        p = [dict(r) for r in c.execute("""SELECT * FROM player_matches WHERE club_id=? AND match_id=?
             ORDER BY rating DESC, goals DESC, assists DESC""", (club_id, match_id))]
        return {"match": dict(m), "players": p}

@app.get("/api/club/{club_id}/rankings")
def rankings(club_id: str, last: int = 0):
    with conn() as c:
        mids = []
        if last > 0:
            mids = [r["match_id"] for r in c.execute("""SELECT match_id FROM matches WHERE club_id=?
                ORDER BY timestamp DESC LIMIT ?""", (club_id, min(last, 1000)))]
        where = "club_id=?"; args = [club_id]
        if mids:
            where += " AND match_id IN (%s)" % ",".join("?" * len(mids)); args += mids
        rows = [dict(r) for r in c.execute(f"""SELECT name, COUNT(*) games, SUM(goals) goals, SUM(assists) assists,
            ROUND(AVG(rating),2) average_rating, SUM(motm) motm, SUM(passes_made) passes_made,
            SUM(pass_attempts) pass_attempts, SUM(tackles_made) tackles_made, SUM(tackle_attempts) tackle_attempts
            FROM player_matches WHERE {where} GROUP BY name
            ORDER BY goals DESC, assists DESC, average_rating DESC""", args)]
        return rows

@app.get("/api/club/{club_id}/player/{name}")
def player(club_id: str, name: str):
    with conn() as c:
        rows = [dict(r) for r in c.execute("""SELECT p.*, m.opponent_name, m.goals club_goals, m.goals_against,
            m.result FROM player_matches p JOIN matches m
            ON m.club_id=p.club_id AND m.match_id=p.match_id
            WHERE p.club_id=? AND p.name=? ORDER BY p.timestamp DESC""", (club_id, name))]
        if not rows: raise HTTPException(404, "Jogador não encontrado.")
        return rows

@app.get("/api/club/{club_id}/export.xlsx")
def export_excel(club_id: str):
    with conn() as c:
        club = c.execute("SELECT * FROM clubs WHERE club_id=?", (club_id,)).fetchone()
        if not club: raise HTTPException(404, "Clube não encontrado.")
        members = [dict(r) for r in c.execute("SELECT * FROM members WHERE club_id=?", (club_id,))]
        matches = [dict(r) for r in c.execute("SELECT * FROM matches WHERE club_id=? ORDER BY timestamp DESC", (club_id,))]
        stats = [dict(r) for r in c.execute("SELECT * FROM player_matches WHERE club_id=? ORDER BY timestamp DESC", (club_id,))]
    wb = Workbook()
    ws = wb.active; ws.title = "Clube"
    def fill_sheet(ws, rows):
        if not rows: return
        headers = list(rows[0].keys())
        ws.append(headers)
        for cell in ws[1]:
            cell.fill = PatternFill("solid", fgColor="0B1730"); cell.font = Font(color="FFFFFF", bold=True)
        for r in rows: ws.append([r.get(h) for h in headers])
        ws.freeze_panes = "A2"; ws.auto_filter.ref = ws.dimensions
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = min(max(12, max(len(str(x.value or "")) for x in col)+2), 35)
    fill_sheet(ws, [dict(club)])
    fill_sheet(wb.create_sheet("Jogadores"), members)
    fill_sheet(wb.create_sheet("Partidas"), matches)
    fill_sheet(wb.create_sheet("Stats Jogadores"), stats)
    bio = io.BytesIO(); wb.save(bio); bio.seek(0)
    filename = f"FC27_{str(club['name']).replace(' ','_')}.xlsx"
    return StreamingResponse(bio, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'})

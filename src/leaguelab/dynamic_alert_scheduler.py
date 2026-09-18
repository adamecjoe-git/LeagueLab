"""LeagueLab game-day scheduler. Python 3.8 compatible."""
import argparse, csv, io, json, sys, time, urllib.error, urllib.request
from datetime import date, datetime
from leaguelab.roster_alert_runner import _build_schedule_source, _load_notification_config
URL="https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv"

def _dt(v):
    s=str(v or "").strip()
    if s.endswith("Z"): s=s[:-1]+"+00:00"
    try: return datetime.fromisoformat(s)
    except ValueError: return None

def _download(url, timeout=15, attempts=4):
    last=None
    for n in range(1,attempts+1):
        try:
            r=urllib.request.Request(url,headers={"User-Agent":"LeagueLab/1.0"})
            with urllib.request.urlopen(r,timeout=timeout) as x: raw=x.read()
            if not raw: raise RuntimeError("empty NFL schedule response")
            return raw.decode("utf-8-sig")
        except Exception as e:
            last=e
            if n<attempts: time.sleep(3*n)
    raise RuntimeError("NFL schedule download failed: {}".format(last))

def _week(day,cfg):
    sc=cfg.get("schedule",{}) or {}
    rows=csv.DictReader(io.StringIO(_download(sc.get("nflverse_url") or URL,int(sc.get("timeout_seconds",15)),int(sc.get("download_attempts",4)))))
    found=set()
    for r in rows:
        if str(r.get("gameday","")).strip()!=day.isoformat(): continue
        if str(r.get("game_type","")).strip().upper() not in ("","REG"): continue
        try: found.add((int(r["season"]),int(r["week"])))
        except Exception: pass
    if not found: return None
    if len(found)!=1: raise RuntimeError("multiple season/weeks found: {}".format(sorted(found)))
    s,w=next(iter(found)); return s,w

def build_daily_plan(day, force_refresh=True, now=None):
    cfg=_load_notification_config(); local=now or datetime.now().astimezone()
    sw=_week(day,cfg)
    if sw is None:
        return {"date":day.isoformat(),"games_today":False,"complete":True,"season":None,"week":None,"schedule":None,"kickoff_groups":[]}
    season,week=sw
    source,label=_build_schedule_source(config=cfg,season=season,week=week,force_refresh=force_refresh)
    groups={}
    for g in source.load_games():
        k=_dt(g.get("kickoff"))
        if not k: continue
        if k.tzinfo and local.tzinfo: k=k.astimezone(local.tzinfo)
        if k.date()!=day: continue
        key=k.isoformat()
        groups.setdefault(key,{"kickoff_at":key,"games":[]})["games"].append({"away":str(g.get("away","")).upper(),"home":str(g.get("home","")).upper()})
    gs=[groups[k] for k in sorted(groups)]
    return {"date":day.isoformat(),"games_today":bool(gs),"complete":not bool(gs),"season":season,"week":week,"schedule":label,"kickoff_groups":gs}

def main():
    p=argparse.ArgumentParser(); p.add_argument("--date"); p.add_argument("--no-refresh",action="store_true"); p.add_argument("--json",action="store_true"); a=p.parse_args()
    day=date.fromisoformat(a.date) if a.date else datetime.now().astimezone().date()
    plan=build_daily_plan(day,not a.no_refresh)
    if a.json: print(json.dumps(plan,indent=2,sort_keys=True))
    else:
        print("Date:",plan["date"]); print("Games today:",plan["games_today"])
        for g in plan["kickoff_groups"]: print(g["kickoff_at"],len(g["games"]),"game(s)")
if __name__=="__main__": main()

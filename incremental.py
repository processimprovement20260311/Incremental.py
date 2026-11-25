  LCT Incremental Season Simulator — Standalone Mode 10 Uses the original Mode 10 simulation mechanics. Run with: streamlit run lct_mode10_app.py import time import hashlib import json import os from dataclasses import dataclass from datetime import date, timedelta import streamlit as st import pandas as pd ============================================================ ENGINE CORE ============================================================ Q_HALF = 12 MARQUEE_OPENER_DATE = "Mar 03" MASTER_SCHEDULE_PATH = "master_schedule.json" MODE10_KEY = "mode10_season" MASK64 = (1 << 64) - 1 @dataclass class Ratings: OFF: float DEF: float SPT: float Overall: float RAW_RATINGS = { "STF": {"OFF":91,"DEF":99,"SPT":91}, "BRK": {"OFF":91,"DEF":99,"SPT":94}, "JRD": {"OFF":97,"DEF":92,"SPT":95}, "TAY": {"OFF":97,"DEF":92,"SPT":95}, "BRE": {"OFF":94,"DEF":95,"SPT":95}, "ASH": {"OFF":96,"DEF":94,"SPT":91}, "TRN": {"OFF":93,"DEF":94,"SPT":94}, "RSN": {"OFF":92,"DEF":95,"SPT":90}, "SZE": {"OFF":89,"DEF":91,"SPT":90}, "BRN": {"OFF":87,"DEF":92,"SPT":90}, "AND": {"OFF":86,"DEF":91,"SPT":81}, "ANG": {"OFF":88,"DEF":88,"SPT":84}, "HIL": {"OFF":86,"DEF":91,"SPT":75}, "TOR": {"OFF":89,"DEF":80,"SPT":90}, "CAS": {"OFF":86,"DEF":83,"SPT":79}, "ADR": {"OFF":83,"DEF":86,"SPT":73}, "KRS": {"OFF":78,"DEF":89,"SPT":80}, "OLV": {"OFF":84,"DEF":82,"SPT":80}, "GNN": {"OFF":77,"DEF":86,"SPT":81}, "LXI": {"OFF":81,"DEF":76,"SPT":79}, "SPH": {"OFF":79,"DEF":79,"SPT":75}, "NTL": {"OFF":74,"DEF":81,"SPT":75}, "JLN": {"OFF":82,"DEF":69,"SPT":82}, "RCH": {"OFF":74,"DEF":80,"SPT":75}, "HAL": {"OFF":91,"DEF":99,"SPT":90}, "SRA": {"OFF":79,"DEF":66,"SPT":77}, "AMB": {"OFF":69,"DEF":72,"SPT":74}, "CRT": {"OFF":69,"DEF":69,"SPT":75}, "KEL": {"OFF":72,"DEF":66,"SPT":76}, "KAT": {"OFF":67,"DEF":73,"SPT":79}, "RLY": {"OFF":69,"DEF":61,"SPT":75}, "GRG": {"OFF":69,"DEF":67,"SPT":69} } BASE_RATINGS = { t: Ratings( v["OFF"], v["DEF"], v["SPT"], round((v["OFF"]*3 + v["DEF"]*3 + v["SPT"])/7, 2) ) for t, v in RAW_RATINGS.items() } TEAMS = list(BASE_RATINGS) ============================================================ RANDOM NUMBER GENERATOR ============================================================ def rotl(x, k): return ((x << k) | (x >> (64-k))) & MASK64 class Xoshiro: def init(self, seed): s, z = [], seed & MASK64 for _ in range(4): z = (z + 0x9E3779B97F4A7C15) & MASK64 x = z x = ((x ^ (x >> 30))*0xBF58476D1CE4E5B9) & MASK64 x = ((x ^ (x >> 27))*0x94D049BB133111EB) & MASK64 x ^= x >> 31 s.append(x & MASK64) self.s = s  def next64(self):
	    s = self.s
	    r = (rotl((s[1]*5)&MASK64, 7)*9)&MASK64
	    t = (s[1]<<17)&MASK64
	    s[2] ^= s[0]
	    s[3] ^= s[1]
	    s[1] ^= s[2]
	    s[0] ^= s[3]
	    s[2] ^= t
	    s[3] = rotl(s[3], 45)
	    return r
	
	def next_float(self):
	    return (self.next64() >> 11)/float(1<<53)
	
	def next_int(self, lo, hi):
	    return lo + int(self.next_float()*(hi-lo+1))
	  def subseed(master, label): h = hashlib.sha256(f"{master}:{label}".encode()).digest() return int.from_bytes(h[:8], "big") & MASK64 class SubStreams: def init(self, seed): self.streams = { l: Xoshiro(subseed(seed, l)) for l in [ "league_schedule","league_games","cup_draw","cup_games", "soe_draw","soe_games","playoff_games","tiebreaks", "wildcard","overtime","hac_games","hac_draw" ] }  def get(self, label):
	    return self.streams[label]
	  def substream_shuffle(seq, rng): for i in range(len(seq)-1, 0, -1): j = rng.next_int(0, i) seq[i], seq[j] = seq[j], seq[i] return seq ============================================================ GAME ENGINE ============================================================ COMP_STREAM_MAP = { "league":"league_games", "cup_group":"cup_games", "cup_knockout":"cup_games", "cup_final":"cup_games", "soe_r32":"soe_games", "soe_final":"soe_games", "playoff_wc":"playoff_games", "playoff_div":"playoff_games", "playoff_bracket":"playoff_games", "super_bowl":"playoff_games" } def clamp(x, lo, hi): return min(max(x, lo), hi) def rhu(x): return int(x+0.5) if x >= 0 else -int(-x+0.5) def weather_o_modifier(weather): return { "Clear":0, "Extreme Rain":-15, "Heavy Snow":-25, "Heavy Winds":-15, "Extreme Cold":-20 }[weather] def apply_weather_to_ratings(weather, hr, ar): mod = weather_o_modifier(weather)  h = Ratings(
	    max(1,hr.OFF+mod), max(1,hr.DEF+mod),
	    hr.SPT, max(1,hr.Overall+mod)
	)
	
	a = Ratings(
	    max(1,ar.OFF+mod), max(1,ar.DEF+mod),
	    ar.SPT, max(1,ar.Overall+mod)
	)
	
	return h, a
	  def is_marquee_game(comp, rnd, game_date): return ( comp in {"cup_final","soe_final","super_bowl"} or (comp=="league" and game_date==MARQUEE_OPENER_DATE) ) def sim_game(home, away, venue, must_win, subs, comp, rnd, game_date, ratings, season, forced_weather=None):  rng = subs.get(COMP_STREAM_MAP.get(comp,"league_games"))
	
	if is_marquee_game(comp,rnd,game_date):
	    weather = "Clear"
	elif forced_weather:
	    weather = forced_weather
	else:
	    r = rng.next_float()
	    weather = (
	        "Clear" if r<0.77 else
	        "Extreme Rain" if r<0.82 else
	        "Heavy Snow" if r<0.87 else
	        "Heavy Winds" if r<0.92 else
	        "Extreme Cold"
	    )
	
	hr, ar = apply_weather_to_ratings(
	    weather, ratings[home], ratings[away]
	)
	
	hV=rng.next_int(25,75)
	hX=rng.next_int(30,70)
	hG=rng.next_int(20,80)
	hC=rng.next_int(30,70)
	
	aV=rng.next_int(25,75)
	aX=rng.next_int(30,70)
	aG=rng.next_int(20,80)
	aC=rng.next_int(30,70)
	
	hQ=rng.next_int(-Q_HALF,Q_HALF)+rng.next_int(-Q_HALF,Q_HALF)
	aQ=rng.next_int(-Q_HALF,Q_HALF)+rng.next_int(-Q_HALF,Q_HALF)
	
	hMb=clamp(50+(hr.OFF-ar.DEF)/3,30,70)
	aMb=clamp(50+(ar.OFF-hr.DEF)/3,30,70)
	
	hM=(hMb+hX)/2
	aM=(aMb+aX)/2
	
	hP=0.70*hr.Overall+0.12*hV+0.08*hM+0.05*hG+0.05*hC
	aP=0.70*ar.Overall+0.12*aV+0.08*aM+0.05*aG+0.05*aC
	
	hBoost=2 if venue=="home" else 0
	
	hAdj=hP+hBoost
	aAdj=aP
	
	hs=rhu(max(24+0.4*(hAdj-73)+hQ,0))
	ass=rhu(max(24+0.4*(aAdj-73)+aQ,0))
	
	winner=None
	ot=False
	
	if hs>ass:
	    winner=home
	elif ass>hs:
	    winner=away
	elif must_win:
	    ot=True
	    orng=subs.get("overtime")
	    possessor_home=(orng.next_int(0,1)==0)
	
	    while True:
	        adj=hAdj if possessor_home else aAdj
	        eot=24+0.4*((adj-5)-73)
	        pr=clamp(eot/48,0,1)
	
	        if orng.next_float()<pr:
	            t=orng.next_float()
	            pts=6 if t<0.60 else (3 if t<0.98 else 2)
	
	            if possessor_home:
	                hs+=pts
	                winner=home
	            else:
	                ass+=pts
	                winner=away
	            break
	
	        possessor_home=not possessor_home
	
	return {
	    "home_team":home,
	    "away_team":away,
	    "home_score":hs,
	    "away_score":ass,
	    "winner":winner,
	    "went_to_overtime":ot,
	    "weather":weather,
	    "competition":comp,
	    "round":rnd,
	    "date":game_date
	}
	  ============================================================ LEAGUE SCHEDULE ============================================================ def circle_method_rounds(teams): arr=teams[:] rounds=[]  for r in range(len(teams)-1):
	    pairs=[
	        (arr[i],arr[len(teams)-1-i])
	        for i in range(len(teams)//2)
	    ]
	    rounds.append(pairs)
	    arr=[arr[0]]+[arr[-1]]+arr[1:-1]
	
	return rounds
	  def build_master_schedule(teams): base=circle_method_rounds(teams) oriented=[]  for ri,pairs in enumerate(base):
	    games=[]
	    for a,b in pairs:
	        games.append(
	            (a,b) if (ri+teams.index(a))%2==0 else (b,a)
	        )
	    oriented.append(games)
	
	return {"teams":teams,"base_rounds":oriented}
	  def load_or_build_master_schedule(teams): if os.path.exists(MASTER_SCHEDULE_PATH): try: with open(MASTER_SCHEDULE_PATH) as f: data=json.load(f) if data.get("teams")==teams: return data except Exception: pass  data=build_master_schedule(teams)
	
	with open(MASTER_SCHEDULE_PATH,"w") as f:
	    json.dump(data,f,indent=2)
	
	return data
	  def build_league_season_schedule(master, season_num, defending_champ=None): teams=master["teams"] base=master["base_rounds"]  nso_idx=(season_num-1)%31
	regular=[(nso_idx+k)%31 for k in range(1,31)]
	
	schedule=[]
	
	for rn,bi in enumerate(regular,start=1):
	    for h,a in base[bi]:
	        schedule.append({
	            "round":rn,"home":h,"away":a,"venue":"home"
	        })
	
	for h,a in base[nso_idx]:
	    schedule.append({
	        "round":31,"home":h,"away":a,"venue":"neutral"
	    })
	    schedule.append({
	        "round":32,"home":a,"away":h,"venue":"neutral"
	    })
	
	for rn,bi in enumerate(regular,start=33):
	    for h,a in base[bi]:
	        schedule.append({
	            "round":rn,"home":a,"away":h,"venue":"home"
	        })
	
	if season_num>=2 and defending_champ:
	    for g in schedule:
	        if g["round"]==1 and defending_champ in (g["home"],g["away"]):
	            if g["away"]==defending_champ:
	                opponent=g["home"]
	                g["home"],g["away"]=defending_champ,opponent
	
	                for x in schedule:
	                    if x["round"]>=33 and x["home"]==opponent and x["away"]==defending_champ:
	                        x["home"],x["away"]=defending_champ,opponent
	                        break
	            break
	
	counts={t:0 for t in teams}
	
	for g in schedule:
	    counts[g["home"]]+=1
	    counts[g["away"]]+=1
	
	assert all(v==62 for v in counts.values())
	assert len(schedule)==992
	
	return schedule
	  def assign_league_dates(schedule):  def daterange(start,end):
	    out=[]
	    while start<=end:
	        out.append(start)
	        start+=timedelta(days=1)
	    return out
	
	Y=2026
	
	r1=[g for g in schedule if g["round"]==1]
	r2=[g for g in schedule if 2<=g["round"]<=30]
	r31=[g for g in schedule if 31<=g["round"]<=32]
	r33=[g for g in schedule if 33<=g["round"]<=61]
	r62=[g for g in schedule if g["round"]==62]
	
	r1[0]["date"]="Mar 03"
	
	pool=r1[1:]+r2
	window=daterange(date(Y,3,4),date(Y,5,22))
	used={}
	idx=0
	
	for g in pool:
	    for attempt in range(len(window)):
	        d=window[(idx+attempt)%len(window)]
	        key=d.isoformat()
	        used.setdefault(key,set())
	
	        if g["home"] not in used[key] and g["away"] not in used[key]:
	            g["date"]=d.strftime("%b %d")
	            used[key].update([g["home"],g["away"]])
	            idx=(idx+attempt+1)%len(window)
	            break
	
	nso_days=daterange(date(Y,5,23),date(Y,5,26))
	
	for i,g in enumerate(r31):
	    g["date"]=nso_days[i//8].strftime("%b %d")
	
	window=daterange(date(Y,6,1),date(Y,8,26))
	used={}
	idx=0
	
	for g in r33:
	    for attempt in range(len(window)):
	        d=window[(idx+attempt)%len(window)]
	        key=d.isoformat()
	        used.setdefault(key,set())
	
	        if g["home"] not in used[key] and g["away"] not in used[key]:
	            g["date"]=d.strftime("%b %d")
	            used[key].update([g["home"],g["away"]])
	            idx=(idx+attempt+1)%len(window)
	            break
	
	for g in r62:
	    g["date"]="Aug 27"
	
	return schedule
	  ============================================================ LEAGUE TABLE ============================================================ def compute_league_table(schedule, results, tiebreak_rng=None):  table={
	    t:{
	        "pts":0,"gd":0,"gf":0,"w":0,"d":0,"l":0,
	        "away_pts":0,"h2h":{}
	    }
	    for t in TEAMS
	}
	
	for r in results:
	    h,a=r["home_team"],r["away_team"]
	    hs,ass=r["home_score"],r["away_score"]
	
	    if r["competition"]!="league":
	        continue
	
	    table[h]["gf"]+=hs
	    table[h]["gd"]+=hs-ass
	    table[a]["gf"]+=ass
	    table[a]["gd"]+=ass-hs
	    table[a]["away_pts"]+=ass
	
	    for team,opponent,score,other in [
	        (h,a,hs,ass),(a,h,ass,hs)
	    ]:
	        item=table[team]["h2h"].setdefault(
	            opponent,{"pts":0,"gd":0}
	        )
	        item["pts"]+=3 if score>other else (1 if score==other else 0)
	        item["gd"]+=score-other
	
	    if hs>ass:
	        table[h]["pts"]+=3
	        table[h]["w"]+=1
	        table[a]["l"]+=1
	    elif ass>hs:
	        table[a]["pts"]+=3
	        table[a]["w"]+=1
	        table[h]["l"]+=1
	    else:
	        table[h]["pts"]+=1
	        table[a]["pts"]+=1
	        table[h]["d"]+=1
	        table[a]["d"]+=1
	
	groups={}
	
	for t in TEAMS:
	    groups.setdefault(table[t]["pts"],[]).append(t)
	
	ranked=[]
	
	for pts in sorted(groups,reverse=True):
	    grp=groups[pts]
	
	    def h2h_pts(t):
	        return sum(table[t]["h2h"].get(o,{"pts":0})["pts"]
	                   for o in grp if o!=t)
	
	    def h2h_gd(t):
	        return sum(table[t]["h2h"].get(o,{"gd":0})["gd"]
	                   for o in grp if o!=t)
	
	    grp.sort(key=lambda t:(
	        -h2h_pts(t),-table[t]["gd"],
	        -h2h_gd(t),-table[t]["away_pts"]
	    ))
	
	    ranked.extend(grp)
	
	return ranked,table
	  ============================================================ SOE TIE RESOLUTION ============================================================ def resolve_soe_tie(t1,t2,r1,r2,subs,leg2_date):  a1=r1["home_score"]+r2["away_score"]
	a2=r1["away_score"]+r2["home_score"]
	
	if a1>a2:
	    return t1,False,None
	if a2>a1:
	    return t2,False,None
	
	if r2["away_score"]>r1["away_score"]:
	    return t1,False,None
	if r1["away_score"]>r2["away_score"]:
	    return t2,False,None
	
	game=sim_game(
	    t2,t1,"home",True,subs,"soe_r32","L2-OT",
	    leg2_date,BASE_RATINGS,0,
	    forced_weather=_CURRENT_WEATHER
	)
	
	return game["winner"],True,game
	  ============================================================ MODE 10 STATE MACHINE ============================================================ def game_subs(seed,season,tag,idx): return SubStreams( subseed(seed,f"S{season}:{tag}:{idx}") ) def m10_new_state(seed,season_num=1,defending_champ=None):  master=load_or_build_master_schedule(TEAMS)
	
	schedule=assign_league_dates(
	    build_league_season_schedule(
	        master,season_num,defending_champ
	    )
	)
	
	return {
	    "run_seed":seed,
	    "season":season_num,
	    "phase":"league",
	    "weather":None if _CURRENT_WEATHER=="Random" else _CURRENT_WEATHER,
	    "schedule":schedule,
	    "league_results":[],
	    "league_next_round":1,
	    "cup":None,
	    "soe":None,
	    "playoffs":None
	}
	  def m10_step_league(state,upto_round):  start=state["league_next_round"]
	
	existing={
	    (r["round_num"],r["home_team"],r["away_team"])
	    for r in state["league_results"]
	}
	
	for idx,g in enumerate(state["schedule"]):
	
	    rn=g["round"]
	
	    if rn<start or rn>upto_round:
	        continue
	
	    key=(rn,g["home"],g["away"])
	
	    if key in existing:
	        continue
	
	    subs=game_subs(state["run_seed"],state["season"],"L",idx)
	
	    r=sim_game(
	        g["home"],g["away"],g["venue"],False,subs,
	        "league",f"R{rn}",g["date"],BASE_RATINGS,
	        state["season"],state["weather"]
	    )
	
	    r["round_num"]=rn
	    state["league_results"].append(r)
	
	state["league_next_round"]=upto_round+1
	
	return state
	  def m10_league_table(state): return compute_league_table( state["schedule"],state["league_results"] ) ---------------- CUP ---------------- def init_cup(state):  teams=TEAMS[:]
	draw=SubStreams(
	    subseed(state["run_seed"],f"S{state['season']}:cup_draw")
	)
	
	substream_shuffle(teams,draw.get("cup_draw"))
	
	return {
	    "groups":[teams[i*4:(i+1)*4] for i in range(8)],
	    "stage":"group",
	    "group_results":[],
	    "group_done":[False]*8,
	    "winners":None,
	    "runners":None,
	    "seeds":None,
	    "r16":None,
	    "qf":None,
	    "sf":None,
	    "final":None
	}
	  def step_cup_group(state,gi):  cup=state["cup"]
	
	if cup["group_done"][gi]:
	    return state
	
	grp=cup["groups"][gi]
	
	for i in range(4):
	    for j in range(4):
	
	        if i==j:
	            continue
	
	        idx=gi*1000+i*4+j
	        subs=game_subs(state["run_seed"],state["season"],"CG",idx)
	
	        r=sim_game(
	            grp[i],grp[j],"home",False,subs,
	            "cup_group","G","TBD",BASE_RATINGS,
	            state["season"],state["weather"]
	        )
	
	        r["group"]=chr(65+gi)
	        cup["group_results"].append(r)
	
	cup["group_done"][gi]=True
	
	return state
	  def cup_group_table(cup,gi):  grp=cup["groups"][gi]
	pts={t:0 for t in grp}
	gd={t:0 for t in grp}
	gf={t:0 for t in grp}
	
	for r in cup["group_results"]:
	    if r.get("group")!=chr(65+gi):
	        continue
	
	    h,a=r["home_team"],r["away_team"]
	    hs,ass=r["home_score"],r["away_score"]
	
	    gf[h]+=hs
	    gf[a]+=ass
	    gd[h]+=hs-ass
	    gd[a]+=ass-hs
	
	    if hs>ass:
	        pts[h]+=3
	    elif ass>hs:
	        pts[a]+=3
	    else:
	        pts[h]+=1
	        pts[a]+=1
	
	ordered=sorted(grp,key=lambda t:(-pts[t],-gd[t],-gf[t]))
	
	return ordered,pts,gd,gf
	  def finalize_cup_groups(state):  cup=state["cup"]
	winners=[]
	runners=[]
	
	for gi in range(8):
	    ordered,_,_,_=cup_group_table(cup,gi)
	    winners.append(ordered[0])
	    runners.append(ordered[1])
	
	cup["winners"]=winners
	cup["runners"]=runners
	cup["seeds"]=winners+runners
	cup["stage"]="r16"
	
	return state
	  def play_bo7(state,hi,lo,tag,idx):  wins={hi:0,lo:0}
	games=[]
	
	for g in range(7):
	
	    subs=game_subs(
	        state["run_seed"],state["season"],tag,idx*10+g
	    )
	
	    r=sim_game(
	        hi,lo,"home",True,subs,"cup_knockout",
	        "Bo7","TBD",BASE_RATINGS,state["season"],
	        state["weather"]
	    )
	
	    wins[r["winner"]]+=1
	    games.append(r)
	
	winner=hi if wins[hi]>wins[lo] else lo
	
	return {
	    "winner":winner,
	    "matchup":f"{hi} vs {lo}",
	    "series":f"{wins[hi]}-{wins[lo]}",
	    "games":games
	}
	  def step_cup_r16(state):  cup=state["cup"]
	if cup["r16"] is not None:
	    return state
	
	seeds=cup["seeds"]
	
	cup["r16"]=[
	    play_bo7(state,seeds[i],seeds[15-i],"C16",i)
	    for i in range(8)
	]
	
	cup["stage"]="qf"
	return state
	  def step_cup_qf(state):  cup=state["cup"]
	if cup["qf"] is not None:
	    return state
	
	w=[x["winner"] for x in cup["r16"]]
	pairs=[(0,7),(3,4),(1,6),(2,5)]
	
	cup["qf"]=[
	    play_bo7(state,w[a],w[b],"CQF",k)
	    for k,(a,b) in enumerate(pairs)
	]
	
	cup["stage"]="sf"
	return state
	  def step_cup_sf(state):  cup=state["cup"]
	if cup["sf"] is not None:
	    return state
	
	w=[x["winner"] for x in cup["qf"]]
	
	cup["sf"]=[
	    play_bo7(state,w[0],w[1],"CSF",0),
	    play_bo7(state,w[2],w[3],"CSF",1)
	]
	
	cup["stage"]="final"
	return state
	  def step_cup_final(state):  cup=state["cup"]
	
	if cup["final"] is not None:
	    return state
	
	hi=cup["sf"][0]["winner"]
	lo=cup["sf"][1]["winner"]
	
	subs=game_subs(state["run_seed"],state["season"],"CFIN",0)
	
	cup["final"]=sim_game(
	    hi,lo,"neutral",True,subs,"cup_final",
	    "Final","Oct 26",BASE_RATINGS,state["season"],
	    state["weather"]
	)
	
	cup["stage"]="done"
	
	return state
	  ---------------- SOE ---------------- def init_soe(state):  teams=TEAMS[:]
	
	draw=SubStreams(
	    subseed(state["run_seed"],f"S{state['season']}:soe_draw")
	)
	
	substream_shuffle(teams,draw.get("soe_draw"))
	
	return {
	    "teams":teams,
	    "stage":"r32",
	    "r32":None,"r16":None,"qf":None,
	    "sf":None,"final":None
	}
	  def soe_two_leg(state,t1,t2,tag,idx):  s1=game_subs(state["run_seed"],state["season"],tag+"A",idx)
	s2=game_subs(state["run_seed"],state["season"],tag+"B",idx)
	
	r1=sim_game(
	    t1,t2,"home",False,s1,"soe_r32","L1","TBD",
	    BASE_RATINGS,state["season"],state["weather"]
	)
	
	r2=sim_game(
	    t2,t1,"home",False,s2,"soe_r32","L2","TBD",
	    BASE_RATINGS,state["season"],state["weather"]
	)
	
	tie_subs=game_subs(
	    state["run_seed"],state["season"],tag+"OT",idx
	)
	
	winner,ot,ot_game=resolve_soe_tie(
	    t1,t2,r1,r2,tie_subs,"TBD"
	)
	
	a1=r1["home_score"]+r2["away_score"]
	a2=r1["away_score"]+r2["home_score"]
	
	aggregate=f"{a1}-{a2}"
	
	if a1==a2:
	    aggregate+=" (OT)" if ot else " (Away Pts)"
	
	return {
	    "winner":winner,
	    "matchup":f"{t1} vs {t2}",
	    "aggregate":aggregate,
	    "games":[r1,r2]+([ot_game] if ot_game else [])
	}
	  def step_soe(state,stage):  soe=state["soe"]
	
	if soe[stage] is not None:
	    return state
	
	if stage=="r32":
	    teams=soe["teams"]
	    tag="S32"
	else:
	    previous={"r16":"r32","qf":"r16","sf":"qf"}[stage]
	    teams=[x["winner"] for x in soe[previous]]
	    tag={"r16":"S16","qf":"SQF","sf":"SSF"}[stage]
	
	count=len(teams)//2
	
	soe[stage]=[
	    soe_two_leg(
	        state,teams[i*2],teams[i*2+1],tag,i
	    )
	    for i in range(count)
	]
	
	next_stage={
	    "r32":"r16","r16":"qf","qf":"sf","sf":"final"
	}
	
	soe["stage"]=next_stage[stage]
	
	return state
	  def step_soe_final(state):  soe=state["soe"]
	
	if soe["final"] is not None:
	    return state
	
	w=[x["winner"] for x in soe["sf"]]
	
	subs=game_subs(state["run_seed"],state["season"],"SFIN",0)
	
	soe["final"]=sim_game(
	    w[0],w[1],"neutral",True,subs,"soe_final",
	    "Final","Nov 24",BASE_RATINGS,state["season"],
	    state["weather"]
	)
	
	soe["stage"]="done"
	
	return state
	  ---------------- PLAYOFFS ---------------- def init_playoffs(state):  ranked,_=m10_league_table(state)
	
	league_champ=ranked[0]
	cup_champ=state["cup"]["final"]["winner"]
	soe_champ=state["soe"]["final"]["winner"]
	
	champs=[]
	
	for c in [league_champ,cup_champ,soe_champ]:
	    if c not in champs:
	        champs.append(c)
	
	fmt="13-Team" if league_champ==cup_champ else "14-Team"
	
	seeds={i+1:c for i,c in enumerate(champs)}
	
	wc_seed=len(champs)+1
	total=14 if fmt=="14-Team" else 13
	slots=total-len(champs)-1
	
	available=[t for t in ranked if t not in seeds.values()]
	
	for i,t in enumerate(available[:slots]):
	    seeds[wc_seed+1+i]=t
	
	wc_pool=[t for t in ranked if t not in seeds.values()]
	
	wc_rng=SubStreams(
	    subseed(state["run_seed"],f"S{state['season']}:wc")
	).get("wildcard")
	
	seeds[wc_seed]=wc_pool[
	    wc_rng.next_int(0,len(wc_pool)-1)
	]
	
	return {
	    "format":fmt,
	    "ranked":ranked,
	    "league_champ":league_champ,
	    "cup_champ":cup_champ,
	    "soe_champ":soe_champ,
	    "seeds":seeds,
	    "stage":"wc",
	    "wc":None,"div":None,"bc":None,"sb":None
	}
	  def step_playoffs(state,stage):  p=state["playoffs"]
	seeds=p["seeds"]
	
	if p[stage] is not None:
	    return state
	
	seed_lk={v:k for k,v in seeds.items()}
	
	if stage=="wc":
	
	    pairs=(
	        [(3+i,14-i) for i in range(6)]
	        if p["format"]=="14-Team"
	        else [(2+i,13-i) for i in range(6)]
	    )
	
	    p["wc"]=[]
	
	    for i,(hi,lo) in enumerate(pairs):
	
	        subs=game_subs(
	            state["run_seed"],state["season"],"PWC",i
	        )
	
	        p["wc"].append(sim_game(
	            seeds[hi],seeds[lo],"home",True,subs,
	            "playoff_wc","WC","TBD",BASE_RATINGS,
	            state["season"],state["weather"]
	        ))
	
	    p["stage"]="div"
	
	elif stage=="div":
	
	    wc_w=[r["winner"] for r in p["wc"]]
	
	    if p["format"]=="14-Team":
	        teams=[seeds[1],seeds[2]]+wc_w
	    else:
	        teams=wc_w
	
	    teams=sorted(teams,key=lambda t:seed_lk[t])
	
	    count=4 if p["format"]=="14-Team" else 3
	
	    p["div"]=[]
	
	    for i in range(count):
	
	        subs=game_subs(
	            state["run_seed"],state["season"],"PDIV",i
	        )
	
	        p["div"].append(sim_game(
	            teams[i],teams[-1-i],"home",True,subs,
	            "playoff_div","Div","TBD",BASE_RATINGS,
	            state["season"],state["weather"]
	        ))
	
	    p["stage"]="bc"
	
	elif stage=="bc":
	
	    winners=[r["winner"] for r in p["div"]]
	
	    if p["format"]=="13-Team":
	        winners=[seeds[1]]+winners
	
	    winners=sorted(winners,key=lambda t:seed_lk[t])
	
	    p["bc"]=[]
	
	    for i,(a,b) in enumerate([(0,3),(1,2)]):
	
	        subs=game_subs(
	            state["run_seed"],state["season"],"PBC",i
	        )
	
	        p["bc"].append(sim_game(
	            winners[a],winners[b],"home",True,subs,
	            "playoff_bracket","BC","TBD",BASE_RATINGS,
	            state["season"],state["weather"]
	        ))
	
	    p["stage"]="sb"
	
	elif stage=="sb":
	
	    winners=[r["winner"] for r in p["bc"]]
	
	    subs=game_subs(
	        state["run_seed"],state["season"],"PSB",0
	    )
	
	    p["sb"]=sim_game(
	        winners[0],winners[1],"neutral",True,subs,
	        "super_bowl","SB","Dec 23",BASE_RATINGS,
	        state["season"],state["weather"]
	    )
	
	    p["stage"]="done"
	
	return state
	  ============================================================ RESULTS DISPLAY HELPERS ============================================================ def show_games(games):  if not games:
	    st.info("No games completed yet.")
	    return
	
	rows=[]
	
	for g in games:
	    rows.append({
	        "Date":g.get("date","TBD"),
	        "Away":g["away_team"],
	        "Away Score":g["away_score"],
	        "Home":g["home_team"],
	        "Home Score":g["home_score"],
	        "Winner":g["winner"] or "Draw",
	        "Weather":g.get("weather","")
	    })
	
	st.dataframe(
	    pd.DataFrame(rows),
	    hide_index=True,
	    use_container_width=True
	)
	  def show_series(series):  if not series:
	    st.info("No completed matchups yet.")
	    return
	
	rows=[]
	
	for x in series:
	    rows.append({
	        "Matchup":x["matchup"],
	        "Winner":x["winner"],
	        "Series/Aggregate":x.get(
	            "series",x.get("aggregate","")
	        )
	    })
	
	st.dataframe(
	    pd.DataFrame(rows),
	    hide_index=True,
	    use_container_width=True
	)
	  def show_stage_games(data):  if not data:
	    st.info("This stage has not been simulated.")
	    return
	
	games=[]
	
	for x in data:
	    games.extend(x.get("games",[]))
	
	show_games(games)
	  def show_group_tables(cup):  for gi in range(8):
	
	    if not cup["group_done"][gi]:
	        continue
	
	    ordered,pts,gd,gf=cup_group_table(cup,gi)
	
	    st.markdown(f"**Group {chr(65+gi)}**")
	
	    st.dataframe(
	        pd.DataFrame([
	            {
	                "Position":i+1,
	                "Team":t,
	                "Points":pts[t],
	                "GD":gd[t],
	                "GF":gf[t],
	                "Status":(
	                    "Group Champion" if i==0 else
	                    "Runner-up" if i==1 else ""
	                )
	            }
	            for i,t in enumerate(ordered)
	        ]),
	        hide_index=True,
	        use_container_width=True
	    )
	  ============================================================ STREAMLIT APPLICATION ============================================================ st.set_page_config( page_title="LCT Mode 10 Simulator", page_icon="🏈", layout="wide" ) st.title("🏈 LCT Incremental Season Simulator") st.caption("Standalone Mode 10 — Incremental Season Engine") _CURRENT_WEATHER="Random" with st.sidebar:  st.header("Simulation Settings")
	
	_CURRENT_WEATHER=st.selectbox(
	    "Weather",
	    [
	        "Random","Clear","Extreme Rain",
	        "Heavy Snow","Heavy Winds","Extreme Cold"
	    ]
	)
	
	seed_input=st.text_input(
	    "Master seed (blank = automatic)",
	    value=""
	)
	
	st.divider()
	
	st.subheader("Team Ratings")
	
	st.dataframe(
	    pd.DataFrame([
	        {
	            "Team":t,
	            "OFF":v.OFF,
	            "DEF":v.DEF,
	            "SPT":v.SPT,
	            "Overall":v.Overall
	        }
	        for t,v in BASE_RATINGS.items()
	    ]),
	    hide_index=True,
	    use_container_width=True
	)
	  master_seed=None if seed_input.strip():  try:
	    master_seed=int(seed_input.strip())
	except ValueError:
	    st.sidebar.error("Seed must be an integer.")
	    st.stop()
	  if MODE10_KEY not in st.session_state: st.session_state[MODE10_KEY]=None s=st.session_state[MODE10_KEY] ============================================================ START / RESET ============================================================ if s is None:  st.info(
	    "Start a new season to begin the incremental simulation. "
	    "You can simulate one round or competition stage at a time."
	)
	
	if st.button("▶ Start New Season",type="primary"):
	
	    seed=(
	        master_seed if master_seed is not None
	        else int(time.time()*1000)&MASK64
	    )
	
	    st.session_state[MODE10_KEY]=m10_new_state(seed)
	
	    st.rerun()
	
	st.stop()
	  st.caption( f"Seed: {s['run_seed']} | " f"Season: {s['season']} | " f"Phase: {s['phase'].upper()} | " f"Weather: {s['weather'] or 'Random'}" ) if st.button("🔄 Reset Current Season"):  st.session_state[MODE10_KEY]=None
	st.rerun()
	  ============================================================ TOP-LEVEL NAVIGATION ============================================================ tab_live,tab_centre=st.tabs([ "🏟️ Live Competition", "📊 Season Results Centre" ]) ============================================================ LIVE COMPETITION ============================================================ with tab_live:  # --------------------------------------------------------
	# LEAGUE
	# --------------------------------------------------------
	
	if s["phase"]=="league":
	
	    st.header("League Phase")
	
	    nxt=s["league_next_round"]
	
	    st.write(f"Next round: **{nxt} of 62**")
	
	    if nxt<=62:
	
	        target=st.slider(
	            "Simulate through round",
	            nxt,62,min(nxt+4,62)
	        )
	
	        c1,c2=st.columns(2)
	
	        if c1.button(f"▶ Simulate through R{target}"):
	
	            s=m10_step_league(s,target)
	            st.session_state[MODE10_KEY]=s
	            st.rerun()
	
	        if c2.button("⏩ Finish League Phase"):
	
	            s=m10_step_league(s,62)
	
	            ranked,_=m10_league_table(s)
	
	            s["league_champion"]=ranked[0]
	            s["phase"]="cup"
	            s["cup"]=init_cup(s)
	
	            st.session_state[MODE10_KEY]=s
	            st.rerun()
	
	    ranked,table=m10_league_table(s)
	
	    played=len(s["league_results"])//16
	
	    st.subheader(f"League Standings — {played} Rounds Completed")
	
	    st.dataframe(
	        pd.DataFrame([
	            {
	                "Pos":i+1,
	                "Team":t,
	                "W":table[t]["w"],
	                "D":table[t]["d"],
	                "L":table[t]["l"],
	                "Pts":table[t]["pts"],
	                "GD":table[t]["gd"],
	                "GF":table[t]["gf"]
	            }
	            for i,t in enumerate(ranked)
	        ]),
	        hide_index=True,
	        use_container_width=True
	    )
	
	    if s.get("league_champion"):
	        st.success(f"League Champion: {s['league_champion']}")
	
	    with st.expander("View Completed League Matches"):
	
	        rounds=sorted(set(
	            r["round_num"] for r in s["league_results"]
	        ))
	
	        for rn in rounds:
	
	            st.markdown(f"**Round {rn}**")
	
	            show_games([
	                r for r in s["league_results"]
	                if r["round_num"]==rn
	            ])
	
	
	# --------------------------------------------------------
	# CUP
	# --------------------------------------------------------
	
	elif s["phase"]=="cup":
	
	    cup=s["cup"]
	
	    st.header("Cup Competition")
	
	    st.write(f"Current Stage: **{cup['stage'].upper()}**")
	
	    if cup["stage"]=="group":
	
	        done=sum(cup["group_done"])
	
	        st.progress(done/8)
	        st.write(f"Groups completed: {done}/8")
	
	        gsel=st.selectbox(
	            "Select group",
	            [chr(65+i) for i in range(8)]
	        )
	
	        gi=ord(gsel)-65
	
	        c1,c2=st.columns(2)
	
	        if c1.button(f"Simulate Group {gsel}"):
	
	            s=step_cup_group(s,gi)
	            st.session_state[MODE10_KEY]=s
	            st.rerun()
	
	        if c2.button("Simulate All Remaining Groups"):
	
	            for k in range(8):
	                if not cup["group_done"][k]:
	                    s=step_cup_group(s,k)
	
	            st.session_state[MODE10_KEY]=s
	            st.rerun()
	
	        st.subheader("Group Standings")
	        show_group_tables(cup)
	
	        if all(cup["group_done"]):
	
	            if st.button("✅ Finalize Groups → Round of 16"):
	
	                s=finalize_cup_groups(s)
	                st.session_state[MODE10_KEY]=s
	                st.rerun()
	
	
	    elif cup["stage"]=="r16":
	
	        st.subheader("Round of 16")
	
	        if st.button("Simulate Round of 16"):
	
	            s=step_cup_r16(s)
	            st.session_state[MODE10_KEY]=s
	            st.rerun()
	
	        show_series(cup["r16"])
	
	
	    elif cup["stage"]=="qf":
	
	        st.subheader("Quarterfinals")
	
	        if st.button("Simulate Quarterfinals"):
	
	            s=step_cup_qf(s)
	            st.session_state[MODE10_KEY]=s
	            st.rerun()
	
	        show_series(cup["r16"])
	        show_series(cup["qf"])
	
	
	    elif cup["stage"]=="sf":
	
	        st.subheader("Semifinals")
	
	        if st.button("Simulate Semifinals"):
	
	            s=step_cup_sf(s)
	            st.session_state[MODE10_KEY]=s
	            st.rerun()
	
	        show_series(cup["qf"])
	        show_series(cup["sf"])
	
	
	    elif cup["stage"]=="final":
	
	        st.subheader("Cup Final")
	
	        if st.button("Simulate Cup Final"):
	
	            s=step_cup_final(s)
	            st.session_state[MODE10_KEY]=s
	            st.rerun()
	
	        show_series(cup["sf"])
	
	
	    elif cup["stage"]=="done":
	
	        f=cup["final"]
	
	        st.success(f"🏆 Cup Champion: {f['winner']}")
	
	        show_games([f])
	
	        if st.button("➡ Proceed to SOE Phase"):
	
	            s["phase"]="soe"
	            s["soe"]=init_soe(s)
	
	            st.session_state[MODE10_KEY]=s
	            st.rerun()
	
	
	# --------------------------------------------------------
	# SOE
	# --------------------------------------------------------
	
	elif s["phase"]=="soe":
	
	    soe=s["soe"]
	
	    st.header("SOE Competition")
	
	    st.write(f"Current Stage: **{soe['stage'].upper()}**")
	
	    if soe["stage"]=="done":
	
	        f=soe["final"]
	
	        st.success(f"🏆 SOE Champion: {f['winner']}")
	
	        show_games([f])
	
	        if st.button("➡ Proceed to Playoffs"):
	
	            s["phase"]="playoffs"
	            s["playoffs"]=init_playoffs(s)
	
	            st.session_state[MODE10_KEY]=s
	            st.rerun()
	
	    else:
	
	        stages=[
	            ("r32","Round of 32"),
	            ("r16","Round of 16"),
	            ("qf","Quarterfinals"),
	            ("sf","Semifinals")
	        ]
	
	        labels=dict(stages)
	
	        if soe["stage"] in labels:
	
	            label=labels[soe["stage"]]
	
	            if st.button(f"Simulate {label}"):
	
	                s=step_soe(s,soe["stage"])
	                st.session_state[MODE10_KEY]=s
	                st.rerun()
	
	        for key,label in stages:
	
	            if soe[key]:
	
	                with st.expander(label,expanded=(key==soe["stage"])):
	
	                    show_series(soe[key])
	                    show_stage_games(soe[key])
	
	
	        if soe["stage"]=="final":
	
	            if st.button("Simulate SOE Final"):
	
	                s=step_soe_final(s)
	                st.session_state[MODE10_KEY]=s
	                st.rerun()
	
	
	# --------------------------------------------------------
	# PLAYOFFS
	# --------------------------------------------------------
	
	elif s["phase"]=="playoffs":
	
	    p=s["playoffs"]
	
	    st.header(f"Playoffs — {p['format']}")
	
	    st.subheader("Playoff Seeding")
	
	    st.dataframe(
	        pd.DataFrame([
	            {"Seed":k,"Team":v}
	            for k,v in sorted(p["seeds"].items())
	        ]),
	        hide_index=True,
	        use_container_width=True
	    )
	
	    if p["stage"]=="done":
	
	        sb=p["sb"]
	
	        st.success(f"🏆 SUPER BOWL CHAMPION: {sb['winner']}")
	
	        show_games([sb])
	
	        if st.button("➡ Start Next Season"):
	
	            new_seed=SubStreams(
	                subseed(
	                    s["run_seed"],
	                    f"S{s['season']+1}:season_roll"
	                )
	            ).get("league_schedule").next_int(0,2**31-1)
	
	            st.session_state[MODE10_KEY]=m10_new_state(
	                new_seed,
	                season_num=s["season"]+1,
	                defending_champ=sb["winner"]
	            )
	
	            st.rerun()
	
	    else:
	
	        stages=[
	            ("wc","Wild Card"),
	            ("div","Divisional Round"),
	            ("bc","Bracket Championship"),
	            ("sb","Super Bowl")
	        ]
	
	        for key,label in stages:
	
	            if p["stage"]==key:
	
	                if st.button(f"Simulate {label}"):
	
	                    s=step_playoffs(s,key)
	                    st.session_state[MODE10_KEY]=s
	                    st.rerun()
	
	                break
	
	    for key,label in [
	        ("wc","Wild Card"),
	        ("div","Divisional Round"),
	        ("bc","Bracket Championship"),
	        ("sb","Super Bowl")
	    ]:
	
	        if p[key]:
	
	            with st.expander(label,expanded=(key==p["stage"])):
	
	                show_games(
	                    p[key] if isinstance(p[key],list)
	                    else [p[key]]
	                )
	  ============================================================ SEASON RESULTS CENTRE ============================================================ with tab_centre:  st.header("📊 Season Results Centre")
	
	st.caption(
	    f"Season {s['season']} — "
	    "Review all completed competitions and match results."
	)
	
	# --------------------------------------------------------
	# CHAMPIONS SUMMARY
	# --------------------------------------------------------
	
	st.subheader("Competition Champions")
	
	league_champ=None
	cup_champ=None
	soe_champ=None
	sb_champ=None
	
	if s.get("league_champion"):
	    league_champ=s["league_champion"]
	
	elif s["league_next_round"]>62:
	    ranked,_=m10_league_table(s)
	    league_champ=ranked[0]
	
	if s["cup"] and s["cup"]["final"]:
	    cup_champ=s["cup"]["final"]["winner"]
	
	if s["soe"] and s["soe"]["final"]:
	    soe_champ=s["soe"]["final"]["winner"]
	
	if s["playoffs"] and s["playoffs"]["sb"]:
	    sb_champ=s["playoffs"]["sb"]["winner"]
	
	champion_data=pd.DataFrame([
	    {"Competition":"League","Champion":league_champ or "Pending"},
	    {"Competition":"Cup","Champion":cup_champ or "Pending"},
	    {"Competition":"SOE","Champion":soe_champ or "Pending"},
	    {"Competition":"Super Bowl","Champion":sb_champ or "Pending"}
	])
	
	st.dataframe(
	    champion_data,
	    hide_index=True,
	    use_container_width=True
	)
	
	st.divider()
	
	# --------------------------------------------------------
	# LEAGUE RESULTS
	# --------------------------------------------------------
	
	st.subheader("1. League Results")
	
	if s["league_results"]:
	
	    ranked,table=m10_league_table(s)
	
	    st.write("**League Standings**")
	
	    st.dataframe(
	        pd.DataFrame([
	            {
	                "Pos":i+1,
	                "Team":t,
	                "W":table[t]["w"],
	                "D":table[t]["d"],
	                "L":table[t]["l"],
	                "Pts":table[t]["pts"],
	                "GD":table[t]["gd"]
	            }
	            for i,t in enumerate(ranked)
	        ]),
	        hide_index=True,
	        use_container_width=True
	    )
	
	    rounds=sorted(set(
	        r["round_num"] for r in s["league_results"]
	    ))
	
	    selected_round=st.selectbox(
	        "View League Round",
	        rounds,
	        key="centre_league_round"
	    )
	
	    show_games([
	        r for r in s["league_results"]
	        if r["round_num"]==selected_round
	    ])
	
	else:
	    st.info("League matches have not started.")
	
	st.divider()
	
	# --------------------------------------------------------
	# CUP RESULTS
	# --------------------------------------------------------
	
	st.subheader("2. Cup Results")
	
	if s["cup"]:
	
	    cup=s["cup"]
	
	    show_group_tables(cup)
	
	    if cup["winners"]:
	
	        st.markdown("**Group Champions**")
	
	        st.dataframe(
	            pd.DataFrame([
	                {
	                    "Group":chr(65+i),
	                    "Champion":cup["winners"][i],
	                    "Runner-up":cup["runners"][i]
	                }
	                for i in range(8)
	            ]),
	            hide_index=True,
	            use_container_width=True
	        )
	
	    for key,label in [
	        ("r16","Round of 16"),
	        ("qf","Quarterfinals"),
	        ("sf","Semifinals")
	    ]:
	
	        if cup[key]:
	
	            with st.expander(label):
	
	                show_series(cup[key])
	
	                selected=st.selectbox(
	                    f"View {label} game details",
	                    range(len(cup[key])),
	                    format_func=lambda x:cup[key][x]["matchup"],
	                    key=f"cup_{key}_match"
	                )
	
	                show_games(cup[key][selected]["games"])
	
	    if cup["final"]:
	
	        st.markdown("**Cup Final**")
	        show_games([cup["final"]])
	
	else:
	    st.info("Cup competition has not started.")
	
	st.divider()
	
	# --------------------------------------------------------
	# SOE RESULTS
	# --------------------------------------------------------
	
	st.subheader("3. SOE Results")
	
	if s["soe"]:
	
	    soe=s["soe"]
	
	    for key,label in [
	        ("r32","Round of 32"),
	        ("r16","Round of 16"),
	        ("qf","Quarterfinals"),
	        ("sf","Semifinals")
	    ]:
	
	        if soe[key]:
	
	            with st.expander(label):
	
	                show_series(soe[key])
	
	                selected=st.selectbox(
	                    f"View {label} game details",
	                    range(len(soe[key])),
	                    format_func=lambda x:soe[key][x]["matchup"],
	                    key=f"soe_{key}_match"
	                )
	
	                show_games(soe[key][selected]["games"])
	
	    if soe["final"]:
	
	        st.markdown("**SOE Final**")
	        show_games([soe["final"]])
	
	else:
	    st.info("SOE competition has not started.")
	
	st.divider()
	
	# --------------------------------------------------------
	# PLAYOFF RESULTS
	# --------------------------------------------------------
	
	st.subheader("4. Playoff Results")
	
	if s["playoffs"]:
	
	    p=s["playoffs"]
	
	    st.write(f"**Format: {p['format']}**")
	
	    st.markdown("**Final Seeding**")
	
	    st.dataframe(
	        pd.DataFrame([
	            {"Seed":k,"Team":v}
	            for k,v in sorted(p["seeds"].items())
	        ]),
	        hide_index=True,
	        use_container_width=True
	    )
	
	    for key,label in [
	        ("wc","Wild Card"),
	        ("div","Divisional Round"),
	        ("bc","Bracket Championship"),
	        ("sb","Super Bowl")
	    ]:
	
	        data=p[key]
	
	        if data:
	
	            with st.expander(label,expanded=(key=="sb" and p["stage"]=="done")):
	
	                show_games(
	                    data if isinstance(data,list) else [data]
	                )
	
	else:
	    st.info("Playoffs have not started.")
	
	st.divider()
	
	# --------------------------------------------------------
	# EXPORT
	# --------------------------------------------------------
	
	st.subheader("5. Export Season Results")
	
	export=json.dumps(s,indent=2,default=str)
	
	st.download_button(
	    "⬇️ Download Complete Season JSON",
	    export,
	    file_name=f"LCT_Season_{s['season']}_{s['run_seed']}.json",
	    mime="application/json"
	)
	
	st.caption(
	    "The JSON export contains the current simulation state, "
	    "completed results, standings and tournament progression."
	)         

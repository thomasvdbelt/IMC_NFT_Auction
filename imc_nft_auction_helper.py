# imc_nft_auction_helper.py
"""
IMC NFT Auction Assistant – v6
Preference‑score allocation model
---------------------------------
* Utility = ΔScore·Scarcity + NeedBonus + GoldBonus + BlockBonus
* Cash slice = Utility / (Utility + best‑alternative utilities) × free budget
* MaxBid never exceeds budget and always leaves $1 per still‑missing mandatory token
"""

import streamlit as st
import pandas as pd
import numpy as np

# ---------- LOAD DATA ----------------------------------------------------
@st.cache_data
def load_tokens():
    df = pd.read_excel('NFT_Auction_Data.xlsx')
    if 'Total Score' not in df.columns:
        cols=[c for c in df.columns if 'Rarity' in c and 'Total' not in c]
        df['Total Score']=(1/df[cols]).sum(axis=1)
    return df

df = load_tokens()
ALL_GOLD=set(df[df['Fur']=='Solid Gold']['id'])
Q90 = df['Total Score'].quantile(0.9)
PTS_PER_DOLLAR = Q90/20   # heuristic anchor (90th‑pct token ≈ $20)

MANDATORY_BGS=["Blue","Aquamarine","Yellow"]

# ---------- SESSION STATE -----------------------------------------------
S=st.session_state
if 'players' not in S: S.players={"Player 1":{"budget":50,"tokens":[]}}
if 'num_players' not in S: S.num_players=2
if 'sold' not in S: S.sold=set()

# ---------- HELPERS ------------------------------------------------------

def rem_df():
    return df[~df['id'].isin(S.sold)]

def tokens_of(p):
    return df[df['id'].isin(S.players[p]['tokens'])]

def has_gold(p):
    return any(t in ALL_GOLD for t in S.players[p]['tokens'])

def missing_bgs(p):
    owned=set(tokens_of(p)['Background'])
    return [bg for bg in MANDATORY_BGS if bg not in owned]

# ---------- SIDEBAR CONFIG ----------------------------------------------
with st.sidebar:
    st.header("Game setup")
    S.num_players=int(st.number_input("Players incl. you",2,20, S.num_players))
    for i in range(1,S.num_players+1):
        S.players.setdefault(f"Player {i}",{"budget":50,"tokens":[]})

    st.header("Utility weights")
    w_need_bg   = st.slider("Need bonus (background)",  0,500,200,50)
    w_need_gold = st.slider("Need bonus (gold)",        0,600,250,50)
    w_block     = st.slider("Block bonus (per rival)",  0,200, 50,10)
    scar_scale  = st.slider("Scarcity scale",0.0,3.0,1.0,0.1)
    up_mult     = st.slider("Upgrade multiplier",0.0,3.0,1.5,0.1)

# ---------- SCARCITY PRECOMPUTE -----------------------------------------
REM = rem_df()
BG_SUPPLY=REM['Background'].value_counts().to_dict()
GOLD_SUPPLY=len(REM[REM['Fur']=='Solid Gold']) or 1

# ---------- UTILITY FUNCTION --------------------------------------------

def scarcity(row):
    if row['Fur']=='Solid Gold':
        demand=sum(1 for p in S.players if not has_gold(p))
        return 1+scar_scale*demand/GOLD_SUPPLY
    col=row['Background']; demand=sum(1 for p in S.players if col in missing_bgs(p))
    supply=BG_SUPPLY.get(col,1)
    return 1+scar_scale*demand/supply


def delta_score(row, player):
    cur=tokens_of(player)
    old=cur[cur['Background']==row['Background']]['Total Score'].max() if not cur.empty else 0
    return max(row['Total Score']-old,0)


def preference(row, player):
    util=delta_score(row,player)*scarcity(row)*up_mult
    if row['Fur']=='Solid Gold' and not has_gold(player):
        util+=w_need_gold
    if row['Background'] in missing_bgs(player):
        util+=w_need_bg
    # block rivals
    rivals_missing=sum(1 for r in S.players if r!=player and (
        (row['Fur']=='Solid Gold' and not has_gold(r)) or
        (row['Background'] in missing_bgs(r)) ))
    util+=w_block*rivals_missing
    return util

# ---------- BID CALC -----------------------------------------------------

def max_bid(row, player):
    budget=S.players[player]['budget']
    if budget<=0: return 0.0

    util_this=preference(row,player)
    # estimate best util per still-missing requirement (excluding this token)
    missing=list(missing_bgs(player))
    if row['Background'] in missing: missing.remove(row['Background'])
    if row['Fur']=='Solid Gold' and not has_gold(player): need_gold=False
    else: need_gold = not has_gold(player)

    alt_utils=[]
    rem=REM if row['id'] in REM['id'].values else pd.concat([REM,row.to_frame().T])
    if need_gold:
        alt_utils.append(rem[rem['Fur']=='Solid Gold']['Total Score'].apply(lambda x:0).max()+w_need_gold)  # fallback util for gold if none remain
    for bg in missing:
        cand=rem[rem['Background']==bg]
        if not cand.empty:
            best_row=cand.iloc[cand['Total Score'].idxmax()]
            alt_utils.append(preference(best_row,player))
    util_total=util_this+sum(alt_utils)
    free_cash=budget-len(missing_bgs(player))*1-(0 if has_gold(player) else 1)  # leave $1 per pending mandatory
    free_cash=max(free_cash,0)
    cash_alloc=free_cash*util_this/ util_total if util_total>0 else 0
    cash_by_score=row['Total Score']/PTS_PER_DOLLAR
    return round(min(cash_alloc,cash_by_score,budget),1)

# cache bid matrix
@st.cache_data
def build_bids(ids_tuple, players_tuple):
    sub=df[df['id'].isin(ids_tuple)].reset_index(drop=True)
    out=sub[['id','Background','Fur','Total Score']].copy()
    for p in players_tuple:
        out[p]=[max_bid(r,p) for _,r in sub.iterrows()]
    return out

# ---------- UI -----------------------------------------------------------
auct_tab, browse_tab = st.tabs(["Auction","Remaining tokens"])

with auct_tab:
    st.title("Auction")
    tid=st.text_input("Token ID on block")
    if tid:
        try:
            tid=int(tid)
            token=df[df['id']==tid].iloc[0]
            st.json(token[['Background','Fur','Total Score']].to_dict())
            bids=build_bids((tid,),tuple(S.players.keys()))
            st.dataframe(bids.set_index('id'))
        except: st.error("Invalid id")
    st.divider()
    with st.form("log"):
        sold=st.text_input("Sold id")
        buyer=st.selectbox("Buyer", list(S.players.keys()))
        price=st.number_input("Price",1,50,1)
        if st.form_submit_button("Record"):
            try:
                sid=int(sold)
                if sid in S.sold: st.warning("Already logged")
                else:
                    S.sold.add(sid)
                    S.players[buyer]['tokens'].append(sid)
                    S.players[buyer]['budget']-=price
                    st.success("Logged")
            except: st.error("Bad id")
    st.divider()
    matrix=pd.DataFrame([{**{"Player":p,"Budget":d['budget']},
                          **{bg:("✅" if bg not in missing_bgs(p) else "❌") for bg in MANDATORY_BGS},
                          **{"Gold":"✅" if has_gold(p) else "❌"}}
                         for p,d in S.players.items()])
    st.dataframe(matrix.set_index('Player'))

with browse_tab:
    st.title("Remaining tokens")
    filtered=REM.sort_values('Total Score',ascending=False)
    st.dataframe(filtered[['id','Background','Fur','Total Score']])

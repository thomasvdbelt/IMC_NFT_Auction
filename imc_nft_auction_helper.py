# imc_nft_auction_helper.py
"""Streamlit dashboard – IMC NFT Auction Game (v3)
Now with:
• Separate Nomination tab
• Scarcity‑aware fair values
• Edge‑ranking nomination list
• Top‑rarity tracker with colour‑coded availability
• Matrix‑style player overview
"""

import streamlit as st
import pandas as pd
import numpy as np

# ---- CONFIG -------------------------------------------------------------
STARTING_BUDGET = 50
BACKGROUND_COLORS = ["Blue", "Aquamarine", "Yellow"]
GOLD_FUR_VALUE_BOOST = 1.5
MISSING_BACKGROUND_BOOST = 0.8
UPGRADE_BACKGROUND_BOOST = 0.3
SCARCITY_SCALE = 1.2
UNIQUENESS_SCALE = 0.4
SAFETY_CASH_BUFFER = 2
# ------------------------------------------------------------------------

@st.cache_data
def load_data():
    df = pd.read_excel('NFT_Auction_Data.xlsx')
    if 'Total Score' not in df.columns:
        rarity_cols = [c for c in df.columns if 'Rarity' in c and 'Total' not in c]
        df['Total Score'] = (1 / df[rarity_cols]).sum(axis=1)
    return df

df = load_data()
ALL_GOLD_IDS = set(df[df['Fur'] == 'Solid Gold']['id'])

# ---- SESSION STATE ------------------------------------------------------
s = st.session_state
if 'players' not in s:
    s.players = {"Player 1": {"budget": STARTING_BUDGET, "tokens": []}}
if 'num_players' not in s:
    s.num_players = 2
if 'auctioned_ids' not in s:
    s.auctioned_ids = set()

# ---- UTILS --------------------------------------------------------------

def remaining_df():
    return df[~df['id'].isin(s.auctioned_ids)]

def tokens_of(p):
    return df[df['id'].isin(s.players[p]['tokens'])]

def has_gold(p):
    return not tokens_of(p)[tokens_of(p)['Fur'] == 'Solid Gold'].empty

def missing_bg(p):
    return [c for c in BACKGROUND_COLORS if c not in set(tokens_of(p)['Background'])]

# Fair value helpers ------------------------------------------------------

def scarcity_mult(row):
    rem = remaining_df()
    if row['Fur'] == 'Solid Gold':
        demand = sum(1 for p in s.players if not has_gold(p))
        supply = len(rem[rem['Fur'] == 'Solid Gold']) or 1
    else:
        col = row['Background']
        demand = sum(1 for p in s.players if col in missing_bg(p))
        supply = len(rem[rem['Background'] == col]) or 1
    return 1 + SCARCITY_SCALE * (demand / supply)

def uniqueness_bonus(row):
    same_bg = remaining_df()[remaining_df()['Background'] == row['Background']]
    if same_bg.empty:
        return UNIQUENESS_SCALE
    top = same_bg['Total Score'].nlargest(2).tolist()
    if len(top) < 2:
        return UNIQUENESS_SCALE
    gap = (top[0]-top[1])/(top[0]+1e-6)
    return UNIQUENESS_SCALE * gap

def upgrade_gain(row):
    cur = tokens_of('Player 1')
    cur_best = cur[cur['Background']==row['Background']]['Total Score'].max() if not cur.empty else 0
    return max(row['Total Score']-cur_best,0)

def value_token(row):
    bg_need = row['Background'] in missing_bg('Player 1')
    gold_need = not has_gold('Player 1')
    if row['Fur']=='Solid Gold':
        base = row['Total Score'] * (GOLD_FUR_VALUE_BOOST if gold_need else 1)
    elif bg_need:
        base = row['Total Score'] * (1+MISSING_BACKGROUND_BOOST)
    else:
        base = upgrade_gain(row)
    v = base * scarcity_mult(row) + uniqueness_bonus(row) * row['Total Score']
    return round(v,1)

def bid_ceiling(row):
    return min(value_token(row), s.players['Player 1']['budget']-SAFETY_CASH_BUFFER)

# Nomination edge ---------------------------------------------------------

def rival_val(row,r):
    if row['Fur']=='Solid Gold':
        return row['Total Score']*GOLD_FUR_VALUE_BOOST if not has_gold(r) else 0
    if row['Background'] in missing_bg(r):
        return row['Total Score']*(1+MISSING_BACKGROUND_BOOST)
    return 0

def edge_score(row):
    myv = value_token(row)
    top_rival = max([rival_val(row,p) for p in s.players if p!='Player 1'] or [0])
    richest = max([s.players[p]['budget'] for p in s.players if p!='Player 1'] or [0])
    edge = myv - top_rival + 0.1*(s.players['Player 1']['budget']-richest)
    return edge,myv,top_rival

# ---- SIDEBAR SETUP ------------------------------------------------------
st.sidebar.header("🎯 Setup")
num_in = st.sidebar.number_input("Players incl. you",2,20,max(s.num_players,2),1)
s.num_players=int(num_in)
for i in range(1,s.num_players+1):
    k=f"Player {i}"
    if k not in s.players:
        s.players[k]={'budget':STARTING_BUDGET,'tokens':[]}

# ---- TABS ---------------------------------------------------------------
main_tab, nom_tab = st.tabs(["Auction", "Nomination Helper"])

# ============  AUCTION TAB  ============
with main_tab:
    st.title("💰 Live Auction")
    colA,colB = st.columns(2)
    with colA:
        st.subheader("Current Token")
        tid = st.text_input("ID on the block")
        if tid:
            try:
                tid=int(tid)
                tok=df[df['id']==tid].iloc[0]
                st.json(tok[['Background','Fur','Total Score']].to_dict())
                st.metric("Fair value",f"${value_token(tok):.1f}")
                st.metric("Bid ceiling",f"${bid_ceiling(tok):.1f}")
            except Exception:
                st.error("Bad ID")
    with colB:
        st.subheader("Log sale")
        with st.form("sale"):
            sold = st.text_input("Sold token id")
            buyer = st.selectbox("Buyer",list(s.players.keys()))
            price = st.number_input("Price",1,STARTING_BUDGET,1)
            if st.form_submit_button("Add"):
                try:
                    sid=int(sold)
                    if sid in s.auctioned_ids:
                        st.warning("Already logged")
                    else:
                        s.auctioned_ids.add(sid)
                        s.players[buyer]['tokens'].append(sid)
                        s.players[buyer]['budget']-=price
                        st.success("Recorded")
                except:
                    st.error("Bad id")
    st.divider()
    st.subheader("Player Matrix")
    matrix=pd.DataFrame([{**{"Player":p,"Budget":d['budget']},
                          **{bg:("✅" if bg not in missing_bg(p) else "❌") for bg in BACKGROUND_COLORS},
                          **{"Gold":"✅" if has_gold(p) else "❌"}}
                         for p,d in s.players.items()])
    st.dataframe(matrix.set_index('Player'))

# ============  NOMINATION TAB  ============
with nom_tab:
    st.title("🎯 Nomination Helper")
    rem=remaining_df().copy()
    rem[['Edge','MyVal','TopRival']]=rem.apply(edge_score,axis=1,result_type='expand')
    st.subheader("Smart nominations (Edge ranking)")
    st.dataframe(rem.sort_values('Edge',ascending=False).head(20)[['id','Background','Fur','Total Score','Edge','MyVal','TopRival']])

    st.subheader("Top rarity tokens by category")
    # Build table of top 15 for each bg + gold
    pieces=[]
    for bg in BACKGROUND_COLORS:
        top=df[df['Background']==bg].nlargest(15,'Total Score')[[
            'id','Total Score']].copy()
        top['Category']=bg
        pieces.append(top)
    gold_top=df[df['Fur']=='Solid Gold'].nlargest(15,'Total Score')[['id','Total Score']]
    gold_top['Category']='Gold'
    pieces.append(gold_top)
    catdf=pd.concat(pieces)
    catdf['Status']=catdf['id'].apply(lambda x:'🟥 Gone' if x in s.auctioned_ids else '🟩 Left')
    st.dataframe(catdf[['Category','id','Total Score','Status']])

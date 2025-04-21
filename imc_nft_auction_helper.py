# imc_nft_auction_helper.py
"""
IMC NFT Auction Assistant – v4
Key changes
------------
• Faster load (aggressive caching, no per‑row apply where possible)
• Per‑player bid table shown whenever you type a token ID
• New bid logic  =  needs_weight × score  BUT never > player budget
• Edge =  myMaxBid – bestRivalMaxBid  (no safety buffer)
• Nomination tab redesign → 4 boxes (Gold + three backgrounds) side‑by‑side, each listing top‑15 with 🟥/🟩 status
"""

import streamlit as st
import pandas as pd
import numpy as np

# ---- CONFIG -------------------------------------------------------------
STARTING_BUDGET = 50
REQUIRED_BGS = ["Blue", "Aquamarine", "Yellow"]
NEED_WEIGHT_BG = 1.0      # multiplier if player missing this background
NEED_WEIGHT_GOLD = 1.3    # multiplier if player missing gold
UPGRADE_WEIGHT = 0.4       # if player has bg but token upgrades score
SCARCITY_SCALE = 1.0
UNIQUENESS_SCALE = 0.3
# ------------------------------------------------------------------------

@st.cache_data
def load_data():
    df = pd.read_excel('NFT_Auction_Data.xlsx')
    if 'Total Score' not in df.columns:
        rc = [c for c in df.columns if 'Rarity' in c and 'Total' not in c]
        df['Total Score'] = (1 / df[rc]).sum(axis=1)
    return df

df = load_data()

ALL_GOLD_IDS = set(df[df['Fur']=='Solid Gold']['id'])

# ---- SESSION STATE ------------------------------------------------------
S = st.session_state
if 'players' not in S:
    S.players = {"Player 1": {"budget": STARTING_BUDGET, "tokens": []}}
if 'num_players' not in S: S.num_players = 2
if 'auctioned_ids' not in S: S.auctioned_ids = set()

# ---- QUICK HELPERS ------------------------------------------------------

def remaining_df():
    return df[~df['id'].isin(S.auctioned_ids)]

def tokens_of(p):
    return df[df['id'].isin(S.players[p]['tokens'])]

def has_gold(p):
    return any(t in ALL_GOLD_IDS for t in S.players[p]['tokens'])

def missing_bgs(p):
    owned = set(tokens_of(p)['Background'])
    return [bg for bg in REQUIRED_BGS if bg not in owned]

# pre‑compute scarcity counts once per rerun
REM = remaining_df()
BG_SUPPLY = REM['Background'].value_counts().to_dict()
GOLD_SUPPLY = len(REM[REM['Fur']=='Solid Gold']) or 1

def scarcity_factor(row):
    if row['Fur']=='Solid Gold':
        demand = sum(1 for p in S.players if not has_gold(p))
        return 1 + SCARCITY_SCALE * demand / GOLD_SUPPLY
    col=row['Background']
    demand = sum(1 for p in S.players if col in missing_bgs(p))
    supply = BG_SUPPLY.get(col,1)
    return 1 + SCARCITY_SCALE * demand / supply

# ----------------  BIDDING LOGIC  ---------------------------------------

def theoretical_bid(row, player):
    budget = S.players[player]['budget']
    if budget<=0: return 0
    if row['Fur']=='Solid Gold':
        weight = NEED_WEIGHT_GOLD if not has_gold(player) else 0
    elif row['Background'] in missing_bgs(player):
        weight = NEED_WEIGHT_BG
    else:
        # upgrade value proportional to gap
        cur = tokens_of(player)
        old = cur[cur['Background']==row['Background']]['Total Score'].max() if not cur.empty else 0
        gain = row['Total Score']-old
        weight = UPGRADE_WEIGHT * gain/ (row['Total Score']+1e-6)
    base = row['Total Score']*weight*scarcity_factor(row)
    return round(min(base, budget),1)

# Pre‑vectorise player bids for speed
@st.cache_data
def build_bid_matrix(ids_tuple, players_tuple):
    sub=df[df['id'].isin(ids_tuple)].copy()
    bids={p:[theoretical_bid(r,p) for _,r in sub.iterrows()] for p in players_tuple}
    out=sub[['id','Background','Fur','Total Score']].reset_index(drop=True)
    for p,v in bids.items(): out[p]=v
    return out

# ---- SIDEBAR SETUP ------------------------------------------------------
st.sidebar.header("Setup")
num = st.sidebar.number_input("Players incl. you",2,20,max(S.num_players,2))
S.num_players=int(num)
for i in range(1,S.num_players+1):
    k=f"Player {i}"; S.players.setdefault(k,{"budget":STARTING_BUDGET,"tokens":[]})

# ---- TABS ---------------------------------------------------------------
main_tab, nom_tab = st.tabs(["Auction", "Nomination Helper"])

# ====================  AUCTION  ====================
with main_tab:
    st.title("Live Auction")
    col1,col2=st.columns(2)
    with col1:
        tok_id=st.text_input("Token ID on the block")
        if tok_id:
            try:
                tid=int(tok_id); row=df[df['id']==tid].iloc[0]
                st.write(row[['Background','Fur','Total Score']])
                # Build bid matrix for this single id
                bid_df=build_bid_matrix((tid,), tuple(S.players.keys()))
                my_max=bid_df['Player 1'][0]
                rival_max=bid_df[[p for p in S.players if p!='Player 1']].max(axis=1)[0]
                st.metric("Your max bid",f"${my_max}")
                st.metric("Highest rival max",f"${rival_max}")
                st.metric("Edge",f"${my_max-rival_max}")
                st.dataframe(bid_df.set_index('id'))
            except: st.error("Bad id")
    with col2:
        with st.form("sale"):
            s_id=st.text_input("Sold id")
            buyer=st.selectbox("Buyer",list(S.players.keys()))
            price=st.number_input("Price",1,STARTING_BUDGET,1)
            if st.form_submit_button("Log"):
                try:
                    sid=int(s_id)
                    if sid in S.auctioned_ids: st.warning("Already logged")
                    else:
                        S.auctioned_ids.add(sid)
                        S.players[buyer]['tokens'].append(sid)
                        S.players[buyer]['budget']-=price
                        st.success("Logged")
                except: st.error("Bad id")
    st.divider()
    st.subheader("Player matrix")
    matrix=pd.DataFrame([{**{"Player":p,"Budget":d['budget']},
                          **{bg:("✅" if bg not in missing_bgs(p) else "❌") for bg in REQUIRED_BGS},
                          **{"Gold":"✅" if has_gold(p) else "❌"}}
                         for p,d in S.players.items()])
    st.dataframe(matrix.set_index('Player'))

# ==================== NOMINATION TAB ====================
with nom_tab:
    st.title("Nomination Helper")
    players_tuple=tuple(S.players.keys())
    bid_matrix=build_bid_matrix(tuple(REM['id']), players_tuple)
    bid_matrix['Edge']=bid_matrix['Player 1']-bid_matrix[[p for p in players_tuple if p!='Player 1']].max(axis=1)
    st.subheader("Best Edge tokens (top 20)")
    st.dataframe(bid_matrix.sort_values('Edge',ascending=False).head(20))

    st.subheader("Top rarity tokens by category")
    cols=st.columns(4)
    def top_table(cat_df):
        cat_df['Status']=cat_df['id'].apply(lambda x:'🟥' if x in S.auctioned_ids else '🟩')
        return cat_df[['id','Total Score','Status']]
    # Gold
    with cols[0]:
        st.markdown("**Gold**")
        st.dataframe(top_table(df[df['Fur']=='Solid Gold'].nlargest(15,'Total Score')))
    # Backgrounds
    for i,bg in enumerate(REQUIRED_BGS,1):
        with cols[i]:
            st.markdown(f"**{bg}**")
            st.dataframe(top_table(df[df['Background']==bg].nlargest(15,'Total Score')))

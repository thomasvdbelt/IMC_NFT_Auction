# imc_nft_auction_helper.py
"""Streamlit dashboard to assist with IMC NFT Auction Game.
Tracks auction state, player holdings, and computes strategic fair value and nomination edges.
"""

import streamlit as st
import pandas as pd
import numpy as np

# ---- CONFIG -------------------------------------------------------------
STARTING_BUDGET = 50
BACKGROUND_COLORS = ["Blue", "Aquamarine", "Yellow"]
GOLD_FUR_VALUE_BOOST = 1.5  # base boost when player lacks gold
MISSING_BACKGROUND_BOOST = 0.8
UPGRADE_BACKGROUND_BOOST = 0.3
SCARCITY_SCALE = 1.2        # scales demand‑vs‑supply weight
UNIQUENESS_SCALE = 0.4      # how much uniqueness among top scores matters
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

# ---- HELPER UTILS -------------------------------------------------------

def remaining_df():
    return df[~df['id'].isin(s.auctioned_ids)]

def tokens_of(player):
    return df[df['id'].isin(s.players[player]['tokens'])]

def has_gold(player):
    return not tokens_of(player)[tokens_of(player)['Fur'] == 'Solid Gold'].empty

def missing_backgrounds(player):
    owned_bg = set(tokens_of(player)['Background'])
    return [c for c in BACKGROUND_COLORS if c not in owned_bg]

# ---- STRATEGIC FAIR VALUE ----------------------------------------------

def scarcity_multiplier(token_row):
    """Demand / supply factor (>=1)."""
    rem = remaining_df()
    demand = 0
    supply = 0
    # Gold scarcity
    if token_row['Fur'] == 'Solid Gold':
        demand = sum(1 for p in s.players if not has_gold(p))
        supply = len(rem[rem['Fur'] == 'Solid Gold'])
    else:
        color = token_row['Background']
        demand = sum(1 for p in s.players if color in missing_backgrounds(p))
        supply = len(rem[rem['Background'] == color])
    supply = max(supply, 1)  # avoid div/0
    return 1 + SCARCITY_SCALE * (demand / supply)


def uniqueness_bonus(token_row):
    """Boost if this token is far better than the second‑best remaining in same bg."""
    same_bg = remaining_df()[remaining_df()['Background'] == token_row['Background']]
    if same_bg.empty:
        return 0
    top_scores = same_bg['Total Score'].nlargest(2).tolist()
    if len(top_scores) < 2:
        return UNIQUENESS_SCALE  # only one left
    gap = top_scores[0] - top_scores[1]
    norm_gap = gap / (top_scores[0] + 1e-6)
    return UNIQUENESS_SCALE * norm_gap


def marginal_upgrade(token_row):
    """Score gain this token delivers over current best in its background."""
    current_best = tokens_of('Player 1')
    current_best = current_best[current_best['Background'] == token_row['Background']]['Total Score'].max() if not current_best.empty else 0
    return max(token_row['Total Score'] - current_best, 0)


def value_token(token_row):
    base = token_row['Total Score']
    bg_missing = token_row['Background'] in missing_backgrounds('Player 1')
    gold_missing = not has_gold('Player 1')
    v = 0
    if token_row['Fur'] == 'Solid Gold':
        # Completion value dominates
        v = base * GOLD_FUR_VALUE_BOOST if gold_missing else marginal_upgrade(token_row)
    elif bg_missing:
        v = base * (1 + MISSING_BACKGROUND_BOOST)
    else:
        v = marginal_upgrade(token_row)
    # Scarcity & uniqueness
    v *= scarcity_multiplier(token_row)
    v += uniqueness_bonus(token_row) * base
    return round(v, 1)

# ---- BID CEILING --------------------------------------------------------

def suggested_bid(token_row):
    my_val = value_token(token_row)
    max_afford = s.players['Player 1']['budget'] - SAFETY_CASH_BUFFER
    return min(my_val, max_afford)

# ---- NOMINATION EDGE ----------------------------------------------------

def rival_value(token_row, rival):
    """Crude rival valuation: treat them like us but w.r.t their needs only."""
    bg_missing = token_row['Background'] in missing_backgrounds(rival)
    rival_gold_missing = not has_gold(rival)
    if token_row['Fur'] == 'Solid Gold':
        if rival_gold_missing:
            return token_row['Total Score'] * GOLD_FUR_VALUE_BOOST
        return 0
    if bg_missing:
        return token_row['Total Score'] * (1 + MISSING_BACKGROUND_BOOST)
    return 0  # assume rivals don't pay just for upgrades (simplification)


def nomination_edge(token_row):
    my_val = value_token(token_row)
    rival_vals = [rival_value(token_row, p) for p in s.players if p != 'Player 1']
    highest_rival = max(rival_vals) if rival_vals else 0
    budget_block = max(0, s.players['Player 1']['budget'] - max((s.players[p]['budget'] for p in s.players if p != 'Player 1'), default=0))
    edge_score = my_val - highest_rival + 0.1 * budget_block
    return edge_score, my_val, highest_rival

# ---- SIDEBAR: GAME SETUP -----------------------------------------------
st.sidebar.header("🎯 Game Setup")
num_players_input = st.sidebar.number_input("Total players (incl. you)", 2, 20, max(s.num_players,2), 1)
s.num_players = int(num_players_input)
for i in range(1, s.num_players+1):
    key = f"Player {i}"
    if key not in s.players:
        s.players[key] = {"budget": STARTING_BUDGET, "tokens": []}

# ---- MAIN PAGE ---------------------------------------------------------
st.title("💰 IMC NFT Auction Assistant – v2")

col1, col2 = st.columns(2)
with col1:
    st.subheader("🧩 Current Auction")
    current_id = st.text_input("Token id being auctioned", value="")
    if current_id:
        try:
            cid = int(current_id)
            token_row = df[df['id']==cid].iloc[0]
            st.write(token_row[['Background','Fur','Total Score']])
            st.markdown(f"**Fair value (you): ${value_token(token_row):.1f}**")
            st.markdown(f"**Bid ceiling:** ${suggested_bid(token_row):.1f}")
        except Exception:
            st.error("Invalid id")
with col2:
    st.subheader("📦 Log a Sale")
    with st.form("sale"):
        sold_id = st.text_input("Sold token id")
        buyer = st.selectbox("Buyer", list(s.players.keys()))
        price = st.number_input("Price",1, STARTING_BUDGET,1)
        if st.form_submit_button("Log"):
            try:
                sid = int(sold_id)
                if sid in s.auctioned_ids:
                    st.warning("Already logged")
                else:
                    s.auctioned_ids.add(sid)
                    s.players[buyer]['tokens'].append(sid)
                    s.players[buyer]['budget'] -= price
                    st.success("Logged!")
            except:
                st.error("Bad id")

st.divider()

# ---- NOMINATION RECOMMENDER TAB ---------------------------------------
with st.expander("💡 Smart Nomination Suggestions", expanded=False):
    rem = remaining_df().copy()
    edges = rem.apply(nomination_edge, axis=1, result_type='expand')
    rem[['Edge','MyVal','TopRival']] = edges
    top_nom = rem.sort_values('Edge', ascending=False).head(20)[['id','Background','Fur','Total Score','Edge','MyVal','TopRival']]
    st.dataframe(top_nom)

st.divider()
st.subheader("📊 Player Overview")
for player, data in s.players.items():
    st.markdown(f"### {player} — 💵 ${data['budget']}")
    st.markdown(f"Needs: {', '.join(missing_backgrounds(player)) or 'None'} | Gold: {'✅' if has_gold(player) else '❌'}")
    if data['tokens']:
        st.dataframe(df[df['id'].isin(data['tokens'])][['id','Background','Fur','Total Score']])
    else:
        st.markdown("_No tokens yet_")

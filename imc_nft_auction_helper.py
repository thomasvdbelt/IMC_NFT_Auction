# imc_nft_auction_helper.py
"""Streamlit dashboard to assist with IMC NFT Auction Game.
Tracks current auction state, player holdings, and computes fair value of tokens.

Author: ChatGPT (improved iteratively with Thomas)
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
SCARCITY_BOOST_SCALE = 0.5
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
TOTAL_COUNTS = df['id'].count()
initial_bg_counts = df['Background'].value_counts().to_dict()

# ---- SESSION STATE INITIALISATION --------------------------------------
if 'my_budget' not in st.session_state:
    st.session_state.my_budget = STARTING_BUDGET
if 'my_tokens' not in st.session_state:
    st.session_state.my_tokens = []
if 'auctioned_ids' not in st.session_state:
    st.session_state.auctioned_ids = set()
if 'players' not in st.session_state:
    st.session_state.players = {"Player 1": {"budget": STARTING_BUDGET, "tokens": []}}
if 'num_players' not in st.session_state:
    st.session_state.num_players = 2  # FIXED: now matches min_value

# ---- HELPER FUNCTIONS ---------------------------------------------------
def remaining_df():
    return df[~df['id'].isin(st.session_state.auctioned_ids)]

def collection_df(player):
    ids = st.session_state.players[player]["tokens"]
    return df[df['id'].isin(ids)]

def collection_status(player):
    owned = collection_df(player)
    backgrounds_owned = set(owned['Background'])
    has_gold = not owned[owned['Fur'] == 'Solid Gold'].empty
    missing_bg = [c for c in BACKGROUND_COLORS if c not in backgrounds_owned]
    return backgrounds_owned, missing_bg, has_gold

def value_token(token_row):
    base = token_row['Total Score']
    backgrounds_owned, missing_bg, has_gold = collection_status("Player 1")
    multiplier = 1.0
    if token_row['Fur'] == 'Solid Gold':
        multiplier += GOLD_FUR_VALUE_BOOST if not has_gold else 0.2
    if token_row['Background'] in missing_bg:
        multiplier += MISSING_BACKGROUND_BOOST
    else:
        current_best = collection_df("Player 1")
        current_best = current_best[current_best['Background'] == token_row['Background']]['Total Score'].max() if not current_best.empty else 0
        if token_row['Total Score'] > current_best:
            multiplier += UPGRADE_BACKGROUND_BOOST
    remaining_bg_count = remaining_df()['Background'].value_counts().to_dict().get(token_row['Background'], 0)
    scarcity_factor = (1 - remaining_bg_count / initial_bg_counts[token_row['Background']])
    multiplier += scarcity_factor * SCARCITY_BOOST_SCALE
    return base * multiplier

# ---- SIDEBAR: GAME SETUP & TRACKING -------------------------------------
st.sidebar.header("🎯 Game Setup")

# Get number of players safely without crashing
num_players_input = st.sidebar.number_input(
    "Total players (incl. you)",
    min_value=2,
    max_value=20,
    value=max(st.session_state.get("num_players", 2), 2),  # always at least 2
    step=1
)
st.session_state.num_players = num_players_input


# Initialize missing players
for i in range(1, st.session_state.num_players + 1):
    player_key = f"Player {i}"
    if player_key not in st.session_state.players:
        st.session_state.players[player_key] = {"budget": STARTING_BUDGET, "tokens": []}

# ---- MAIN INTERFACE ------------------------------------------------------
st.title("💰 IMC NFT Auction Assistant")

st.subheader("🧩 Current Auction")
current_id = st.text_input("Current token id being auctioned", value="")
if current_id:
    try:
        cid = int(current_id)
        token_row = df[df['id'] == cid].iloc[0]
        val = value_token(token_row)
        st.success(f"🎯 Fair value estimate (you): ${val:.1f}")
        st.json(token_row[['Background', 'Fur', 'Total Score']].to_dict())
    except:
        st.error("Invalid token id.")

st.divider()
st.subheader("📦 Log a Sale")
with st.form("log_sale"):
    sold_token_id = st.text_input("Token id that was sold")
    buyer = st.selectbox("Buyer", options=list(st.session_state.players.keys()))
    price = st.number_input("Final price", min_value=1, max_value=STARTING_BUDGET, value=1)
    submitted = st.form_submit_button("Log Sale")
    if submitted:
        try:
            tid = int(sold_token_id)
            if tid in st.session_state.auctioned_ids:
                st.warning("Already sold.")
            else:
                st.session_state.auctioned_ids.add(tid)
                st.session_state.players[buyer]['tokens'].append(tid)
                st.session_state.players[buyer]['budget'] -= price
                st.success(f"Logged: Token {tid} bought by {buyer} for ${price}")
        except:
            st.error("Invalid token id.")

st.divider()
st.subheader("📊 Player Overview")
for player, data in st.session_state.players.items():
    st.markdown(f"**{player}** — Budget: ${data['budget']}")
    if data['tokens']:
        tokens_df = df[df['id'].isin(data['tokens'])][['id', 'Background', 'Fur', 'Total Score']]
        st.dataframe(tokens_df)
    else:
        st.markdown("_No tokens yet._")

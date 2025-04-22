# imc_nft_auction_helper.py
"""
Streamlit dashboard for IMC NFT Auction Game
Focus: Clear bidding logic, token utility scoring, dynamic dashboard
Author: ChatGPT (Aaron Edition)
"""

import streamlit as st
import pandas as pd
import numpy as np

# =============== CONFIGURATION ===============
STARTING_BUDGET = 50
MANDATORY_BACKGROUNDS = ["Blue", "Aquamarine", "Yellow"]

# Utility weight defaults
DEFAULT_NEED_BG = 10
DEFAULT_NEED_GOLD = 15
DEFAULT_BLOCK = 5
DEFAULT_SCARCITY = 1.0
UPGRADE_MULTIPLIER = 1.5

# =============== LOAD DATA ===============
@st.cache_data
def load_data():
    df = pd.read_excel("NFT_Auction_Data.xlsx")
    if "Total Score" not in df.columns:
        cols = [c for c in df.columns if "Rarity" in c and "Total" not in c]
        df["Total Score"] = (1 / df[cols]).sum(axis=1)
    return df

df = load_data()
ALL_GOLD = set(df[df['Fur'] == 'Solid Gold']['id'])
REQUIRED = MANDATORY_BACKGROUNDS + ['Gold']

# =============== SESSION STATE ===============
S = st.session_state
if "players" not in S:
    S.players = {"Player 1": {"budget": STARTING_BUDGET, "tokens": []}}
if "num_players" not in S:
    S.num_players = 13
if "auctioned_ids" not in S:
    S.auctioned_ids = set()

# =============== UTILITY FUNCTIONS ===============
def remaining_df():
    return df[~df['id'].isin(S.auctioned_ids)]

def tokens_of(player):
    return df[df['id'].isin(S.players[player]['tokens'])]

def has_gold(player):
    return any(t in ALL_GOLD for t in S.players[player]['tokens'])

def missing_bgs(player):
    owned = set(tokens_of(player)['Background'])
    return [bg for bg in MANDATORY_BACKGROUNDS if bg not in owned]

def player_status(player):
    return {
        "Budget": S.players[player]['budget'],
        "Gold": "✅" if has_gold(player) else "❌",
        **{bg: "✅" if bg not in missing_bgs(player) else "❌" for bg in MANDATORY_BACKGROUNDS}
    }

# =============== PREFERENCE SCORING ===============
def scarcity_factors():
    rem = remaining_df()
    bg_counts = rem['Background'].value_counts().to_dict()
    gold_remain = len(rem[rem['Fur'] == 'Solid Gold']) or 1
    return bg_counts, gold_remain


def utility_score(row, player, w_bg, w_gold, w_block, w_scarcity):
    cur_tokens = tokens_of(player)
    owned_bgs = set(cur_tokens['Background'])
    has_gold_fur = has_gold(player)
    delta_score = 0

    # Upgrade value
    old = cur_tokens[cur_tokens['Background'] == row['Background']]['Total Score'].max() if not cur_tokens.empty else 0
    delta_score = max(row['Total Score'] - old, 0)

    # Need bonuses
    util = delta_score * UPGRADE_MULTIPLIER
    if row['Background'] in MANDATORY_BACKGROUNDS and row['Background'] not in owned_bgs:
        util += w_bg
    if row['Fur'] == 'Solid Gold' and not has_gold_fur:
        util += w_gold

    # Scarcity scaling
    bg_counts, gold_remain = scarcity_factors()
    demand = sum(1 for p in S.players if p != player and (
        (row['Background'] in missing_bgs(p)) or
        (row['Fur'] == 'Solid Gold' and not has_gold(p))
    ))
    supply = bg_counts.get(row['Background'], 1) if row['Fur'] != 'Solid Gold' else gold_remain
    scarcity = 1 + w_scarcity * demand / supply
    util *= scarcity

    # Block bonus
    util += w_block * demand
    return util


def calculate_bid(row, player, weights):
    budget = S.players[player]['budget']
    if budget <= 0:
        return 0.0
    u = utility_score(row, player, *weights)

    # Estimate total utility needed to finish set
    missing = missing_bgs(player)
    if row['Background'] in missing:
        missing.remove(row['Background'])
    if row['Fur'] == 'Solid Gold' and not has_gold(player):
        need_gold = False
    else:
        need_gold = not has_gold(player)

    alt_utils = []
    rem = remaining_df()
    if need_gold:
        gold_tokens = rem[rem['Fur'] == 'Solid Gold']
        if not gold_tokens.empty:
            alt_utils.append(max(utility_score(t, player, *weights) for _, t in gold_tokens.iterrows()))
        else:
            alt_utils.append(weights[1])  # fallback for no golds
    for bg in missing:
        bg_tokens = rem[rem['Background'] == bg]
        if not bg_tokens.empty:
            alt_utils.append(max(utility_score(t, player, *weights) for _, t in bg_tokens.iterrows()))
        else:
            alt_utils.append(weights[0])  # fallback for no bgs

    total_util = u + sum(alt_utils)
    safe_cash = max(budget - (1 * (len(missing) + (1 if need_gold else 0))), 0)
    bid = (u / total_util) * safe_cash if total_util > 0 else 0
    return round(min(bid, budget), 1)

# =============== SIDEBAR CONFIG ===============
st.sidebar.title("Game Setup")
S.num_players = st.sidebar.number_input("Players incl. you", 2, 20, value=S.num_players)
for i in range(1, S.num_players + 1):
    S.players.setdefault(f"Player {i}", {"budget": STARTING_BUDGET, "tokens": []})

st.sidebar.title("Utility Weights")
w_bg = st.sidebar.slider("Need bonus (background)", 0, 30, DEFAULT_NEED_BG)
w_gold = st.sidebar.slider("Need bonus (Gold fur)", 0, 30, DEFAULT_NEED_GOLD)
w_block = st.sidebar.slider("Block bonus per rival", 0, 20, DEFAULT_BLOCK)
w_scar = st.sidebar.slider("Scarcity scale", 0.0, 3.0, DEFAULT_SCARCITY)
weights = (w_bg, w_gold, w_block, w_scar)

# =============== MAIN TABS ===============
auction_tab, browse_tab = st.tabs(["🎯 Auction Mode", "📦 Token Overview"])

with auction_tab:
    st.title("Live Auction Tracker")
    token_id = st.text_input("Current Token ID")
    if token_id:
        try:
            tid = int(token_id)
            token = df[df['id'] == tid].iloc[0]
            st.subheader("Token Info")
            st.json(token[['Background', 'Fur', 'Total Score']].to_dict())
            bids = {
                p: calculate_bid(token, p, weights)
                for p in S.players
            }
            bid_df = pd.DataFrame.from_dict(bids, orient='index', columns=['Max Bid ($)'])
            st.subheader("Suggested Bids")
            st.dataframe(bid_df)
        except:
            st.warning("Invalid token ID")

    st.divider()
    with st.form("📥 Log Auction Result"):
        sid = st.text_input("Sold Token ID")
        buyer = st.selectbox("Winner", list(S.players.keys()))
        price = st.number_input("Winning Price", 1, 50, 1)
        if st.form_submit_button("Log Token"):
            try:
                sid = int(sid)
                S.auctioned_ids.add(sid)
                S.players[buyer]['tokens'].append(sid)
                S.players[buyer]['budget'] -= price
                st.success(f"Token {sid} added to {buyer} for ${price}")
            except:
                st.error("Invalid ID")

    st.divider()
    st.subheader("Player Overview")
    matrix = pd.DataFrame([{
        "Player": p,
        **player_status(p)
    } for p in S.players])
    st.dataframe(matrix.set_index("Player"))

with browse_tab:
    st.title("Remaining Tokens")
    rem = remaining_df()
    col1, col2 = st.columns(2)
    with col1:
        bgs = st.multiselect("Filter Backgrounds", options=["All"] + MANDATORY_BACKGROUNDS, default=["All"])
        if "All" not in bgs:
            rem = rem[rem['Background'].isin(bgs)]
    with col2:
        if st.checkbox("Gold Only"):
            rem = rem[rem['Fur'] == 'Solid Gold']

    st.dataframe(rem[['id', 'Background', 'Fur', 'Total Score']].sort_values('Total Score', ascending=False))

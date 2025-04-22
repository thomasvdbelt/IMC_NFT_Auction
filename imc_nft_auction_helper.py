# imc_nft_auction_helper.py
"""
Streamlit dashboard for IMC NFT Auction Game (Simplified Bidding Logic)
Focus: Budget-aware scarcity-driven utility scoring without sabotage logic
Author: ChatGPT (Aaron Edition)
"""

import streamlit as st
import pandas as pd
import numpy as np

# =============== CONFIGURATION ===============
STARTING_BUDGET = 50
MANDATORY_BACKGROUNDS = ["Blue", "Aquamarine", "Yellow"]
GOLD_BONUS_MULTIPLIER = 1.2  # <= Added parameter for user control over Gold weighting

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

# =============== SESSION STATE ===============
S = st.session_state
if "players" not in S:
    S.players = {"Player 1": {"budget": STARTING_BUDGET, "tokens": []}}
if "num_players" not in S:
    S.num_players = 13
if "auctioned_ids" not in S:
    S.auctioned_ids = set()

# =============== HELPERS ===============
def remaining_df():
    return df[~df['id'].isin(S.auctioned_ids)]

def tokens_of(player):
    return df[df['id'].isin(S.players[player]['tokens'])]

def has_gold(player):
    return any(t in ALL_GOLD for t in S.players[player]['tokens'])

def missing_bgs(player):
    owned = set(tokens_of(player)['Background'])
    return [bg for bg in MANDATORY_BACKGROUNDS if bg not in owned]

def total_score(player):
    owned = tokens_of(player)
    score = 0
    for bg in MANDATORY_BACKGROUNDS:
        score += owned[owned['Background'] == bg]['Total Score'].max() if not owned[owned['Background'] == bg].empty else 0
    if has_gold(player):
        score += owned[owned['Fur'] == 'Solid Gold']['Total Score'].max() if not owned[owned['Fur'] == 'Solid Gold'].empty else 0
    return round(score, 2)

# =============== SCARCITY TRACKING ===============
def category_scarcity():
    rem = remaining_df()
    bg_demand = {bg: 0 for bg in MANDATORY_BACKGROUNDS + ["Gold"]}
    for p in S.players:
        for bg in missing_bgs(p):
            bg_demand[bg] += 1
        if not has_gold(p):
            bg_demand["Gold"] += 1
    return bg_demand

# =============== BID LOGIC ===============
def calculate_bid(token, player):
    rem = remaining_df()
    budget = S.players[player]['budget']
    if budget <= 0:
        return 0.0

    missing = missing_bgs(player)
    needs_gold = not has_gold(player)
    slots_left = len(missing) + (1 if needs_gold else 0)

    if slots_left == 0:
        return 0.0

    # Determine whether this token helps
    bg = token['Background']
    fur = token['Fur']
    rarity = token['Total Score']

    contributes_bg = bg in missing
    contributes_gold = fur == 'Solid Gold' and needs_gold

    if not contributes_bg and not contributes_gold:
        return 0.0

    # Category scarcity tracking
    scarcity = category_scarcity()

    categories_needed = []
    total_needed_rarity = 0

    if contributes_bg:
        categories_needed.append(bg)
    if contributes_gold:
        categories_needed.append("Gold")

    for need in missing:
        top_bg = rem[rem['Background'] == need]
        top_score = top_bg['Total Score'].max() if not top_bg.empty else 0.01
        total_needed_rarity += top_score
    if needs_gold:
        golds = rem[rem['Fur'] == 'Solid Gold']
        gold_score = golds['Total Score'].max() if not golds.empty else 0.01
        total_needed_rarity += gold_score * GOLD_BONUS_MULTIPLIER

    # Calculate scarcity factor and combined score
    all_factors = []
    for cat in categories_needed:
        if cat == "Gold":
            cat_tokens = rem[rem['Fur'] == 'Solid Gold']
        else:
            cat_tokens = rem[rem['Background'] == cat]
        demand = scarcity.get(cat, 1)
        top_rarities = cat_tokens.sort_values('Total Score', ascending=False).head(demand)['Total Score'].tolist()
        if len(top_rarities) <= 1:
            scarcity_factor = 1.5
        else:
            scarcity_factor = 1 + (top_rarities[0] - top_rarities[-1]) / (top_rarities[0] + 1e-6)
        top_score = cat_tokens['Total Score'].max() if not cat_tokens.empty else 0.01
        if cat == "Gold":
            top_score *= GOLD_BONUS_MULTIPLIER
        all_factors.append((scarcity_factor, top_score))

    combined_score = rarity * (GOLD_BONUS_MULTIPLIER if contributes_gold else 1)
    budget_fraction = combined_score / total_needed_rarity if total_needed_rarity > 0 else 0.3

    if slots_left == 1:
        return round(budget, 1)

    bid = min(budget, budget * budget_fraction)
    return round(bid, 1)

# =============== SIDEBAR CONFIG ===============
st.sidebar.title("Game Setup")
S.num_players = st.sidebar.number_input("Players incl. you", 2, 20, value=S.num_players)
for i in range(1, S.num_players + 1):
    S.players.setdefault(f"Player {i}", {"budget": STARTING_BUDGET, "tokens": []})

# Allow adjustment of Gold bonus multiplier
GOLD_BONUS_MULTIPLIER = st.sidebar.slider("Gold Bonus Multiplier", 1.0, 3.0, GOLD_BONUS_MULTIPLIER, 0.1)

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
                p: calculate_bid(token, p)
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
        "Budget": S.players[p]['budget'],
        **{bg: "✅" if bg not in missing_bgs(p) else "❌" for bg in MANDATORY_BACKGROUNDS},
        "Gold": "✅" if has_gold(p) else "❌",
        "Score": total_score(p)
    } for p in S.players])
    st.dataframe(matrix.set_index("Player"))

    st.subheader("Category Demand Tracker")
    st.write(category_scarcity())

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

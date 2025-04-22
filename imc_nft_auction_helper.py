# imc_nft_auction_helper.py
"""
Streamlit dashboard for IMC NFT Auction Game
Budget‑fraction bidding model aiming to complete the collection
(Blue, Aquamarine, Yellow backgrounds + Solid‑Gold fur) in ≤3 tokens.

Author: Thomasvdbelt
"""
import streamlit as st
import pandas as pd
import numpy as np

# =============== CONFIG ===============
STARTING_BUDGET      = 50
MANDATORY_BACKGROUNDS = ["Blue", "Aquamarine", "Yellow"]

# =============== LOAD DATA ===============
@st.cache_data
def load_data():
    df = pd.read_excel("NFT_Auction_Data.xlsx")
    # add Total‑Score column if absent
    if "Total Score" not in df.columns:
        rarity_cols  = [c for c in df.columns if "Rarity" in c and "Total" not in c]
        df["Total Score"] = (1 / df[rarity_cols]).sum(axis=1)
    return df

df        = load_data()
ALL_GOLD  = set(df[df["Fur"] == "Solid Gold"]["id"])

# =============== SESSION STATE ===============
S = st.session_state
if "players" not in S:
    S.players        = {"Player 1": {"budget": STARTING_BUDGET, "tokens": []}}
if "num_players" not in S:
    S.num_players    = 13
if "auctioned_ids" not in S:
    S.auctioned_ids  = set()

# =============== HELPERS ===============
def remaining_df():
    """Tokens not yet auctioned away."""
    return df[~df["id"].isin(S.auctioned_ids)]

def tokens_of(player):
    """DataFrame of tokens owned by player."""
    return df[df["id"].isin(S.players[player]["tokens"])]

def has_gold(player):
    return any(t in ALL_GOLD for t in S.players[player]["tokens"])

def missing_bgs(player):
    owned = set(tokens_of(player)["Background"])
    return [bg for bg in MANDATORY_BACKGROUNDS if bg not in owned]

def total_score(player):
    owned = tokens_of(player)
    score = 0
    # best card per required background
    for bg in MANDATORY_BACKGROUNDS:
        bg_cards = owned[owned["Background"] == bg]
        if not bg_cards.empty:
            score += bg_cards["Total Score"].max()
    # best gold
    if has_gold(player):
        gold_cards = owned[owned["Fur"] == "Solid Gold"]
        if not gold_cards.empty:
            score += gold_cards["Total Score"].max()
    return round(score, 2)

# =============== SCARCITY / QUALITY SPREAD ===============
def topK_quality_stats(category_mask, demand_count, K_cap=10, eps=1e-6):
    """
    Returns (expected_score, best_score, worst_of_topK, K_used)
    where expected_score = mean of top‑K scores.
    """
    cat_left = remaining_df()[category_mask]
    if cat_left.empty:
        return (0.01, 0.01, 0.01, 1)   # avoid div/0

    K = max(1, min(demand_count, K_cap))
    topK = cat_left["Total Score"].sort_values(ascending=False).head(K)
    return (topK.mean(), topK.iloc[0], topK.iloc[-1], K)

# =============== BID LOGIC ===============
def calculate_bid(token: pd.Series, player: str, eps=1e-6) -> int:
    """
    Suggested integer bid ($) for `player` on `token`, or 0 to pass.
    Logic:
      – only bids if token fills at least one missing requirement
      – splits remaining budget across still‑missing slots
      – scales by ( token_score / expected_score ) × quality‑spread factor
    """
    budget = S.players[player]["budget"]
    if budget < 1:
        return 0

    # ---------------- player needs ----------------
    need_bgs   = missing_bgs(player)      # list of backgrounds still missing
    need_gold  = not has_gold(player)

    token_bg   = token["Background"]
    is_gold    = token["Fur"] == "Solid Gold"

    fills_bg   = token_bg in need_bgs
    fills_gold = is_gold and need_gold

    # finished collection → do nothing (no pure‑upgrade mode)
    if not (need_bgs or need_gold):
        return 0

    # skip tokens that don’t help
    if not (fills_bg or fills_gold):
        return 0

    # ---------------- how many slots involved ----------------
    slots_needed = len(need_bgs) + int(need_gold)
    slots_filled = int(fills_bg) + int(fills_gold)      # 1 or 2 when a Gold also has needed BG
    base_share   = budget / slots_needed * slots_filled

    # ---------------- category stats (choose BG or Gold) ----------------
    if fills_gold:                                          # valuing Gold aspect first
        cat_mask   = remaining_df()["Fur"] == "Solid Gold"
        cat_demand = sum(not has_gold(p) for p in S.players)
        expected, maxi, mini, _ = topK_quality_stats(cat_mask, cat_demand)
    else:                                                   # valuing background aspect
        cat_mask   = remaining_df()["Background"] == token_bg
        cat_demand = sum(token_bg in missing_bgs(p) for p in S.players)
        expected, maxi, mini, _ = topK_quality_stats(cat_mask, cat_demand)

    # ---------------- quality multipliers ----------------
    token_score   = token["Total Score"]
    marginal      = token_score / expected                     # >1 ⇒ above fair value
    spread_factor = 1 + (token_score - mini) / (maxi - mini + eps)

    bid = base_share * marginal * spread_factor
    bid = max(1, round(bid))          # round to whole dollars, min $1
    return int(min(bid, budget))

# =============== SIDEBAR CONFIG ===============
st.sidebar.title("Game Setup")
S.num_players = st.sidebar.number_input("Players incl. you", 2, 20, value=S.num_players)
for i in range(1, S.num_players + 1):
    S.players.setdefault(f"Player {i}", {"budget": STARTING_BUDGET, "tokens": []})

# =============== MAIN TABS ===============
auction_tab, browse_tab = st.tabs(["🎯 Auction Mode", "📦 Token Overview"])

# ----------  AUCTION MODE ----------
with auction_tab:
    st.title("Live Auction Tracker")

    token_id = st.text_input("Current Token ID")
    if token_id:
        try:
            tid   = int(token_id)
            token = df[df["id"] == tid].iloc[0]
            st.subheader("Token Info")
            st.json(token[["Background", "Fur", "Total Score"]].to_dict())

            bids = {p: calculate_bid(token, p) for p in S.players}
            bid_df = pd.DataFrame.from_dict(bids, orient="index", columns=["Max Bid ($)"])
            st.subheader("Suggested Bids (integer dollars)")
            st.dataframe(bid_df)

        except Exception as e:
            st.warning(f"Invalid token ID: {e}")

    st.divider()
    # ------------- Log auction result -------------
    with st.form("📥 Log Auction Result"):
        sid   = st.text_input("Sold Token ID")
        buyer = st.selectbox("Winner", list(S.players.keys()))
        price = st.number_input("Winning Price ($)", 1, 50, 1)
        if st.form_submit_button("Log Token"):
            try:
                sid_int = int(sid)
                S.auctioned_ids.add(sid_int)
                S.players[buyer]["tokens"].append(sid_int)
                S.players[buyer]["budget"] -= price
                st.success(f"Token {sid_int} added to {buyer} for ${price}")
            except Exception as e:
                st.error(f"Invalid ID: {e}")

    st.divider()
    # ------------- Player overview -------------
    st.subheader("Player Overview")
    matrix = pd.DataFrame([{
        "Player": p,
        "Budget": S.players[p]["budget"],
        **{bg: "✅" if bg not in missing_bgs(p) else "❌" for bg in MANDATORY_BACKGROUNDS},
        "Gold":    "✅" if has_gold(p) else "❌",
        "Score":   total_score(p)
    } for p in S.players]).set_index("Player")
    st.dataframe(matrix)

# ----------  TOKEN BROWSER ----------
with browse_tab:
    st.title("Remaining Tokens")
    rem = remaining_df()

    col1, col2 = st.columns(2)
    with col1:
        bgs = st.multiselect("Filter Backgrounds", options=["All"] + MANDATORY_BACKGROUNDS, default=["All"])
        if "All" not in bgs:
            rem = rem[rem["Background"].isin(bgs)]
    with col2:
        if st.checkbox("Gold Only"):
            rem = rem[rem["Fur"] == "Solid Gold"]

    st.dataframe(rem[["id", "Background", "Fur", "Total Score"]]
                 .sort_values("Total Score", ascending=False))

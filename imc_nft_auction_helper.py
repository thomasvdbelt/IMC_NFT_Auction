
# imc_nft_auction_helper.py
"""Streamlit dashboard to assist with IMC NFT Auction Game.
Place this script in the same folder as `NFT_Auction_Data.xlsx` and run:
    streamlit run imc_nft_auction_helper.py
The app keeps track of your budget, collection status, and recommends bids
and nominations based on dynamic valuations that account for scarcity and
opponents' needs.

Author: ChatGPT
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
SAFETY_CASH_BUFFER = 2          # Leave at least this amount unspent
# ------------------------------------------------------------------------

@st.cache_data
def load_data():
    df = pd.read_excel('NFT_Auction_Data.xlsx')
    # Ensure Total Score column exists; compute if missing
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
    st.session_state.my_tokens = []          # list of ids you own
if 'others_budget' not in st.session_state:
    st.session_state.others_budget = {}      # {player_name: remaining}
if 'auctioned_ids' not in st.session_state:
    st.session_state.auctioned_ids = set()   # ids already sold

# ---- HELPER FUNCTIONS ---------------------------------------------------
def remaining_df():
    """Return dataframe of tokens not yet auctioned"""
    return df[~df['id'].isin(st.session_state.auctioned_ids)]

def collection_df():
    """Return dataframe of tokens you own"""
    return df[df['id'].isin(st.session_state.my_tokens)]

def collection_status():
    owned = collection_df()
    backgrounds_owned = set(owned['Background'])
    has_gold = not owned[owned['Fur']=='Solid Gold'].empty
    missing_bg = [c for c in BACKGROUND_COLORS if c not in backgrounds_owned]
    return backgrounds_owned, missing_bg, has_gold

def best_scores_by_background(owned):
    scores = {}
    for bg in BACKGROUND_COLORS:
        tokens_bg = owned[owned['Background']==bg]
        scores[bg] = tokens_bg['Total Score'].max() if not tokens_bg.empty else 0
    return scores

def value_token(token_row):
    """Heuristic value of a token to *you* given current state"""
    base = token_row['Total Score']
    backgrounds_owned, missing_bg, has_gold = collection_status()
    multiplier = 1.0
    if token_row['Fur'] == 'Solid Gold':
        multiplier += GOLD_FUR_VALUE_BOOST if not has_gold else 0.2
    if token_row['Background'] in missing_bg:
        multiplier += MISSING_BACKGROUND_BOOST
    else:
        # potential upgrade
        current_best = best_scores_by_background(collection_df()).get(token_row['Background'], 0)
        if token_row['Total Score'] > current_best:
            multiplier += UPGRADE_BACKGROUND_BOOST
    # scarcity
    remaining_bg_count = remaining_df()['Background'].value_counts().to_dict().get(token_row['Background'], 0)
    scarcity_factor = (1 - remaining_bg_count / initial_bg_counts[token_row['Background']])
    multiplier += scarcity_factor * SCARCITY_BOOST_SCALE
    return base * multiplier

def suggested_bid(token_row):
    val = value_token(token_row)
    max_affordable = st.session_state.my_budget - SAFETY_CASH_BUFFER
    return min(round(val,1), max_affordable)

def recommend_nomination(top_n=20):
    rem = remaining_df().copy()
    rem['MyValue'] = rem.apply(value_token, axis=1)
    rem_sorted = rem.sort_values('MyValue', ascending=False)
    return rem_sorted.head(top_n)[['id','Background','Fur','Total Score','MyValue']]

# ---- SIDEBAR INPUTS -----------------------------------------------------
st.sidebar.header("🔧 Update Game State")

with st.sidebar.expander("💰 Budget & Tokens", expanded=False):
    st.session_state.my_budget = st.number_input("My remaining budget", 
                                                min_value=0, max_value=STARTING_BUDGET, 
                                                value=st.session_state.my_budget, step=1)
    new_token = st.text_input("Add purchased token id", value="")
    if st.button("Add token", key='add_token'):
        try:
            tid = int(new_token)
            if tid not in df['id'].values:
                st.warning("Token id not found in dataset.")
            elif tid in st.session_state.my_tokens:
                st.warning("You already own this token.")
            else:
                st.session_state.my_tokens.append(tid)
                st.success(f"Token {tid} added to your collection.")
        except ValueError:
            st.warning("Please enter a valid integer id.")
    if st.button("Undo last token", key='undo'):
        if st.session_state.my_tokens:
            removed = st.session_state.my_tokens.pop()
            st.success(f"Removed token {removed} from collection.")

with st.sidebar.expander("📑 Other players", expanded=False):
    player_to_update = st.text_input("Player name", value="")
    budget_val = st.number_input("Their remaining budget", min_value=0, max_value=STARTING_BUDGET, value=0, step=1)
    if st.button("Update / Add player", key='update_player'):
        if player_to_update:
            st.session_state.others_budget[player_to_update] = budget_val
            st.success("Updated.")
    if st.button("Remove player", key='remove_player'):
        if player_to_update in st.session_state.others_budget:
            del st.session_state.others_budget[player_to_update]
            st.success("Removed.")

with st.sidebar.expander("📦 Auction log", expanded=False):
    sold_token = st.text_input("Mark token id sold", value="")
    if st.button("Mark sold", key='sold'):
        try:
            sold_id = int(sold_token)
            st.session_state.auctioned_ids.add(sold_id)
            st.success(f"Token {sold_id} marked as auctioned.")
        except ValueError:
            st.warning("Enter valid id.")

# ---- MAIN TABS ----------------------------------------------------------
tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "💡 Suggestions", "📈 Token Browser"])

with tab1:
    st.header("Your Collection & KPIs")
    owned_df = collection_df()
    st.subheader("Owned tokens")
    st.dataframe(owned_df[['id','Background','Fur','Total Score']])
    bg_owned, missing_bg, has_gold = collection_status()
    st.markdown(f"**Backgrounds owned:** {', '.join(sorted(list(bg_owned)))}")
    st.markdown(f"**Missing backgrounds:** {', '.join(missing_bg) if missing_bg else 'None'}")
    st.markdown(f"**Gold fur acquired:** {'✅' if has_gold else '❌'}")
    # Score calculation (simple)
    best_scores = best_scores_by_background(owned_df)
    score_without_wildcard = sum(best_scores.values()) if has_gold else 0
    st.markdown(f"**Current projected final score:** {score_without_wildcard:.1f} (without wildcard multiplier)")
    st.markdown(f"**Remaining budget:** ${st.session_state.my_budget}")
    st.markdown("---")
    st.subheader("Other players (manual)")
    if st.session_state.others_budget:
        others_df = pd.DataFrame({'Player': list(st.session_state.others_budget.keys()),
                                  'Budget': list(st.session_state.others_budget.values())})
        st.dataframe(others_df)

with tab2:
    st.header("Bid & Nomination Advice")
    current_id = st.text_input("Current token id being auctioned", value="")
    if current_id:
        try:
            cid = int(current_id)
            token_row = df[df['id']==cid].iloc[0]
            val = value_token(token_row)
            bid = suggested_bid(token_row)
            st.success(f"Suggested bid ceiling: **${bid:.1f}** (heuristic value: {val:.1f})")
            st.json(token_row[['Background','Fur','Total Score']].to_dict())
        except Exception as e:
            st.error("Invalid id.")
    st.markdown("---")
    st.subheader("Top nominations for you")
    st.write("Filter for tokens that maximise your collection objectives and force rivals to pay up.")
    recs = recommend_nomination(top_n=15)
    st.dataframe(recs)

with tab3:
    st.header("Browse remaining tokens")
    rem = remaining_df()
    cols = st.multiselect("Select columns to view", options=['id','Background','Fur','Clothes','Mouth','Eyes','Hat','Total Score'],
                          default=['id','Background','Fur','Total Score'])
    st.dataframe(rem[cols].sort_values('Total Score', ascending=False))

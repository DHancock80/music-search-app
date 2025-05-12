import streamlit as st
import pandas as pd
import re
from rapidfuzz import fuzz
import os

# Load and clean data
@st.cache_data
def load_data():
    df = pd.read_csv("expanded_discogs_tracklists.csv")
    df.columns = df.columns.str.strip()
    df = df.dropna(subset=["Artist", "Track Title"])
    return df

# Clean artist string
def clean_artist_name(name):
    name = name.lower()
    name = re.sub(r'[\*\(\)#\[\]]', '', name)  # remove *, (#), [], etc.
    name = re.sub(r'\s+', ' ', name)  # collapse spaces
    return name.strip()

# Extract all artists from collaborations
def extract_individual_artists(artist_str):
    delimiters = [',', '&', ' and ', ' feat. ', ' featuring ', ' ft. ']
    pattern = '|'.join(map(re.escape, delimiters))
    split_artists = re.split(pattern, artist_str, flags=re.IGNORECASE)
    return [clean_artist_name(a) for a in split_artists if a.strip()]

# Fuzzy match
def fuzzy_artist_match(df, query):
    query_clean = clean_artist_name(query)
    results = []
    for idx, row in df.iterrows():
        artists = extract_individual_artists(row['Artist'])
        for artist in artists:
            if fuzz.partial_ratio(query_clean, artist) >= 85:
                results.append(row)
                break
    return pd.DataFrame(results)

# Filter video tracks
def filter_video(df, include_video):
    if include_video == "Audio Only":
        return df[df['Format'].str.contains("video", case=False) == False]
    elif include_video == "Video Only":
        return df[df['Format'].str.contains("video", case=False)]
    return df

# Show cover art from Discogs
@st.cache_data
def get_cover_url(release_id):
    return f"https://img.discogs.com/placeholder/{release_id}.jpg"

# Load session search history
def update_search_history(query):
    if 'history' not in st.session_state:
        st.session_state.history = []
    if query and query not in st.session_state.history:
        st.session_state.history.insert(0, query)
        st.session_state.history = st.session_state.history[:10]  # limit to 10

# Main app
st.set_page_config(page_title="Music Search App", layout="wide")
st.title("🎵 DH Music Collection Search")

# Load CSV
try:
    df = load_data()
except FileNotFoundError:
    st.error("CSV file not found. Please upload expanded_discogs_tracklists.csv.")
    st.stop()

# Sidebar options
query = st.text_input("Search Artist (fuzzy matching supported)")
format_filter = st.selectbox("Show:", ["All", "Audio Only", "Video Only"])

if query:
    update_search_history(query)
    filtered_df = fuzzy_artist_match(df, query)
    filtered_df = filter_video(filtered_df, format_filter)

    if not filtered_df.empty:
        st.markdown(f"### Results for **{query}** ({len(filtered_df)} matches)")
        for _, row in filtered_df.iterrows():
            with st.container():
                col1, col2 = st.columns([1, 4])
                with col1:
                    release_id = row.get("release_id", "")
                    if pd.notna(release_id):
                        st.image(get_cover_url(release_id), width=100)
                with col2:
                    st.markdown(f"**{row['Track Title']}**  ")
                    st.markdown(f"Artist: *{row['Artist']}*  ")
                    st.markdown(f"Album: {row['Title']} ({row.get('Format', 'Unknown')})")
                    st.markdown("---")
    else:
        st.warning("No results found.")

# Show search history
if 'history' in st.session_state and st.session_state.history:
    st.sidebar.markdown("### 🔎 Search History")
    for past_query in st.session_state.history:
        if st.sidebar.button(past_query):
            query = past_query
            st.experimental_rerun()

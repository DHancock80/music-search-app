# music_search_app.py
import streamlit as st
import pandas as pd

# Load your expanded tracklist CSV file
df = pd.read_csv("expanded_discogs_tracklist.csv", dtype=str).fillna("")

# Title
st.title("🎵 My Music Collection Search")

# Search type filter
search_type = st.radio("Search for:", ["Song Title", "Artist", "Album"], horizontal=True)

# Search input
query = st.text_input("Enter search term:").strip().lower()

# Format filter
format_filter = st.selectbox("Filter by format:", ["All", "Album", "Single"])

# Search logic
def search(df, query, search_type, format_filter):
    if not query:
        return pd.DataFrame()

    result = df.copy()
    
    if format_filter != "All":
        result = result[result["Format"].str.lower().str.contains(format_filter.lower())]

    if search_type == "Song Title":
        result = result[result["track_title"].str.lower().str.contains(query)]
        result = result.sort_values("track_title")
    elif search_type == "Artist":
        result = result[result["track_artist"].str.lower().str.contains(query)]
        result = result.sort_values("track_title")
    elif search_type == "Album":
        result = result[result["Title"].str.lower().str.contains(query)]
        result = result.sort_values("Title")

    return result[["track_title", "track_artist", "Title", "Artist", "Catalog#", "Format", "Released", "disc_number", "track_position"]]

# Perform search
if query:
    results = search(df, query, search_type, format_filter)
    if not results.empty:
        st.success(f"Found {len(results)} result(s).")
        st.dataframe(results, use_container_width=True)
    else:
        st.warning("No results found.")
else:
    st.info("Enter a search term above to begin.")

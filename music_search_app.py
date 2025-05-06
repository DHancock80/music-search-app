import streamlit as st
import pandas as pd

# Load the data
df = pd.read_csv("expanded_discogs_tracklist.csv")

# Standardize strings
df["Artist"] = df["Artist"].astype(str)
df["Track Title"] = df["Track Title"].astype(str)
df["Title"] = df["Title"].astype(str)
df["Format"] = df["Format"].astype(str)

# App title
st.title("🎵 DH Music Collection Search App")

# Search input
query = st.text_input("Search for a song or artist")

# Search type: song or artist
search_type = st.selectbox("Search by", ["Song Title", "Artist"])

# Format filter
format_filter = st.selectbox("Filter by format", ["All", "Album", "Single"])

# Search function
def search(df, query, search_type, format_filter):
    result = df.copy()

    # Apply format filter
    if format_filter != "All":
        result = result[result["Format"].str.lower().str.contains(format_filter.lower())]

    # Apply search filter
    if search_type == "Song Title":
        result = result[result["Track Title"].str.lower().str.contains(query.lower())]
        result = result.sort_values(by=["Track Title"])
    else:  # Artist
        result = result[result["Artist"].str.lower().str.contains(query.lower())]
        result = result.sort_values(by=["Track Title"])

    return result[["Artist", "Track Title", "Title", "Format", "CD", "Track Number"]]

# Display results
if query:
    results = search(df, query, search_type, format_filter)

    if not results.empty:
        st.write(f"### Results ({len(results)} found):")
        st.dataframe(results)
    else:
        st.warning("No matching results found.")

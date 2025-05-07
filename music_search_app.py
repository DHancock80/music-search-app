import streamlit as st
import pandas as pd
import requests
from PIL import Image
from io import BytesIO
import os
import json

# Load Discogs API token from Streamlit secrets
DISCOGS_TOKEN = st.secrets["discogs_token"]

# Load the CSV file and normalize column names
# We assume the file uses ISO-8859-1 encoding due to prior issues
csv_file = "expanded_discogs_tracklists.csv"
df = pd.read_csv(csv_file, dtype=str, encoding="ISO-8859-1").fillna("")
df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")  # normalize column names

# In-memory cover art override cache (could be stored remotely later)
COVER_ART_CACHE_FILE = "cover_art_cache.json"

if os.path.exists(COVER_ART_CACHE_FILE):
    with open(COVER_ART_CACHE_FILE, "r") as f:
        cover_art_overrides = json.load(f)
else:
    cover_art_overrides = {}

# Sidebar Filters
search_type = st.radio("Search by:", ["Song Title", "Artist"], horizontal=True)
query = st.text_input(f"Enter {search_type}")

# Format filters as horizontal checkboxes
format_options = ["album", "single", "video"]
st.markdown("**Filter by Format:**")
cols = st.columns(len(format_options))
selected_formats = []
for i, fmt in enumerate(format_options):
    if cols[i].checkbox(fmt.capitalize(), value=True):
        selected_formats.append(fmt)

# Helper: Get Discogs cover art by release_id
def fetch_cover_art(release_id):
    url = f"https://api.discogs.com/releases/{release_id}?token={DISCOGS_TOKEN}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            return data.get("images", [{}])[0].get("uri")
    except Exception as e:
        print(f"Discogs API error for release {release_id}: {e}")
    return None

# Perform search if query is entered
if query:
    if search_type == "Song Title":
        result = df[df["track_title"].str.contains(query, case=False, na=False)]
    else:
        result = df[df["artist"].str.contains(query, case=False, na=False)]

    if selected_formats:
        result = result[result["format"].str.lower().isin(selected_formats)]

    # Group results by release
    grouped = result.groupby("release_id")
    for release_id, group in grouped:
        release_info = group.iloc[0]

        st.markdown("---")

        # Cover art handling
        cover_url = cover_art_overrides.get(release_id)
        if not cover_url:
            cover_url = fetch_cover_art(release_id)
            if cover_url:
                cover_art_overrides[release_id] = cover_url
                with open(COVER_ART_CACHE_FILE, "w") as f:
                    json.dump(cover_art_overrides, f)

        if cover_url:
            st.image(cover_url, width=150)
        else:
            st.text("No cover art available")

        # Display tracklist for this release
        st.markdown(f"**{release_info['title']}** by **{release_info['artist']}**")
        st.markdown(f"Label: {release_info['label']}  ")
        st.markdown(f"Released: {release_info['released']}  ")
        st.markdown("**Tracklist:**")

        for _, track in group.iterrows():
            st.markdown(f"{track['cd']} - Track {track['track_number']}: {track['track_title']}")

        # Option to update cover art
        with st.expander("Suggest new cover image"):
            new_url = st.text_input(f"Paste new image URL for release {release_id}", key=f"url_{release_id}")
            if new_url:
                cover_art_overrides[release_id] = new_url
                with open(COVER_ART_CACHE_FILE, "w") as f:
                    json.dump(cover_art_overrides, f)
                st.success("New cover art URL saved.")

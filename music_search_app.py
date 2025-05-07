import streamlit as st
import pandas as pd
import requests
import os
from PIL import Image
from io import BytesIO

# Load Discogs token from Streamlit secrets
DISCOGS_TOKEN = st.secrets["discogs_token"]

# Load CSV and clean up column names and data
csv_file = "expanded_discogs_tracklists.csv"
df = pd.read_csv(csv_file, dtype=str, encoding="ISO-8859-1").fillna("")

# Normalize column names
# e.g., 'Track Number' or 'Track\nNumber' -> 'track_number'
df.columns = df.columns.str.strip().str.lower().str.replace(r"\s+", "_", regex=True)

# Strip whitespace from all string values
df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)

# Check columns after cleaning
# st.write("Cleaned column names:", list(df.columns))

# Set page title
st.set_page_config(page_title="Music Collection Search", layout="wide")
st.title("Search Your Music Collection")

# Sidebar filters
search_type = st.radio("Search by:", ["Song Title", "Artist", "Album Title"])
query = st.text_input("Enter your search:")

format_choice = st.radio("Filter by Format", ["Album", "Single", "Video"], horizontal=True)

# Main search logic
if query:
    query = query.lower()

    if search_type == "Song Title":
        result = df[df["track_title"].str.lower().str.contains(query, na=False)]
    elif search_type == "Artist":
        result = df[df["artist"].str.lower().str.contains(query, na=False)]
    else:
        result = df[df["title"].str.lower().str.contains(query, na=False)]

    result = result[result["format"].str.contains(format_choice, na=False, case=False)]

    if result.empty:
        st.warning("No results found.")
    else:
        for _, row in result.iterrows():
            release_id = row["release_id"]
            track_title = row["track_title"]
            album_title = row["title"]
            artist = row["artist"]
            label = row["label"]
            release_date = row["released"]
            cd_number = row["cd"]
            track_number = row["track_number"]

            st.markdown(f"### {track_title} — {artist}")
            st.markdown(f"**Album:** {album_title}")
            st.markdown(f"**Label:** {label}  ")
            st.markdown(f"**Released:** {release_date} | CD: {cd_number}, Track: {track_number}")

            # Try cached cover art
            local_path = f"cover_art/{release_id}.jpg"
            if os.path.exists(local_path):
                st.image(local_path, width=150)
            else:
                # Try Discogs API
                try:
                    url = f"https://api.discogs.com/releases/{release_id}?token={DISCOGS_TOKEN}"
                    response = requests.get(url)
                    if response.status_code == 200:
                        data = response.json()
                        if "images" in data and data["images"]:
                            image_url = data["images"][0]["uri"]
                            img_data = requests.get(image_url).content
                            os.makedirs("cover_art", exist_ok=True)
                            with open(local_path, "wb") as f:
                                f.write(img_data)
                            st.image(local_path, width=150)
                        else:
                            st.info("No image available.")
                    else:
                        st.info("Discogs API error.")
                except Exception as e:
                    st.warning(f"Error fetching image: {e}")

            # User correction UI
            new_url = st.text_input(f"Paste new image URL for release {release_id}", key=f"url_{release_id}")
            if new_url:
                try:
                    img_data = requests.get(new_url).content
                    with open(local_path, "wb") as f:
                        f.write(img_data)
                    st.success("Image updated!")
                    st.image(local_path, width=150)
                except Exception as e:
                    st.error(f"Failed to load image from URL: {e}")

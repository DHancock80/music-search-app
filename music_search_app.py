import streamlit as st
import pandas as pd
import requests
import os
from PIL import Image, UnidentifiedImageError
from io import BytesIO

# Load Discogs token from Streamlit secrets
DISCOGS_TOKEN = st.secrets["discogs_token"]
HEADERS = {"Authorization": f"Discogs token={DISCOGS_TOKEN}"}

# Load CSV
@st.cache_data
def load_data():
    df = pd.read_csv("collection.csv")
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_").str.replace("#", "number")
    return df

df = load_data()

# Search inputs
st.title("Music Collection Search")

col1, col2, col3 = st.columns(3)
with col1:
    query = st.text_input("Search by Song Title or Artist")
with col2:
    search_type = st.radio("Search by", ["Song Title", "Artist"], horizontal=True)
with col3:
    format_filter = st.radio("Filter by Format", ["All", "Album", "Single", "Video"], horizontal=True)

# Filter based on inputs
if query:
    if search_type == "Song Title":
        result = df[df["track_title"].str.contains(query, case=False, na=False)]
    else:
        result = df[df["artist"].str.contains(query, case=False, na=False)]

    if format_filter != "All":
        result = result[result["format"].str.contains(format_filter, case=False, na=False)]

    st.write(f"### Results: {len(result)} matches")

    for i, row in result.iterrows():
        st.markdown(f"**{row['track_title']}** – *{row['title']}* ({row['artist']})")
        st.text(f"Label: {row['label']} | Released: {row['released']} | CD: {row['cd']} | Track #: {row['track_number']}")

        # Try loading from local cache
        local_path = f"images/{row['release_id']}.jpg"
        image_shown = False

        if os.path.exists(local_path):
            try:
                st.image(local_path, width=150)
                image_shown = True
            except UnidentifiedImageError:
                os.remove(local_path)

        # If not in cache, try downloading from Discogs
        if not image_shown:
            response = requests.get(f"https://api.discogs.com/releases/{row['release_id']}", headers=HEADERS)
            if response.status_code == 200:
                data = response.json()
                image_url = data.get("images", [{}])[0].get("uri")
                if image_url:
                    try:
                        image_data = requests.get(image_url).content
                        img = Image.open(BytesIO(image_data))
                        st.image(img, width=150)

                        # Save locally
                        os.makedirs("images", exist_ok=True)
                        with open(local_path, "wb") as f:
                            f.write(image_data)
                    except Exception as e:
                        st.warning("Image failed to load.")
            else:
                st.warning("Cover image not found.")

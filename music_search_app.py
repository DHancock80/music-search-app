import streamlit as st
import pandas as pd
import requests
import os
from PIL import Image
from io import BytesIO

# Load secrets (Discogs token)
DISCOGS_TOKEN = st.secrets["discogs_token"]

# Constants
CSV_FILE = "expanded_discogs_tracklists.csv"
COVER_OVERRIDE_FILE = "cover_overrides.csv"
COVER_DIR = "cover_cache"

# Ensure cover cache directory exists
os.makedirs(COVER_DIR, exist_ok=True)

@st.cache_data
def load_data():
    df = pd.read_csv(CSV_FILE)
    return df

@st.cache_data
def load_cover_overrides():
    if os.path.exists(COVER_OVERRIDE_FILE):
        return pd.read_csv(COVER_OVERRIDE_FILE)
    return pd.DataFrame(columns=["release_id", "image_url"])

def save_cover_override(release_id, image_url):
    overrides = load_cover_overrides()
    new_entry = pd.DataFrame([[release_id, image_url]], columns=["release_id", "image_url"])
    updated = pd.concat([overrides, new_entry], ignore_index=True)
    updated.drop_duplicates(subset="release_id", keep="last", inplace=True)
    updated.to_csv(COVER_OVERRIDE_FILE, index=False)

@st.cache_data(show_spinner=False)
def get_cover_image(release_id):
    # Check for user override first
    overrides = load_cover_overrides()
    override_row = overrides[overrides["release_id"] == release_id]
    if not override_row.empty:
        return override_row.iloc[0]["image_url"]

    # Check cache
    local_path = os.path.join(COVER_DIR, f"{release_id}.jpg")
    if os.path.exists(local_path):
        return local_path

    # Fetch from Discogs
    url = f"https://api.discogs.com/releases/{release_id}?token={DISCOGS_TOKEN}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            image_url = data.get("images", [{}])[0].get("uri")
            if image_url:
                img_data = requests.get(image_url).content
                with open(local_path, "wb") as f:
                    f.write(img_data)
                return local_path
    except:
        pass

    return None

# UI Layout
st.set_page_config(page_title="Music Collection Search", layout="wide")
st.title("🎵 Music Collection Search")

# Search options
search_type = st.radio("Search by:", ["Artist", "Title", "Track Title"], horizontal=True)
query = st.text_input("Enter your search:")

# Load data
df = load_data()

# Search logic
if query:
    if search_type == "Artist":
        results = df[df["Artist"].str.contains(query, case=False, na=False)]
    elif search_type == "Title":
        results = df[df["Title"].str.contains(query, case=False, na=False)]
    elif search_type == "Track Title":
        results = df[df["Track Title"].str.contains(query, case=False, na=False)]
    else:
        results = pd.DataFrame()

    st.markdown(f"### Found {len(results)} result(s)")

    for _, row in results.iterrows():
        st.markdown("---")
        cols = st.columns([1, 3])
        with cols[0]:
            cover = get_cover_image(row["release_id"])
            if cover:
                try:
                    st.image(cover, width=150)
                except:
                    st.warning("Invalid image format. You can override below.")
            else:
                st.info("No cover image available.")

        with cols[1]:
            st.subheader(f"{row['Artist']} - {row['Title']}")
            st.text(f"Track {row['Track Number']} on Disc {row['CD']}")
            st.text(f"Label: {row['Label']} | Format: {row['Format']} | Released: {row['Released']}")
            st.text(f"Track Title: {row['Track Title']}")

            # Allow image override
            with st.expander("Submit a new cover image URL"):
                new_url = st.text_input(f"New cover URL for Release ID {row['release_id']}", key=row['release_id'])
                if st.button("Submit URL", key=f"btn_{row['release_id']}"):
                    save_cover_override(row['release_id'], new_url)
                    st.success("Cover override saved. Refresh to see changes.")
else:
    st.info("Enter a search term to begin.")

import streamlit as st
import pandas as pd
import requests
import base64
import os

# Config
CSV_FILE = "expanded_discogs_tracklist.csv"
COVER_OVERRIDE_FILE = "cover_overrides.csv"

# --- Helper Functions ---
@st.cache_data
def load_data():
    return pd.read_csv(CSV_FILE, encoding='latin1')

@st.cache_data
def load_cover_overrides():
    if os.path.exists(COVER_OVERRIDE_FILE):
        return pd.read_csv(COVER_OVERRIDE_FILE)
    else:
        return pd.DataFrame(columns=["release_id", "cover_url"])

def save_cover_override(df):
    df.to_csv(COVER_OVERRIDE_FILE, index=False)
    if "GITHUB_TOKEN" in st.secrets:
        sync_to_github()

def sync_to_github():
    repo = st.secrets["GITHUB_REPO"]
    token = st.secrets["GITHUB_TOKEN"]
    path = "cover_overrides.csv"
    api_url = f"https://api.github.com/repos/{repo}/contents/{path}"

    with open(COVER_OVERRIDE_FILE, "rb") as file:
        content = file.read()
    content_b64 = base64.b64encode(content).decode()

    # Get current file SHA
    r = requests.get(api_url, headers={"Authorization": f"token {token}"})
    if r.status_code == 200:
        sha = r.json()["sha"]
        payload = {
            "message": "Update cover_overrides.csv",
            "content": content_b64,
            "sha": sha
        }
        response = requests.put(api_url, json=payload, headers={"Authorization": f"token {token}"})
    else:
        # Create new file if it doesn't exist
        payload = {
            "message": "Create cover_overrides.csv",
            "content": content_b64
        }
        response = requests.put(api_url, json=payload, headers={"Authorization": f"token {token}"})
    if response.status_code in [200, 201]:
        st.session_state["last_sync"] = "✅ cover_overrides.csv synced to GitHub."
    else:
        st.session_state["last_sync"] = f"❌ GitHub sync failed: {response.status_code} - {response.text}"

def fetch_discogs_cover(release_id):
    token = st.secrets["DISCOGS_TOKEN"]
    url = f"https://api.discogs.com/releases/{release_id}"
    headers = {"Authorization": f"Discogs token={token}"}
    try:
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            return data["images"][0]["uri"] if "images" in data else None
    except:
        return None

# --- Streamlit App ---
st.set_page_config(page_title="Music Search App", layout="wide")
st.markdown("<h1 style='font-size:40px;'>Music Search App</h1>", unsafe_allow_html=True)

# Load data
try:
    df = load_data()
except Exception as e:
    st.error(f"Error loading the CSV file: {e}")
    st.stop()

cover_overrides = load_cover_overrides()

# --- Search Controls ---
search_term = st.text_input("Enter your search:", "")
search_type = st.radio("Search by:", ["Song Title", "Artist", "Album"], horizontal=True)
format_filter = st.selectbox("Format filter:", options=["All", "Album", "Single", "Video"])

if search_term:
    if search_type == "Song Title":
        filtered = df[df["Track Title"].str.contains(search_term, case=False, na=False)]
    elif search_type == "Artist":
        filtered = df[df["Artist"].str.contains(search_term, case=False, na=False)]
    else:  # Album
        filtered = df[df["Title"].str.contains(search_term, case=False, na=False)]

    if format_filter != "All":
        filtered = filtered[filtered["Format"].str.contains(format_filter, case=False, na=False)]

    st.write(f"Found {len(filtered)} result(s)")

    # Group by Album (release_id)
    grouped = filtered.groupby("release_id")

    for release_id, group in grouped:
        album_title = group["Title"].iloc[0]
        album_artist = group["Artist"].iloc[0]
        album_format = group["Format"].iloc[0]

        # Handle Various artists label
        display_artist = album_artist if album_artist.lower() != "various" else "Various Artists"

        # Get cover art (from override first)
        cover_row = cover_overrides[cover_overrides["release_id"] == release_id]
        if not cover_row.empty:
            cover_url = cover_row["cover_url"].values[0]
        else:
            cover_url = fetch_discogs_cover(release_id)
            if cover_url:
                new_row = pd.DataFrame({"release_id": [release_id], "cover_url": [cover_url]})
                cover_overrides = pd.concat([cover_overrides, new_row], ignore_index=True)
                save_cover_override(cover_overrides)

        # --- Album Card ---
        col1, col2 = st.columns([1, 6])
        with col1:
            if cover_url:
                st.image(cover_url, width=120)
            else:
                st.write("(No cover art available)")

        with col2:
            st.markdown(f"### {album_title}")
            st.markdown(f"**Artist:** {display_artist}")

            # Cover art update section
            with st.expander("Update Cover Art"):
                new_cover = st.text_input(f"Paste a new cover art URL:", key=f"cover_{release_id}")
                col_submit, col_reset = st.columns([1, 1])
                with col_submit:
                    if st.button("Submit new cover art", key=f"submit_{release_id}"):
                        cover_overrides = cover_overrides[cover_overrides["release_id"] != release_id]
                        new_row = pd.DataFrame({"release_id": [release_id], "cover_url": [new_cover]})
                        cover_overrides = pd.concat([cover_overrides, new_row], ignore_index=True)
                        save_cover_override(cover_overrides)
                        st.success("Cover art override saved! Reload the app to see changes.")
                with col_reset:
                    if st.button("Reset to original cover", key=f"reset_{release_id}"):
                        cover_overrides = cover_overrides[cover_overrides["release_id"] != release_id]
                        save_cover_override(cover_overrides)
                        st.success("Cover override removed. Reload to apply changes.")

            # Tracklist expander
            with st.expander("Click to view tracklist"):
                tracklist = group[["Track Title", "Artist", "CD", "Track Number"]].rename(
                    columns={
                        "Track Title": "Song",
                        "Artist": "Artist",
                        "CD": "Disc",
                        "Track Number": "Track"
                    }
                )
                tracklist = tracklist.reset_index(drop=True)
                st.dataframe(tracklist, use_container_width=True, hide_index=True)

# Debugging expander for cover_overrides
with st.expander("🔧 View current cover_overrides.csv (debugging)"):
    st.dataframe(cover_overrides)

# Show last GitHub sync result (if any)
if "last_sync" in st.session_state:
    st.success(st.session_state["last_sync"])

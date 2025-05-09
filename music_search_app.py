import streamlit as st
import pandas as pd
import requests
import base64
import os
from fuzzywuzzy import fuzz

# ---------------------- Config ----------------------
CSV_FILE = "expanded_discogs_tracklists.csv"
COVER_OVERRIDE_FILE = "cover_overrides.csv"

# ------------------ Helper Functions ----------------
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

    r = requests.get(api_url, headers={"Authorization": f"token {token}"})
    if r.status_code == 200:
        sha = r.json()["sha"]
        payload = {
            "message": "Update cover_overrides.csv",
            "content": content_b64,
            "sha": sha
        }
        requests.put(api_url, json=payload, headers={"Authorization": f"token {token}"})
    else:
        payload = {
            "message": "Create cover_overrides.csv",
            "content": content_b64
        }
        requests.put(api_url, json=payload, headers={"Authorization": f"token {token}"})

def fetch_discogs_cover(release_id):
    token = st.secrets["DISCOGS_API_TOKEN"]
    url = f"https://api.discogs.com/releases/{release_id}"
    headers = {"Authorization": f"Discogs token={token}"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return data["images"][0]["uri"] if "images" in data else None
        else:
            return None
    except Exception:
        return None

# ------------------ Streamlit App -------------------
st.set_page_config(page_title="Music Search App", layout="wide")
st.markdown("<h1 style='font-size:40px;'>Music Search App</h1>", unsafe_allow_html=True)

# Load data
df = load_data()
cover_overrides = load_cover_overrides()

# ------------------ Search Controls -----------------
search_term = st.text_input("Enter your search:", "")
search_type = st.radio("Search by:", ["Song Title", "Artist", "Album"], horizontal=True)

# Format filter
format_counts = {
    "All": df["release_id"].nunique(),
    "Album": df[df["Format"].str.contains("Album|Compilation|Comp", case=False, na=False)]["release_id"].nunique(),
    "Single": df[df["Format"].str.contains("Single", case=False, na=False)]["release_id"].nunique(),
    "Video": df[df["Format"].str.contains("Video", case=False, na=False)]["release_id"].nunique(),
}
format_labels = [f"All ({format_counts['All']})", f"Album ({format_counts['Album']})", f"Single ({format_counts['Single']})", f"Video ({format_counts['Video']})"]
selected_format = st.radio("Filter by format:", format_labels, horizontal=True)

# Sort by
sort_option = st.radio("Sort by:", ["Album Title", "Artist"], horizontal=True)

# ------------------ Search Logic --------------------
def fuzzy_filter(df, column, search_term, threshold=80):
    return df[df[column].apply(lambda x: fuzz.token_set_ratio(str(x), search_term) >= threshold)]

if search_term:
    if search_type == "Song Title":
        results = fuzzy_filter(df, "Track Title", search_term)
    elif search_type == "Artist":
        results = fuzzy_filter(df, "Artist", search_term)
    else:
        results = fuzzy_filter(df, "Title", search_term)

    format_value = selected_format.split()[0]
    if format_value != "All":
        if format_value == "Album":
            results = results[results["Format"].str.contains("Album|Compilation|Comp", case=False, na=False)]
        else:
            results = results[results["Format"].str.contains(format_value, case=False, na=False)]

    album_data = []
    for release_id in results["release_id"].unique():
        group = results[results["release_id"] == release_id]
        album_title = group["Title"].iloc[0]
        album_artist = group["Artist"].iloc[0]
        album_format = group["Format"].iloc[0]
        is_compilation = "Compilation" in str(album_format) or "Comp" in str(album_format)
        display_artist = "Various Artists" if is_compilation else album_artist
        album_data.append({
            "release_id": release_id,
            "title": album_title,
            "artist": display_artist,
            "group": group
        })

    if sort_option == "Album Title":
        album_data = sorted(album_data, key=lambda x: x["title"].lower())
    else:
        album_data = sorted(album_data, key=lambda x: x["artist"].lower())

    st.write(f"Found {len(album_data)} album(s)")

    for album in album_data:
        release_id = album["release_id"]
        album_title = album["title"]
        album_artist = album["artist"]
        group = album["group"]

        # Get cover art
        cover_row = cover_overrides[cover_overrides["release_id"] == release_id]
        if not cover_row.empty:
            cover_url = cover_row["cover_url"].values[0]
        else:
            cover_url = fetch_discogs_cover(release_id)
            if cover_url:
                new_row = pd.DataFrame({"release_id": [release_id], "cover_url": [cover_url]})
                cover_overrides = pd.concat([cover_overrides, new_row], ignore_index=True)
                save_cover_override(cover_overrides)

        # Layout
        col1, col2 = st.columns([1, 6])
        with col1:
            if cover_url:
                st.image(cover_url, width=140)
            else:
                st.write("(No cover art available)")

            # Update Cover Art Button
            if st.button("Update Cover Art", key=f"update_{release_id}"):
                st.session_state[f"show_modal_{release_id}"] = True

            if st.session_state.get(f"show_modal_{release_id}", False):
                st.subheader(f"Update Cover Art for {album_title}")
                new_cover = st.text_input("Paste a new cover art URL:", key=f"cover_input_{release_id}")
                col_submit, col_reset = st.columns(2)
                with col_submit:
                    if st.button("Submit New Cover", key=f"submit_{release_id}"):
                        cover_overrides = cover_overrides[cover_overrides["release_id"] != release_id]
                        new_row = pd.DataFrame({"release_id": [release_id], "cover_url": [new_cover]})
                        cover_overrides = pd.concat([cover_overrides, new_row], ignore_index=True)
                        save_cover_override(cover_overrides)
                        st.success("Cover art updated successfully!")
                        st.session_state[f"show_modal_{release_id}"] = False
                with col_reset:
                    if st.button("Reset to Original Cover", key=f"reset_{release_id}"):
                        cover_overrides = cover_overrides[cover_overrides["release_id"] != release_id]
                        save_cover_override(cover_overrides)
                        st.success("Cover art reset to original!")
                        st.session_state[f"show_modal_{release_id}"] = False

        with col2:
            st.markdown(f"### {album_title}")
            st.markdown(f"**Artist:** {album_artist}")

            # Tracklist expander
            with st.expander("Click to view tracklist"):
                tracklist = group[["Track Title", "Artist", "CD", "Track Number"]].rename(
                    columns={
                        "Track Title": "Song",
                        "Artist": "Artist",
                        "CD": "Disc",
                        "Track Number": "Track"
                    }
                ).reset_index(drop=True)

                tracklist["Disc"] = tracklist["Disc"].fillna(1).replace("", 1)

                st.dataframe(tracklist, use_container_width=True, hide_index=True)

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
    token = st.secrets["DISCOGS_TOKEN"]
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
try:
    df = load_data()
except Exception as e:
    st.error(f"Error loading the CSV file: {e}")
    st.stop()

cover_overrides = load_cover_overrides()

# ------------------ Search Controls -----------------
search_term = st.text_input("Enter your search:", "")
search_type = st.radio("Search by:", ["Song Title", "Artist", "Album"], horizontal=True)

# Enhanced fuzzy filtering function
def fuzzy_filter(df, column, search_term, threshold=80):
    return df[df[column].apply(lambda x: fuzz.token_set_ratio(str(x), search_term) >= threshold)]

if search_term:
    if search_type == "Song Title":
        results = fuzzy_filter(df, "Track Title", search_term)
    elif search_type == "Artist":
        results = fuzzy_filter(df, "Artist", search_term)
    else:  # Album
        results = fuzzy_filter(df, "Title", search_term)

    # Prepare unique album sets
    album_release_ids = set(results[
        results["Format"].str.contains("Album", case=False, na=False)
        | results["Format"].str.contains("Compilation", case=False, na=False)
        | results["Format"].str.contains("Comp", case=False, na=False)
    ]["release_id"])

    single_release_ids = set(results[
        results["Format"].str.contains("Single", case=False, na=False)
    ]["release_id"])

    video_release_ids = set(results[
        results["Format"].str.contains("Video", case=False, na=False)
    ]["release_id"])

    all_release_ids = set(results["release_id"])

    # Format filter as radio buttons with album counts
    format_options = {
        f"All ({len(all_release_ids)})": "All",
        f"Album ({len(album_release_ids)})": "Album",
        f"Single ({len(single_release_ids)})": "Single",
        f"Video ({len(video_release_ids)})": "Video"
    }
    selected_format = st.radio("Filter by format (albums):", list(format_options.keys()), horizontal=True)
    selected_format_value = format_options[selected_format]

    # Apply format filtering to unique albums
    if selected_format_value == "Album":
        filtered_release_ids = album_release_ids
    elif selected_format_value == "Single":
        filtered_release_ids = single_release_ids
    elif selected_format_value == "Video":
        filtered_release_ids = video_release_ids
    else:
        filtered_release_ids = all_release_ids

    st.write(f"Found {len(filtered_release_ids)} album(s)")

    # Sort options
    sort_option = st.radio("Sort by:", ["Album Title", "Artist"], horizontal=True)

    album_data = []
    for release_id in filtered_release_ids:
        group = results[results["release_id"] == release_id]
        album_title = group["Title"].iloc[0]
        album_artist = group["Artist"].iloc[0]
        album_format = group["Format"].iloc[0]
        is_compilation = (
            "Compilation" in str(album_format)
            or "Comp" in str(album_format)
        )
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

        # Album card
        col1, col2 = st.columns([1, 6])
        with col1:
            if cover_url:
                st.image(cover_url, width=120)
            else:
                st.write("(No cover art available)")

        with col2:
            st.markdown(f"### {album_title}")
            st.markdown(f"**Artist:** {album_artist}")

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

            with st.expander("Click to view tracklist"):
                tracklist = group[["Track Title", "Artist", "CD", "Track Number"]].rename(
                    columns={
                        "Track Title": "Song",
                        "Artist": "Artist",
                        "CD": "Disc",
                        "Track Number": "Track"
                    }
                ).reset_index(drop=True)

                tracklist["Disc"] = tracklist["Disc"].fillna(1)
                tracklist["Disc"] = tracklist["Disc"].replace("", 1)

                st.dataframe(tracklist, use_container_width=True, hide_index=True)

if "last_sync" in st.session_state:
    st.success(st.session_state["last_sync"])

import streamlit as st
import pandas as pd
import requests
from io import StringIO
from fuzzywuzzy import fuzz
from github import Github

# --- CONFIG ---
st.set_page_config(page_title="Music Search App", layout="wide")

# --- SECRETS ---
DISCOGS_TOKEN = st.secrets["DISCOGS_API_TOKEN"]
GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
GITHUB_REPO = st.secrets["GITHUB_REPO"]
CSV_PATH = st.secrets["data_csv"]

# --- INITIAL SETUP ---
@st.cache_data(ttl=600)
def load_data():
    df = pd.read_csv(CSV_PATH)
    return df.fillna("")

@st.cache_data(ttl=600)
def load_cover_overrides():
    url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/cover_overrides.csv"
    try:
        overrides_df = pd.read_csv(url)
    except:
        overrides_df = pd.DataFrame(columns=["release_id", "cover_url"])
    return overrides_df

# --- FETCH COVER ---
def fetch_discogs_cover(release_id):
    api_url = f"https://api.discogs.com/releases/{release_id}"
    headers = {"Authorization": f"Discogs token={DISCOGS_TOKEN}"}
    response = requests.get(api_url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        return data.get("images", [{}])[0].get("uri", "")
    return ""

# --- SYNC COVER OVERRIDES TO GITHUB ---
def sync_to_github(df):
    g = Github(GITHUB_TOKEN)
    repo = g.get_repo(GITHUB_REPO)
    content_file = repo.get_contents("cover_overrides.csv")
    csv_buffer = StringIO()
    df.to_csv(csv_buffer, index=False)
    repo.update_file(
        content_file.path,
        "Batch sync cover_overrides.csv",
        csv_buffer.getvalue(),
        content_file.sha,
    )

# --- MAIN ---
df = load_data()
cover_overrides = load_cover_overrides()

st.title("🎵 Music Search App")

query = st.text_input("Enter your search:")
search_by = st.radio("Search by:", ["Song Title", "Artist", "Album"], horizontal=True)

format_filter = st.radio(
    "Filter by format (albums):",
    ["All", "Album", "Single", "Video"],
    horizontal=True,
)

sort_by = st.radio("Sort by:", ["Album Title", "Artist"], horizontal=True)

if query:
    if search_by == "Song Title":
        mask = df["Track Title"].str.contains(query, case=False, na=False)
    elif search_by == "Artist":
        mask = df["Artist"].str.contains(query, case=False, na=False)
    else:
        mask = df["Title"].str.contains(query, case=False, na=False)

    results = df[mask]

    # Format filter logic
    if format_filter != "All":
        results = results[results["Format"].str.contains(format_filter, case=False, na=False)]

    if results.empty:
        st.warning("No results found.")
    else:
        num_albums = results["Title"].nunique()
        num_tracks = len(results)

        st.write(f"**Found {num_tracks} track(s) across {num_albums} album(s)**")

        grouped = results.groupby("release_id")

        album_list = []
        for release_id, group in grouped:
            album_title = group["Title"].iloc[0]
            artist = group["Artist"].iloc[0]
            cover_row = cover_overrides[cover_overrides["release_id"] == release_id]

            if not cover_row.empty:
                cover_url = cover_row["cover_url"].values[0]
            else:
                cover_url = fetch_discogs_cover(release_id)
                if cover_url:
                    cover_overrides.loc[len(cover_overrides)] = [release_id, cover_url]

            album_list.append({
                "release_id": release_id,
                "album_title": album_title,
                "artist": artist,
                "cover_url": cover_url,
                "tracks": group[["Track Title", "Artist", "CD", "Track Number"]]
            })

        # Sort
        if sort_by == "Album Title":
            album_list = sorted(album_list, key=lambda x: x["album_title"].lower())
        else:
            album_list = sorted(album_list, key=lambda x: x["artist"].lower())

        # Display
        for album in album_list:
            cols = st.columns([1, 5])
            with cols[0]:
                if album["cover_url"]:
                    st.image(album["cover_url"], width=120)
                else:
                    st.write("No cover available")
                with st.expander("Update cover art"):
                    new_url = st.text_input(
                        f"Paste a new cover art URL for {album['album_title']}",
                        key=f"url_{album['release_id']}",
                    )
                    if st.button("Submit new cover art", key=f"submit_{album['release_id']}"):
                        # Update overrides df
                        idx = cover_overrides[cover_overrides["release_id"] == album["release_id"]].index
                        if not idx.empty:
                            cover_overrides.loc[idx, "cover_url"] = new_url
                        else:
                            cover_overrides.loc[len(cover_overrides)] = [album["release_id"], new_url]
                        sync_to_github(cover_overrides)
                        st.success("Cover art updated!")

            with cols[1]:
                st.subheader(f"{album['album_title']}")
                st.caption(f"Artist: {album['artist']}")
                with st.expander("Click to view tracklist"):
                    # Display table with compact Disc + Track columns
                    tracklist_df = album["tracks"].rename(columns={
                        "Track Title": "Song",
                        "Artist": "Artist",
                        "CD": "Disc",
                        "Track Number": "Track"
                    })
                    tracklist_df = tracklist_df.fillna("").astype(str)
                    st.table(tracklist_df[["Song", "Artist", "Disc", "Track"]])

        # Save batch sync to GitHub
        if not cover_overrides.empty:
            try:
                sync_to_github(cover_overrides)
            except Exception as e:
                st.warning(f"GitHub sync warning: {e}")

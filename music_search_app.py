import streamlit as st
import pandas as pd
import re
import requests
import time
import base64
from datetime import datetime

# Constants
CSV_FILE = 'expanded_discogs_tracklist.csv'
COVER_OVERRIDES_FILE = 'cover_overrides.csv'
DISCOGS_API_URL = 'https://api.discogs.com/releases/'
DISCOGS_API_TOKEN = st.secrets["DISCOGS_API_TOKEN"]  # 🔑 Paste your Discogs token here

# GitHub settings
GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]  # 🔑 Paste your GitHub personal access token here
GITHUB_REPO = 'DHancock80/music-search-app'
GITHUB_BRANCH = 'main'

@st.cache_data
def load_data():
    try:
        df = pd.read_csv(CSV_FILE, encoding='latin1')
        
        if 'cover_art' not in df.columns:
            df['cover_art'] = None
        
        try:
            overrides = pd.read_csv(COVER_OVERRIDES_FILE, encoding='latin1')
            if 'release_id' in overrides.columns and 'cover_url' in overrides.columns:
                overrides = overrides.drop_duplicates(subset='release_id', keep='last')
                df = df.merge(overrides, on='release_id', how='left', suffixes=('', '_override'))
                df['cover_art_final'] = df['cover_url'].combine_first(df['cover_art'])
            else:
                df['cover_art_final'] = df['cover_art']
        except FileNotFoundError:
            st.warning("Cover overrides file not found. Proceeding without overrides.")
            df['cover_art_final'] = df['cover_art']
            
    except Exception as e:
        st.error(f"Error loading the CSV file: {e}")
        df = pd.DataFrame()
    return df

def clean_artist_name(artist):
    if pd.isna(artist):
        return ''
    artist = artist.lower()
    artist = re.sub(r'[\*\(\)\[\]#]', '', artist)
    artist = re.sub(r'\s*(feat\.|ft\.|featuring)\s*', ' ', artist)
    artist = artist.replace('&', ' ').replace(',', ' ')
    artist = re.sub(r'\s+', ' ', artist).strip()
    return artist

def search(df, query, search_type, format_filter):
    if df.empty:
        return df
    query = query.lower().strip()
    results = df.copy()

    if search_type == 'Song Title':
        results = results[results['Track Title'].str.lower().str.contains(query, na=False)]
    elif search_type == 'Artist':
        results['artist_clean'] = results['Artist'].apply(clean_artist_name)
        results = results[results['artist_clean'].str.contains(query, na=False)]
    elif search_type == 'Album':
        results = results[results['Title'].str.lower().str.contains(query, na=False)]

    if format_filter != 'All':
        if 'Format' in results.columns:
            results = results[results['Format'].str.lower() == format_filter.lower()]

    return results

def fetch_discogs_cover(release_id):
    headers = {"Authorization": f"Discogs token={DISCOGS_API_TOKEN}"}
    try:
        response = requests.get(f"{DISCOGS_API_URL}{release_id}", headers=headers)
        if response.status_code == 200:
            data = response.json()
            if 'images' in data and len(data['images']) > 0:
                return data['images'][0]['uri']
    except Exception as e:
        st.write(f"Error fetching release {release_id}: {e}")
    return None

def upload_to_github(file_path, repo, token, branch, commit_message):
    api_url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    with open(file_path, "rb") as f:
        content = f.read()
    content_b64 = base64.b64encode(content).decode()

    # Get the current file SHA (if it exists)
    get_resp = requests.get(api_url, headers=headers, params={"ref": branch})
    if get_resp.status_code == 200:
        sha = get_resp.json()['sha']
    else:
        sha = None

    data = {
        "message": commit_message,
        "content": content_b64,
        "branch": branch
    }
    if sha:
        data["sha"] = sha

    response = requests.put(api_url, headers=headers, json=data)
    return response

# Streamlit app
st.title('🎵 Music Search App')

# Debug expander
with st.expander("📂 View current cover_overrides.csv (debugging)"):
    try:
        overrides = pd.read_csv(COVER_OVERRIDES_FILE, encoding='latin1')
        st.dataframe(overrides)
    except FileNotFoundError:
        st.info("No cover_overrides.csv file found yet.")

df = load_data()

if df.empty:
    st.stop()

search_query = st.text_input('Enter your search:', '')
search_type = st.radio('Search by:', ['Song Title', 'Artist', 'Album'], horizontal=True)
format_filter = st.selectbox('Format filter:', ['All', 'Album', 'Single'])

if search_query:
    results = search(df, search_query, search_type, format_filter)

    unique_results = results.drop_duplicates()
    st.write(f"### Found {len(unique_results)} result(s)")

    if unique_results.empty:
        st.info("No results found.")
    else:
        cover_cache = {}
        grouped = results.groupby('release_id')

        for release_id, group in grouped:
            first_row = group.iloc[0]
            album_title = first_row['Title']
            artist = first_row['Artist']
            cover = first_row.get('cover_art_final')

            # Check if cover is missing
            if (pd.isna(cover) or str(cover).strip() == '') and pd.notna(release_id):
                if release_id not in cover_cache:
                    time.sleep(0.2)
                    cover = fetch_discogs_cover(release_id)
                    if cover:
                        st.write(f"Fetched cover for release_id {release_id} ✅")
                        new_entry = pd.DataFrame([{'release_id': release_id, 'cover_url': cover}])
                        try:
                            existing = pd.read_csv(COVER_OVERRIDES_FILE, encoding='latin1')
                            if 'release_id' not in existing.columns or 'cover_url' not in existing.columns:
                                existing = pd.DataFrame(columns=['release_id', 'cover_url'])
                            existing = existing[existing['release_id'] != release_id]
                            updated = pd.concat([existing, new_entry], ignore_index=True)
                        except FileNotFoundError:
                            updated = new_entry

                        updated.to_csv(COVER_OVERRIDES_FILE, index=False, encoding='latin1')
                        # 🚀 Sync to GitHub
                        commit_message = f"Auto-update cover_overrides.csv ({datetime.utcnow().isoformat()} UTC)"
                        gh_response = upload_to_github(
                            COVER_OVERRIDES_FILE,
                            GITHUB_REPO,
                            GITHUB_TOKEN,
                            GITHUB_BRANCH,
                            commit_message
                        )
                        if gh_response.status_code in [200, 201]:
                            st.success("✅ cover_overrides.csv synced to GitHub.")
                        else:
                            st.error(f"❌ GitHub sync failed: {gh_response.status_code} - {gh_response.text}")
                    else:
                        st.write(f"Failed to fetch cover for release_id {release_id} ❌")
                    cover_cache[release_id] = cover
                else:
                    cover = cover_cache[release_id]
            else:
                cover_cache[release_id] = cover

            with st.container():
                cols = st.columns([1, 5])
                with cols[0]:
                    if cover:
                        st.markdown(
                            f'<a href="{cover}" target="_blank">'
                            f'<img src="{cover}" width="120"></a>',
                            unsafe_allow_html=True
                        )
                    else:
                        st.text("No cover art")

                with cols[1]:
                    st.markdown(f"### {album_title}")
                    st.markdown(f"**Artist:** {artist}")

                with st.expander("Update Cover Art"):
                    new_url = st.text_input("Paste a new cover art URL:", key=f"url_{release_id}")
                    submit_col, reset_col = st.columns(2)

                    with submit_col:
                        if st.button("Submit new cover art", key=f"submit_{release_id}"):
                            if new_url:
                                new_entry = pd.DataFrame([{'release_id': release_id, 'cover_url': new_url}])
                                try:
                                    existing = pd.read_csv(COVER_OVERRIDES_FILE, encoding='latin1')
                                    if 'release_id' not in existing.columns or 'cover_url' not in existing.columns:
                                        existing = pd.DataFrame(columns=['release_id', 'cover_url'])
                                    existing = existing[existing['release_id'] != release_id]
                                    updated = pd.concat([existing, new_entry], ignore_index=True)
                                except FileNotFoundError:
                                    updated = new_entry

                                updated.to_csv(COVER_OVERRIDES_FILE, index=False, encoding='latin1')
                                # 🚀 Sync to GitHub
                                commit_message = f"Manual update cover_overrides.csv ({datetime.utcnow().isoformat()} UTC)"
                                gh_response = upload_to_github(
                                    COVER_OVERRIDES_FILE,
                                    GITHUB_REPO,
                                    GITHUB_TOKEN,
                                    GITHUB_BRANCH,
                                    commit_message
                                )
                                if gh_response.status_code in [200, 201]:
                                    st.success("Cover art override saved & synced to GitHub!")
                                    st.cache_data.clear()
                                    st.rerun()
                                else:
                                    st.error(f"GitHub sync failed: {gh_response.status_code} - {gh_response.text}")
                            else:
                                st.error("Please enter a valid URL.")

                    with reset_col:
                        if st.button("Reset to original cover", key=f"reset_{release_id}"):
                            try:
                                existing = pd.read_csv(COVER_OVERRIDES_FILE, encoding='latin1')
                                if 'release_id' not in existing.columns or 'cover_url' not in existing.columns:
                                    existing = pd.DataFrame(columns=['release_id', 'cover_url'])
                                updated = existing[existing['release_id'] != release_id]
                                updated.to_csv(COVER_OVERRIDES_FILE, index=False, encoding='latin1')
                                # 🚀 Sync to GitHub
                                commit_message = f"Reset cover_overrides.csv ({datetime.utcnow().isoformat()} UTC)"
                                gh_response = upload_to_github(
                                    COVER_OVERRIDES_FILE,
                                    GITHUB_REPO,
                                    GITHUB_TOKEN,
                                    GITHUB_BRANCH,
                                    commit_message
                                )
                                if gh_response.status_code in [200, 201]:
                                    st.success("Cover override removed & synced to GitHub!")
                                    st.cache_data.clear()
                                    st.rerun()
                                else:
                                    st.error(f"GitHub sync failed: {gh_response.status_code} - {gh_response.text}")
                            except FileNotFoundError:
                                st.success("Cover override removed locally.")
                                st.cache_data.clear()
                                st.rerun()

                tracklist = group[[
                    'Track Title', 'Artist', 'CD', 'Track Number', 'Format'
                ]].rename(columns={
                    'Track Title': 'Song',
                    'CD': 'Disc',
                    'Track Number': 'Track',
                }).reset_index(drop=True)

                st.dataframe(
                    tracklist,
                    use_container_width=True,
                    hide_index=True,
                )

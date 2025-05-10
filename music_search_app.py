# Music Search App – Fully Functional Final Version

import streamlit as st
import pandas as pd
import re
import requests
import time
import base64
from datetime import datetime
from rapidfuzz import process

# Constants
CSV_FILE = 'expanded_discogs_tracklist.csv'
COVER_OVERRIDES_FILE = 'cover_overrides.csv'
DISCOGS_API_TOKEN = st.secrets["DISCOGS_API_TOKEN"]
GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
GITHUB_REPO = 'DHancock80/music-search-app'
GITHUB_BRANCH = 'main'

# Load and cache data
@st.cache_data
def load_data():
    try:
        df = pd.read_csv(CSV_FILE, encoding='latin1')
        if 'cover_art' not in df.columns:
            df['cover_art'] = None
        try:
            overrides = pd.read_csv(COVER_OVERRIDES_FILE, encoding='latin1')
            overrides = overrides.drop_duplicates(subset='release_id', keep='last')
            df = df.merge(overrides, on='release_id', how='left', suffixes=('', '_override'))
            df['cover_art_final'] = df['cover_url'].combine_first(df['cover_art'])
        except:
            df['cover_art_final'] = df['cover_art']
    except Exception as e:
        st.error(f"Error loading CSV: {e}")
        df = pd.DataFrame()
    return df

# Helper functions
def clean_text(text):
    if pd.isna(text): return ''
    return re.sub(r'[^\w\s]', '', text).strip().lower()

def fuzzy_search(df, query, field):
    query = clean_text(query)
    choices = df[field].dropna().unique()
    matches = process.extract(query, choices, limit=25, scorer=process.fuzz.WRatio)
    match_texts = [m[0] for m in matches if m[1] > 65]
    return df[df[field].isin(match_texts)]

def fetch_discogs_cover(release_id):
    headers = {"Authorization": f"Discogs token={DISCOGS_API_TOKEN}"}
    try:
        res = requests.get(f"https://api.discogs.com/releases/{release_id}", headers=headers)
        if res.status_code == 200:
            data = res.json()
            if 'images' in data and data['images']:
                return data['images'][0]['uri']
    except Exception as e:
        print(f"Fetch error {release_id}: {e}")
    return None

def upload_to_github(file_path, repo, token, branch, message):
    url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    with open(file_path, "rb") as f:
        content = base64.b64encode(f.read()).decode()
    sha = None
    r = requests.get(url, headers=headers, params={"ref": branch})
    if r.status_code == 200:
        sha = r.json().get('sha')
    data = {"message": message, "content": content, "branch": branch}
    if sha: data["sha"] = sha
    return requests.put(url, headers=headers, json=data)

# App UI
st.set_page_config(page_title="Music Search App")
st.title("Music Search App")
df = load_data()
if df.empty: st.stop()

search_type = st.radio("Search by:", ["Song Title", "Artist", "Album"], horizontal=True)
query = st.text_input("Start typing to search:", key="search_query")
if st.button("New Search"):
    st.session_state.search_query = ''
    st.experimental_rerun()

search_field = {'Song Title': 'Track Title', 'Artist': 'Artist', 'Album': 'Title'}[search_type]

if query:
    results = fuzzy_search(df, query, search_field)
else:
    results = pd.DataFrame()

# Format breakdown counts
if not results.empty:
    format_counts = {
        'All': len(results),
        'Album': len(results[results['Format'].str.lower().isin(['album', 'compilation', 'comp'])]),
        'Single': len(results[results['Format'].str.lower() == 'single']),
        'Video': len(results[results['Format'].str.lower() == 'video'])
    }
else:
    format_counts = {k: 0 for k in ['All', 'Album', 'Single', 'Video']}

selected_format = st.radio("Filter by format:", [f"{k} ({v})" for k, v in format_counts.items()], horizontal=True)
format_key = selected_format.split()[0]

if format_key != 'All':
    if format_key == 'Album':
        results = results[results['Format'].str.lower().isin(['album', 'compilation', 'comp'])]
    else:
        results = results[results['Format'].str.lower() == format_key.lower()]

if not results.empty:
    st.write(f"### Found {len(results)} track(s) across {results['Title'].nunique()} album(s)")
    new_covers = []
    for release_id, group in results.groupby('release_id'):
        row = group.iloc[0]
        album = row['Title']
        artist = row['Artist']
        cover = row.get('cover_art_final')
        if pd.isna(cover):
            cover = fetch_discogs_cover(release_id)
            if cover:
                new_covers.append({'release_id': release_id, 'cover_url': cover})
        cols = st.columns([1, 5])
        with cols[0]:
            if cover:
                st.markdown(f'<a href="{cover}" target="_blank"><img src="{cover}" width="120"></a>', unsafe_allow_html=True)
            else:
                st.text("No cover")
            if st.button("Update Cover Art", key=f"show_{release_id}"):
                st.session_state[f'show_modal_{release_id}'] = not st.session_state.get(f'show_modal_{release_id}', False)
        with cols[1]:
            st.markdown(f"### {album}")
            st.markdown(f"**Artist:** {artist if 'various' not in artist.lower() else 'Various Artists'}")
            if st.session_state.get(f'show_modal_{release_id}', False):
                new_url = st.text_input("New cover URL:", key=f"url_{release_id}")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Submit", key=f"submit_{release_id}"):
                        new_entry = pd.DataFrame([{'release_id': release_id, 'cover_url': new_url}])
                        try:
                            existing = pd.read_csv(COVER_OVERRIDES_FILE, encoding='latin1')
                            existing = existing[existing['release_id'] != release_id]
                            updated = pd.concat([existing, new_entry], ignore_index=True)
                        except:
                            updated = new_entry
                        updated.to_csv(COVER_OVERRIDES_FILE, index=False, encoding='latin1')
                        upload_to_github(COVER_OVERRIDES_FILE, GITHUB_REPO, GITHUB_TOKEN, GITHUB_BRANCH, f"Manual update for {release_id}")
                        st.success("Cover updated and synced.")
                        st.experimental_rerun()
                with col2:
                    if st.button("Reset", key=f"reset_{release_id}"):
                        try:
                            existing = pd.read_csv(COVER_OVERRIDES_FILE, encoding='latin1')
                            updated = existing[existing['release_id'] != release_id]
                            updated.to_csv(COVER_OVERRIDES_FILE, index=False, encoding='latin1')
                            upload_to_github(COVER_OVERRIDES_FILE, GITHUB_REPO, GITHUB_TOKEN, GITHUB_BRANCH, f"Reset for {release_id}")
                            st.success("Cover reset.")
                            st.experimental_rerun()
                        except:
                            st.warning("Nothing to reset.")
        with st.expander("Click to view tracklist"):
            tracklist = group[['Track Title', 'Artist', 'CD', 'Track Number']]
            tracklist.columns = ['Song', 'Artist', 'Disc', 'Track']
            st.dataframe(tracklist, use_container_width=True, hide_index=True)

    # Batch save
    if new_covers:
        try:
            existing = pd.read_csv(COVER_OVERRIDES_FILE, encoding='latin1')
            for entry in new_covers:
                existing = existing[existing['release_id'] != entry['release_id']]
                existing = pd.concat([existing, pd.DataFrame([entry])], ignore_index=True)
        except:
            existing = pd.DataFrame(new_covers)
        existing.to_csv(COVER_OVERRIDES_FILE, index=False, encoding='latin1')
        upload_to_github(COVER_OVERRIDES_FILE, GITHUB_REPO, GITHUB_TOKEN, GITHUB_BRANCH, f"Batch sync {datetime.utcnow().isoformat()} UTC")

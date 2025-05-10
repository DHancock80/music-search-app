# Music Search App - Final Version with Full Functionality

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

def clean_artist_name(artist):
    if pd.isna(artist): return ''
    artist = re.sub(r'\s*(feat\.|ft\.|featuring)\s*', ' ', artist, flags=re.I)
    artist = re.sub(r'[^\w\s]', '', artist)
    return artist.strip().lower()

def fuzzy_search(df, query, search_type):
    query = query.lower().strip()
    if search_type == 'Song Title':
        return df[df['Track Title'].str.lower().str.contains(query, na=False)]
    elif search_type == 'Artist':
        df['artist_clean'] = df['Artist'].apply(clean_artist_name)
        return df[df['artist_clean'].str.contains(query, na=False)]
    elif search_type == 'Album':
        return df[df['Title'].str.lower().str.contains(query, na=False)]
    return df

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

# UI
st.title("Music Search App")
df = load_data()
if df.empty: st.stop()

album_list = df['Title'].dropna().unique()
artist_list = df['Artist'].dropna().unique()
song_list = df['Track Title'].dropna().unique()

search_type = st.radio('Search by:', ['Song Title', 'Artist', 'Album'], horizontal=True)
suggestions = song_list if search_type == 'Song Title' else artist_list if search_type == 'Artist' else album_list
query = st.text_input('Enter your search:', '', placeholder='Start typing...')

if query:
    matches = process.extract(query, suggestions, limit=5)
    if matches: query = st.selectbox('Suggestions:', [query] + [m[0] for m in matches])

if st.button("❌ Clear Search"):
    st.rerun()

results = fuzzy_search(df, query, search_type) if query else pd.DataFrame()

format_counts = {
    'All': len(results),
    'Album': len(results[results['Format'].str.lower().isin(['album', 'compilation', 'comp'])]),
    'Single': len(results[results['Format'].str.lower() == 'single']),
    'Video': len(results[results['Format'].str.lower() == 'video'])
} if not results.empty else {k: 0 for k in ['All', 'Album', 'Single', 'Video']}

format_filter = st.radio("Filter by format:", [f"{k} ({v})" for k, v in format_counts.items()], horizontal=True)
selected_format = format_filter.split()[0]

if selected_format != 'All':
    results = results[results['Format'].str.lower().isin(
        ['album', 'compilation', 'comp'] if selected_format == 'Album' else [selected_format.lower()]
    )]

if not results.empty:
    st.write(f"### Found {len(results)} track(s) across {results['Title'].nunique()} album(s)")
    new_covers = []
    for release_id, group in results.groupby('release_id'):
        row = group.iloc[0]
        album, artist, cover = row['Title'], row['Artist'], row.get('cover_art_final')
        if pd.isna(cover):
            cover = fetch_discogs_cover(release_id)
            if cover: new_covers.append({'release_id': release_id, 'cover_url': cover})
        cols = st.columns([1, 5])
        with cols[0]:
            if cover:
                st.markdown(f'<a href="{cover}" target="_blank"><img src="{cover}" width="120"></a>', unsafe_allow_html=True)
            else:
                st.text("No cover")
            link_key = f"link_{release_id}"
            if st.button("🖼️ Update Cover Art", key=link_key):
                st.session_state[link_key + '_show'] = not st.session_state.get(link_key + '_show', False)
        with cols[1]:
            st.markdown(f"### {album}")
            st.markdown(f"**Artist:** {artist}")
            if st.session_state.get(link_key + '_show', False):
                st.markdown("---")
                new_url = st.text_input("New cover URL:", key=f"url_{release_id}")
                submit, reset = st.columns(2)
                with submit:
                    if st.button("Submit", key=f"submit_{release_id}"):
                        df_new = pd.DataFrame([{'release_id': release_id, 'cover_url': new_url}])
                        try:
                            existing = pd.read_csv(COVER_OVERRIDES_FILE, encoding='latin1')
                            existing = existing[existing['release_id'] != release_id]
                            updated = pd.concat([existing, df_new], ignore_index=True)
                        except:
                            updated = df_new
                        updated.to_csv(COVER_OVERRIDES_FILE, index=False, encoding='latin1')
                        upload_to_github(COVER_OVERRIDES_FILE, GITHUB_REPO, GITHUB_TOKEN, GITHUB_BRANCH, f"Update {release_id}")
                        st.success("Saved and synced to GitHub!")
                        st.rerun()
                with reset:
                    if st.button("Reset", key=f"reset_{release_id}"):
                        try:
                            existing = pd.read_csv(COVER_OVERRIDES_FILE, encoding='latin1')
                            updated = existing[existing['release_id'] != release_id]
                            updated.to_csv(COVER_OVERRIDES_FILE, index=False, encoding='latin1')
                            upload_to_github(COVER_OVERRIDES_FILE, GITHUB_REPO, GITHUB_TOKEN, GITHUB_BRANCH, f"Reset {release_id}")
                            st.success("Cover reset!")
                            st.rerun()
                        except:
                            st.warning("No override to remove.")
        with st.expander("Click to view tracklist"):
            tracklist = group[['Track Title', 'Artist', 'CD', 'Track Number']]
            tracklist.columns = ['Song', 'Artist', 'Disc', 'Track']
            st.dataframe(tracklist, use_container_width=True, hide_index=True)
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

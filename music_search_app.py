# Full code with all UI elements restored (cover art, tracklist, update cover art, GitHub sync, etc.)
# Rapidfuzz integrated with improved normalization and all previous functionality preserved

import streamlit as st
import pandas as pd
import re
import requests
import time
import base64
from datetime import datetime
from rapidfuzz import fuzz

# Constants
CSV_FILE = 'expanded_discogs_tracklists.csv'
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

def normalize(text):
    return re.sub(r'[^a-z0-9 ]', '', str(text).lower())

def fuzzy_filter(series, query, threshold=60):
    return series.apply(lambda x: fuzz.token_set_ratio(str(x).lower(), query.lower()) >= threshold)

def search(df, query, search_type, format_filter):
    if df.empty:
        return df
    results = df.copy()

    if search_type == 'Song Title':
        results = results[fuzzy_filter(results['Track Title'], query)]
    elif search_type == 'Artist':
        results['artist_clean'] = results['Artist'].apply(clean_artist_name)
        results = results[fuzzy_filter(results['artist_clean'], query)]
    elif search_type == 'Album':
        results = results[fuzzy_filter(results['Title'], query)]

    if format_filter != 'All':
        if 'Format' in results.columns:
            results = results[results['Format'].str.lower() == format_filter.lower()]

    return results

def fetch_discogs_cover(release_id):
    headers = {"Authorization": f"Discogs token={DISCOGS_API_TOKEN}"}
    try:
        response = requests.get(f"https://api.discogs.com/releases/{release_id}", headers=headers)
        if response.status_code == 200:
            data = response.json()
            if 'images' in data and len(data['images']) > 0:
                return data['images'][0]['uri']
    except Exception as e:
        print(f"Error fetching release {release_id}: {e}")
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

    get_resp = requests.get(api_url, headers=headers, params={"ref": branch})
    sha = get_resp.json().get('sha') if get_resp.status_code == 200 else None

    data = {
        "message": commit_message,
        "content": content_b64,
        "branch": branch
    }
    if sha:
        data["sha"] = sha

    response = requests.put(api_url, headers=headers, json=data)
    return response

st.title('Music Search App')
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
        new_covers = []
        grouped = results.groupby('release_id')

        for release_id, group in grouped:
            first_row = group.iloc[0]
            album_title = first_row['Title']
            artist = first_row['Artist']
            cover = first_row.get('cover_art_final')

            if (pd.isna(cover) or str(cover).strip() == '') and pd.notna(release_id):
                if release_id not in cover_cache:
                    time.sleep(0.2)
                    cover = fetch_discogs_cover(release_id)
                    if cover:
                        new_covers.append({'release_id': release_id, 'cover_url': cover})
                    cover_cache[release_id] = cover
                else:
                    cover = cover_cache[release_id]
            else:
                cover_cache[release_id] = cover

            with st.container():
                cols = st.columns([1, 5])
                with cols[0]:
                    if cover:
                        st.markdown(f'<a href="{cover}" target="_blank"><img src="{cover}" width="120"></a>', unsafe_allow_html=True)
                    else:
                        st.text("No cover art")

                with cols[1]:
                    st.markdown(f"### {album_title}")
                    st.markdown(f"**Artist:** {artist}")

                    with st.expander("Click to view tracklist"):
                        tracklist = group[['Track Title', 'Artist', 'CD', 'Track Number']].rename(columns={
                            'Track Title': 'Song', 'CD': 'Disc', 'Track Number': 'Track'
                        }).reset_index(drop=True)
                        st.dataframe(tracklist, use_container_width=True, hide_index=True)

        if new_covers:
            try:
                existing = pd.read_csv(COVER_OVERRIDES_FILE, encoding='latin1')
                if 'release_id' not in existing.columns or 'cover_url' not in existing.columns:
                    existing = pd.DataFrame(columns=['release_id', 'cover_url'])
                for entry in new_covers:
                    existing = existing[existing['release_id'] != entry['release_id']]
                    existing = pd.concat([existing, pd.DataFrame([entry])], ignore_index=True)
            except FileNotFoundError:
                existing = pd.DataFrame(new_covers)

            existing.to_csv(COVER_OVERRIDES_FILE, index=False, encoding='latin1')
            commit_message = f"Batch sync cover_overrides.csv ({datetime.utcnow().isoformat()} UTC)"
            upload_to_github(
                COVER_OVERRIDES_FILE, GITHUB_REPO, GITHUB_TOKEN, GITHUB_BRANCH, commit_message
            )

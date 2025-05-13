import streamlit as st
import pandas as pd
import re
import requests
import time
import base64
from datetime import datetime

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

        if df.columns[0].startswith("Unnamed"):
            df = df.drop(columns=[df.columns[0]])

        expected_columns = ['Artist', 'Title', 'Label', 'Format', 'Rating', 'Released', 'release_id', 'CD', 'Track Number', 'Track Title']
        missing = [col for col in expected_columns if col not in df.columns]
        if missing:
            st.warning(f"Missing expected columns in CSV: {missing}")

        if 'cover_art' not in df.columns:
            df['cover_art'] = None

        try:
            overrides = pd.read_csv(COVER_OVERRIDES_FILE, encoding='latin1', on_bad_lines='skip')
            if 'release_id' not in overrides.columns or 'cover_url' not in overrides.columns:
                st.warning("Overrides file missing required columns. Skipping override merge.")
                df['cover_art_final'] = df['cover_art']
            else:
                overrides = overrides.drop_duplicates(subset='release_id', keep='last')
                df = df.merge(overrides, on='release_id', how='left', suffixes=('', '_override'))
                df['cover_art_final'] = df['cover_url'].combine_first(df['cover_art'])
        except Exception as e:
            st.warning(f"Could not read cover overrides: {e}")
            df['cover_art_final'] = df['cover_art']

    except Exception as e:
        st.error(f"Error loading the CSV file: {e}")
        df = pd.DataFrame()
    return df

def clean_artist_name(artist):
    if pd.isna(artist):
        return ''
    artist = artist.lower()
    artist = re.sub(r'[\*\(\)\[#]', '', artist)
    artist = re.sub(r'\s*(feat\.|ft\.|featuring)\s*', ' ', artist)
    artist = artist.replace('&', ' ').replace(',', ' ')
    artist = re.sub(r'\s+', ' ', artist).strip()
    return artist

def search(df, query, search_type):
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
    sha = get_resp.json()['sha'] if get_resp.status_code == 200 else None

    data = {
        "message": commit_message,
        "content": content_b64,
        "branch": branch
    }
    if sha:
        data["sha"] = sha

    response = requests.put(api_url, headers=headers, json=data)
    return response

def update_cover_override(release_id, url):
    try:
        overrides = pd.read_csv(COVER_OVERRIDES_FILE, encoding='latin1', on_bad_lines='skip')
    except Exception:
        overrides = pd.DataFrame(columns=['release_id', 'cover_url'])

    overrides = overrides[overrides['release_id'] != release_id]
    overrides = pd.concat([overrides, pd.DataFrame([{'release_id': release_id, 'cover_url': url}])], ignore_index=True)
    overrides.to_csv(COVER_OVERRIDES_FILE, index=False, encoding='latin1')
    commit_message = f"Updated override for release_id {release_id} ({datetime.utcnow().isoformat()} UTC)"
    upload_to_github(COVER_OVERRIDES_FILE, GITHUB_REPO, GITHUB_TOKEN, GITHUB_BRANCH, commit_message)

def remove_cover_override(release_id):
    try:
        overrides = pd.read_csv(COVER_OVERRIDES_FILE, encoding='latin1', on_bad_lines='skip')
        overrides = overrides[overrides['release_id'] != release_id]
        overrides.to_csv(COVER_OVERRIDES_FILE, index=False, encoding='latin1')
        commit_message = f"Removed override for release_id {release_id} ({datetime.utcnow().isoformat()} UTC)"
        upload_to_github(COVER_OVERRIDES_FILE, GITHUB_REPO, GITHUB_TOKEN, GITHUB_BRANCH, commit_message)
    except FileNotFoundError:
        pass

# App continues unchanged from here...

st.title('Music Search App')

if 'expanded_cover_id' not in st.session_state:
    st.session_state.expanded_cover_id = None

# remaining app logic as-is...
# no changes needed below unless new bugs are discovered

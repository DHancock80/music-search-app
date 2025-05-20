import pandas as pd
import base64
import requests
import os
import shutil
import re
import unicodedata
from datetime import datetime
import streamlit as st
from rapidfuzz import fuzz

# Constants
DISCOGS_ICON_WHITE = 'https://raw.githubusercontent.com/DHancock80/music-search-app/main/discogs_white.png'
DISCOGS_ICON_BLACK = 'https://raw.githubusercontent.com/DHancock80/music-search-app/main/discogs_black.png'
CSV_FILE = 'expanded_discogs_tracklists.csv'
COVER_OVERRIDES_FILE = 'cover_overrides.csv'
BACKUP_FOLDER = 'backups'
PLACEHOLDER_COVER = 'https://upload.wikimedia.org/wikipedia/commons/thumb/6/65/No-Image-Placeholder.svg/2048px-No-Image-Placeholder.svg.png'

missing_secrets = [k for k in ["DISCOGS_API_TOKEN", "GITHUB_TOKEN", "GITHUB_REPO"] if k not in st.secrets]
if missing_secrets:
    st.error("🔐 One or more required Streamlit secrets are missing. Please check your settings.")
    st.stop()

DISCOGS_API_TOKEN = st.secrets["DISCOGS_API_TOKEN"]
GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
GITHUB_REPO = st.secrets["GITHUB_REPO"]
GITHUB_BRANCH = 'main'

if 'open_expander_id' not in st.session_state:
    st.session_state['open_expander_id'] = None
if 'results_summary' not in st.session_state:
    st.session_state['results_summary'] = {'All': 0, 'Album': 0, 'Single': 0, 'Video': 0}


def normalize(text):
    if pd.isna(text): return ''
    text = str(text).lower()
    text = ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c))
    text = re.sub(r'[^a-z0-9]+', ' ', text)
    return text.strip()


def fuzzy_match(text, query, threshold=85):
    return fuzz.partial_ratio(normalize(text), normalize(query)) >= threshold


@st.cache_data
def get_auto_suggestions(df, field, query, limit=10):
    norm_query = normalize(query)
    matches = df[field].dropna().unique()
    ranked = sorted(matches, key=lambda x: fuzz.partial_ratio(norm_query, normalize(x)), reverse=True)
    return ranked[:limit]


@st.cache_data
def load_data():
    try:
        df = pd.read_csv(CSV_FILE, encoding='utf-8', on_bad_lines='skip')
        if 'cover_art' not in df.columns:
            df['cover_art'] = None
        try:
            overrides = pd.read_csv(COVER_OVERRIDES_FILE, encoding='utf-8', on_bad_lines='skip')
            overrides.columns = overrides.columns.str.strip().str.lower()
            if not {'release_id', 'cover_url'}.issubset(overrides.columns):
                df['cover_art_final'] = df['cover_art']
            else:
                overrides = overrides.drop_duplicates(subset='release_id', keep='last')
                df = df.merge(overrides, on='release_id', how='left', suffixes=('', '_override'))
                df['cover_art_final'] = df['cover_url'].combine_first(df['cover_art'])
        except:
            df['cover_art_final'] = df['cover_art']
    except:
        df = pd.DataFrame()
    return df


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


def update_cover_override(release_id, new_url):
    try:
        if not os.path.exists(BACKUP_FOLDER):
            os.makedirs(BACKUP_FOLDER)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = os.path.join(BACKUP_FOLDER, f"cover_overrides_backup_{timestamp}.csv")
        shutil.copy(COVER_OVERRIDES_FILE, backup_file)
        backups = sorted(os.listdir(BACKUP_FOLDER))
        if len(backups) > 10:
            os.remove(os.path.join(BACKUP_FOLDER, backups[0]))
    except Exception as e:
        st.error(f"Backup failed: {e}")

    try:
        overrides = pd.read_csv(COVER_OVERRIDES_FILE, encoding='utf-8')
        overrides.columns = overrides.columns.str.strip().str.lower()
    except:
        overrides = pd.DataFrame(columns=['release_id', 'cover_url'])

    overrides = overrides[overrides['release_id'] != release_id]
    overrides = pd.concat([overrides, pd.DataFrame([{'release_id': release_id, 'cover_url': new_url}])], ignore_index=True)
    overrides.to_csv(COVER_OVERRIDES_FILE, index=False, encoding='utf-8')
    upload_to_github(COVER_OVERRIDES_FILE, GITHUB_REPO, GITHUB_TOKEN, GITHUB_BRANCH, f"Update cover for {release_id}")
    st.success("✅ Custom cover art uploaded and synced to GitHub!")
    st.cache_data.clear()
    st.rerun()


def reset_cover_override(release_id):
    try:
        overrides = pd.read_csv(COVER_OVERRIDES_FILE, encoding='utf-8')
        overrides.columns = overrides.columns.str.strip().str.lower()
        overrides = overrides[overrides['release_id'] != release_id]
        overrides.to_csv(COVER_OVERRIDES_FILE, index=False, encoding='utf-8')
        upload_to_github(COVER_OVERRIDES_FILE, GITHUB_REPO, GITHUB_TOKEN, GITHUB_BRANCH, f"Reset cover for {release_id}")
        st.success("✅ Reverted to original cover art and synced to GitHub!")
        st.cache_data.clear()
        st.rerun()
    except Exception as e:
        st.error(f"Reset failed: {e}")


# === UI Enhancements and Sorting Logic ===
df = load_data()
search_type = st.radio("Search by:", ["Song Title", "Artist", "Album"], horizontal=True)
query = st.text_input("Enter your search:", "")
sort_option = st.selectbox("Sort results by:", ["Alphabetical (A-Z)", "Release Year (Newest First)", "Release Year (Oldest First)"])

# Auto suggestions (before search)
if query and len(query) >= 3:
    suggestions = get_auto_suggestions(df, {'Song Title': 'Track Title', 'Artist': 'Artist', 'Album': 'Title'}[search_type], query)
    if suggestions:
        st.caption("Suggestions:")
        st.write(", ".join(suggestions))

# Apply search
if query:
    field_map = {'Song Title': 'Track Title', 'Artist': 'Artist', 'Album': 'Title'}
    field = field_map[search_type]
    results = df[df[field].apply(lambda x: fuzzy_match(str(x), query))]

    # Sort results
    if sort_option == "Alphabetical (A-Z)":
        results = results.sort_values(by="Title", na_position="last")
    elif sort_option == "Release Year (Newest First)":
        results = results.sort_values(by="Year", ascending=False, na_position="last")
    elif sort_option == "Release Year (Oldest First)":
        results = results.sort_values(by="Year", ascending=True, na_position="last")

    st.success(f"{len(results)} results found.")

    for release_id, group in results.groupby("release_id"):
        release = group.iloc[0]
        st.subheader(release['Title'])
        st.text(f"Artist: {release['Artist']}")
        st.image(release['cover_art_final'] or PLACEHOLDER_COVER, width=150)

        with st.expander("Click to view tracklist"):
            st.dataframe(group[['Track Title', 'Artist', 'CD', 'Track Number']])

        with st.expander("Update Cover Art"):
            new_url = st.text_input("Custom cover art URL:", key=f"url_{release_id}")
            cols = st.columns(2)
            with cols[0]:
                if st.button("Upload custom URL", key=f"upload_{release_id}"):
                    update_cover_override(release_id, new_url)
            with cols[1]:
                if st.button("Revert to original Cover Art", key=f"revert_{release_id}"):
                    reset_cover_override(release_id)

# Version 1.9 - Full working version with improved fallback and suggestions

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
from streamlit_searchbox import st_searchbox

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
if 'search_type' not in st.session_state:
    st.session_state['search_type'] = "All"

def normalize(text):
    if pd.isna(text): return ''
    text = str(text).lower()
    text = ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', ' ', text).strip()

def fuzzy_match(text, query, threshold=85):
    return fuzz.partial_ratio(normalize(text), normalize(query)) >= threshold

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
    if response.status_code not in [200, 201]:
        st.error(f"❌ GitHub upload failed: {response.status_code} - {response.text}")
    return response

def fetch_discogs_cover(release_id):
    try:
        url = f"https://api.discogs.com/releases/{release_id}"
        headers = {"Authorization": f"Discogs token={DISCOGS_API_TOKEN}"}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if 'images' in data and data['images']:
                return data['images'][0].get('uri')
    except Exception as e:
        st.warning(f"Discogs API error: {e}")
    return None

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

        fallback_url = fetch_discogs_cover(release_id)
        if fallback_url:
            overrides = pd.concat([overrides, pd.DataFrame([{'release_id': release_id, 'cover_url': fallback_url}])], ignore_index=True)

        overrides.to_csv(COVER_OVERRIDES_FILE, index=False, encoding='utf-8')
        upload_to_github(COVER_OVERRIDES_FILE, GITHUB_REPO, GITHUB_TOKEN, GITHUB_BRANCH, f"Reset cover for {release_id}")
        st.success("✅ Reverted to original cover art and synced to GitHub!")
        st.cache_data.clear()
        st.rerun()
    except Exception as e:
        st.error(f"Reset failed: {e}")

@st.cache_data
def load_data():
    try:
        df = pd.read_csv(CSV_FILE, encoding='utf-8')
        if df.columns[0].startswith("Unnamed"):
            df = df.drop(columns=[df.columns[0]])
        if 'cover_art' not in df.columns:
            df['cover_art'] = None
        try:
            overrides = pd.read_csv(COVER_OVERRIDES_FILE, encoding='utf-8', on_bad_lines='skip')
            overrides.columns = overrides.columns.str.strip().str.lower()
            if not {'release_id', 'cover_url'}.issubset(overrides.columns):
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

def get_autocomplete_suggestions(prefix: str):
    df = load_data()
    search_type = st.session_state.get('search_type', 'All')
    normalized_prefix = normalize(prefix)

    field_map = {
        "Song Title": ["Track Title"],
        "Artist": ["Artist"],
        "Album": ["Title"],
        "All": ["Track Title", "Artist", "Title"]
    }

    fields = field_map.get(search_type, ["Track Title"])
    suggestions = {}

    for field in fields:
        if field not in df.columns:
            continue
        for val in df[field].dropna().astype(str).unique():
            norm_val = normalize(val)
            if not norm_val: continue
            words = norm_val.split()

            # Scoring logic
            if norm_val == normalized_prefix:
                score = 1000
            elif norm_val.startswith(normalized_prefix):
                score = 950
            elif words and words[0] == normalized_prefix:
                score = 925
            elif normalized_prefix in words:
                score = 900
            else:
                score = fuzz.partial_ratio(norm_val, normalized_prefix)

            # Penalize very short entries
            if len(norm_val) < 4:
                score -= 200

            # Boost longer more descriptive titles
            score += min(len(norm_val), 50)

            if val not in suggestions or score > suggestions[val]:
                suggestions[val] = score

    sorted_matches = sorted(suggestions.items(), key=lambda x: -x[1])
    return [x[0] for x in sorted_matches[:15]]

# === UI ===
st.markdown("""
<style>
/* Smaller buttons and inputs for compact layout */
div[data-testid="stButton"] > button {
    background: none;
    border: none;
    padding: 0;
    font-size: 14px;
    text-decoration: underline;
    color: var(--text-color);
    cursor: pointer;
}
div[data-testid="stButton"] > button:hover {
    color: var(--primary-color);
}

/* Responsive table container */
.scroll-table {
    overflow-x: auto;
    width: 100%;
}

/* Adjust title font size and image layout on small screens */
@media (max-width: 480px) {
    .album-container {
        display: flex;
        flex-direction: row;
        align-items: center;
        gap: 10px;
    }
    .album-img img {
        width: 70px !important;
    }
    .album-details {
        font-size: 14px;
    }
}
</style>
""", unsafe_allow_html=True)

st.title("Music Search App")

if st.button("🔄 New Search (Clear)"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

search_type = st.radio("Search by:", ["All", "Song Title", "Artist", "Album"], horizontal=True, key="search_type")
df = load_data()

try:
    search_query = st_searchbox(get_autocomplete_suggestions, key="search_autocomplete")
    if search_query:
        st.session_state["last_query"] = search_query
except Exception:
    search_query = st.session_state.get("last_query", "")

search_query = st.session_state.get("last_query", "")

if search_query:
    field_map = {"Song Title": "Track Title", "Artist": "Artist", "Album": "Title", "All": None}
    search_type = st.session_state.get("search_type", "All")

    if search_type == "All":
        mask = (
            df["Track Title"].fillna("").apply(lambda x: fuzzy_match(x, search_query)) |
            df["Artist"].fillna("").apply(lambda x: fuzzy_match(x, search_query)) |
            df["Title"].fillna("").apply(lambda x: fuzzy_match(x, search_query))
        )
        results = df[mask]
    else:
        field = field_map[search_type]
        results = df[df[field].fillna("").apply(lambda x: fuzzy_match(x, search_query))]

    unique_releases = results[['release_id', 'Format']].drop_duplicates()
    format_counts = {
        'All': len(results),
        'Album': unique_releases['Format'].str.contains("album|compilation|comp", case=False, na=False).sum(),
        'Single': unique_releases['Format'].str.contains("single", case=False, na=False).sum(),
        'Video': unique_releases['Format'].str.contains("video", case=False, na=False).sum()
    }

    format_filter = st.radio(
        'Format:',
        [f"All ({format_counts['All']})", f"Album ({format_counts['Album']})", f"Single ({format_counts['Single']})", f"Video ({format_counts['Video']})"],
        horizontal=True
    )
    format_clean = format_filter.split()[0]

    if format_clean != "All":
        pattern = 'album|compilation|comp' if format_clean == "Album" else format_clean.lower()
        results = results[results["Format"].fillna("").str.lower().str.contains(pattern, na=False)]

   if results.empty:
    st.warning("No results found.")
else:
    # Optional style tweaks
    st.markdown("""
    <style>
    div[data-testid="stButton"] > button {
        background: none;
        border: none;
        padding: 0;
        font-size: 14px;
        text-decoration: underline;
        color: var(--text-color);
        cursor: pointer;
    }
    div[data-testid="stButton"] > button:hover {
        color: var(--primary-color);
    }
    </style>
    """, unsafe_allow_html=True)

    # 📱 Simple View Toggle
    simple_view = st.checkbox("📱 Enable Simple View (Mobile-Friendly List)", value=False)

    for release_id, group in results.groupby("release_id"):
        first = group.iloc[0]
        cover_url = first.get("cover_art_final") or PLACEHOLDER_COVER
        artist = "Various Artists" if group["Artist"].nunique() > 1 else group["Artist"].iloc[0]
        title = first["Title"]
        theme = st.get_option("theme.base")
        icon_url = DISCOGS_ICON_BLACK if theme == "light" else DISCOGS_ICON_WHITE

        if simple_view:
            st.image(cover_url, width=100)
            st.markdown(f"**{title}**  \n*Artist: {artist}*")
        else:
            cols = st.columns([1, 5])
            with cols[0]:
                st.markdown(f"""
                    <a href="{cover_url}" target="_blank">
                        <img src="{cover_url}" width="120" style="border-radius:8px;" />
                    </a>
                """, unsafe_allow_html=True)
            with cols[1]:
                st.markdown(f"""
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <div style="font-size:20px;font-weight:600;">{title}</div>
                        <a href="https://www.discogs.com/release/{release_id}" target="_blank">
                            <img src="{icon_url}" width="24" style="margin-left:10px;" />
                        </a>
                    </div>
                    <div><strong>Artist:</strong> {artist}</div>
                """, unsafe_allow_html=True)

        if st.button("Edit Cover Art", key=f"edit_btn_{release_id}"):
            st.session_state["open_expander_id"] = release_id if st.session_state["open_expander_id"] != release_id else None

        is_expanded = st.session_state.get("open_expander_id") == release_id
        if is_expanded:
            with st.expander("Update Cover Art", expanded=True):
                with st.form(f"form_{release_id}"):
                    new_url = st.text_input("Custom cover art URL:", key=f"url_{release_id}")
                    cols = st.columns(2)
                    with cols[0]:
                        if st.form_submit_button("Upload custom URL"):
                            update_cover_override(release_id, new_url)
                    with cols[1]:
                        if st.form_submit_button("Revert to original Cover Art"):
                            reset_cover_override(release_id)
        else:
            with st.expander("Click to view tracklist"):
                st.dataframe(group[['Track Title', 'Artist', 'CD', 'Track Number']].rename(columns={
                    'Track Title': 'Song', 'CD': 'Disc', 'Track Number': 'Track'
                }).reset_index(drop=True), use_container_width=True, hide_index=True)

else:
    st.caption("Please enter a search query above.")

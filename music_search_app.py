# Version 1.6 - Final fix: single search bar, working format filters, Discogs API fallback

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

# Load secrets
required_secrets = ["DISCOGS_API_TOKEN", "GITHUB_TOKEN", "GITHUB_REPO"]
missing = [k for k in required_secrets if k not in st.secrets]
if missing:
    st.error(f"Missing secrets: {', '.join(missing)}")
    st.stop()

DISCOGS_API_TOKEN = st.secrets["DISCOGS_API_TOKEN"]
GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
GITHUB_REPO = st.secrets["GITHUB_REPO"]
GITHUB_BRANCH = 'main'

if 'open_expander_id' not in st.session_state:
    st.session_state['open_expander_id'] = None
if 'search_type' not in st.session_state:
    st.session_state['search_type'] = "Song Title"

def normalize(text):
    if pd.isna(text): return ''
    text = str(text).lower()
    text = ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', ' ', text).strip()

def fuzzy_match(text, query, threshold=85):
    return fuzz.partial_ratio(normalize(text), normalize(query)) >= threshold

def upload_to_github(file_path, repo, token, branch, message):
    url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    with open(file_path, "rb") as f:
        content = base64.b64encode(f.read()).decode()
    get_resp = requests.get(url, headers=headers, params={"ref": branch})
    sha = get_resp.json().get('sha') if get_resp.status_code == 200 else None
    data = {
        "message": message,
        "content": content,
        "branch": branch
    }
    if sha: data["sha"] = sha
    r = requests.put(url, headers=headers, json=data)
    if r.status_code not in [200, 201]:
        st.error(f"GitHub upload failed: {r.status_code} - {r.text}")
    return r

def fetch_original_cover(release_id):
    try:
        url = f"https://api.discogs.com/releases/{release_id}"
        headers = {"Authorization": f"Discogs token={DISCOGS_API_TOKEN}"}
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            return r.json().get("images", [{}])[0].get("uri", PLACEHOLDER_COVER)
    except:
        pass
    return PLACEHOLDER_COVER

def update_cover_override(release_id, new_url):
    try:
        if not os.path.exists(BACKUP_FOLDER): os.makedirs(BACKUP_FOLDER)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        shutil.copy(COVER_OVERRIDES_FILE, f"{BACKUP_FOLDER}/cover_overrides_backup_{ts}.csv")
    except Exception as e:
        st.warning(f"Backup failed: {e}")
    try:
        overrides = pd.read_csv(COVER_OVERRIDES_FILE, encoding="utf-8")
        overrides.columns = overrides.columns.str.strip().str.lower()
    except:
        overrides = pd.DataFrame(columns=['release_id', 'cover_url'])
    overrides = overrides[overrides['release_id'] != release_id]
    overrides = pd.concat([overrides, pd.DataFrame([{'release_id': release_id, 'cover_url': new_url}])], ignore_index=True)
    overrides.to_csv(COVER_OVERRIDES_FILE, index=False, encoding="utf-8")
    upload_to_github(COVER_OVERRIDES_FILE, GITHUB_REPO, GITHUB_TOKEN, GITHUB_BRANCH, f"Update cover for {release_id}")
    st.cache_data.clear()
    st.rerun()

def reset_cover_override(release_id):
    try:
        overrides = pd.read_csv(COVER_OVERRIDES_FILE, encoding="utf-8")
        overrides.columns = overrides.columns.str.strip().str.lower()
        overrides = overrides[overrides['release_id'] != release_id]
        original = fetch_original_cover(release_id)
        overrides = pd.concat([overrides, pd.DataFrame([{'release_id': release_id, 'cover_url': original}])], ignore_index=True)
        overrides.to_csv(COVER_OVERRIDES_FILE, index=False, encoding="utf-8")
        upload_to_github(COVER_OVERRIDES_FILE, GITHUB_REPO, GITHUB_TOKEN, GITHUB_BRANCH, f"Revert cover for {release_id}")
        st.cache_data.clear()
        st.rerun()
    except Exception as e:
        st.warning(f"Revert failed: {e}")

@st.cache_data
def load_data():
    try:
        df = pd.read_csv(CSV_FILE, encoding="utf-8")
        if df.columns[0].startswith("Unnamed"): df = df.iloc[:, 1:]
        if 'cover_art' not in df.columns: df['cover_art'] = None
        try:
            overrides = pd.read_csv(COVER_OVERRIDES_FILE, encoding="utf-8")
            overrides.columns = overrides.columns.str.strip().str.lower()
            overrides = overrides.drop_duplicates(subset='release_id', keep='last')
            df = df.merge(overrides, on='release_id', how='left')
            df['cover_art_final'] = df['cover_url'].combine_first(df['cover_art'])
        except:
            df['cover_art_final'] = df['cover_art']
    except Exception as e:
        st.error(f"Failed to load data: {e}")
        return pd.DataFrame()
    return df

def get_autocomplete_suggestions(prefix: str):
    df = load_data()
    field_map = {"Song Title": "Track Title", "Artist": "Artist", "Album": "Title"}
    field = field_map[st.session_state["search_type"]]
    values = df[field].dropna().astype(str).unique()
    normalized_prefix = normalize(prefix)
    ranked = []
    for val in values:
        norm = normalize(val)
        score = 1000 if norm == normalized_prefix else \
                950 if norm.split()[0] == normalized_prefix else \
                900 if norm.startswith(normalized_prefix) else \
                fuzz.partial_ratio(norm, normalized_prefix)
        ranked.append((val, score))
    return [x[0] for x in sorted(ranked, key=lambda x: -x[1])[:10]]

# === UI ===
st.title("Music Search App")
if st.button("🔄 New Search (Clear)"):
    st.session_state.clear()
    st.rerun()

search_type = st.radio("Search by:", ["Song Title", "Artist", "Album"], horizontal=True, key="search_type")
df = load_data()

try:
    search_query = st_searchbox(get_autocomplete_suggestions, key="search_autocomplete")
    if search_query: st.session_state['last_query'] = search_query
except:
    search_query = st.session_state.get('last_query', "")

if search_query:
    field_map = {"Song Title": "Track Title", "Artist": "Artist", "Album": "Title"}
    field = field_map[search_type]
    results = df[df[field].apply(lambda x: fuzzy_match(str(x), search_query))]

    unique = results[['release_id', 'Format']].drop_duplicates()
    format_counts = {
        'All': len(results),
        'Album': unique['Format'].str.contains("album|compilation|comp", case=False, na=False).sum(),
        'Single': unique['Format'].str.contains("single", case=False, na=False).sum(),
        'Video': unique['Format'].str.contains("video", case=False, na=False).sum()
    }

    format_filter = st.radio(
        "Format:",
        [f"All ({format_counts['All']})", f"Album ({format_counts['Album']})", f"Single ({format_counts['Single']})", f"Video ({format_counts['Video']})"],
        horizontal=True
    )
    fmt = format_filter.split()[0]
    if fmt != "All":
        pattern = 'album|compilation|comp' if fmt == "Album" else fmt.lower()
        results = results[results['Format'].fillna('').str.lower().str.contains(pattern, na=False)]

    if results.empty:
        st.warning("No results found.")
    else:
        st.markdown("""
        <style>
        div[data-testid="stButton"] > button {
            background: none; border: none; padding: 0;
            font-size: 14px; text-decoration: underline;
            color: var(--text-color); cursor: pointer;
        }
        div[data-testid="stButton"] > button:hover {
            color: var(--primary-color);
        }
        </style>
        """, unsafe_allow_html=True)

        for rid, group in results.groupby("release_id"):
            first = group.iloc[0]
            title = first['Title']
            artist = "Various Artists" if group["Artist"].nunique() > 1 else group["Artist"].iloc[0]
            cover = first.get("cover_art_final") or PLACEHOLDER_COVER
            cols = st.columns([1, 5])
            with cols[0]:
                st.markdown(f'<img src="{cover}" width="120" style="border-radius:8px;" />', unsafe_allow_html=True)
            with cols[1]:
                icon = DISCOGS_ICON_BLACK if st.get_option("theme.base") == "light" else DISCOGS_ICON_WHITE
                st.markdown(f"""
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <div style="font-size:20px;font-weight:600;">{title}</div>
                    <a href="https://www.discogs.com/release/{rid}" target="_blank">
                        <img src="{icon}" width="24" />
                    </a>
                </div>
                <div><strong>Artist:</strong> {artist}</div>
                """, unsafe_allow_html=True)

            if st.button("Edit Cover Art", key=f"edit_btn_{rid}"):
                st.session_state["open_expander_id"] = rid if st.session_state.get("open_expander_id") != rid else None

            if st.session_state.get("open_expander_id") == rid:
                with st.expander("Update Cover Art", expanded=True):
                    with st.form(f"form_{rid}"):
                        new_url = st.text_input("Custom cover art URL:", key=f"url_{rid}")
                        c1, c2 = st.columns(2)
                        with c1:
                            if st.form_submit_button("Upload custom URL"):
                                update_cover_override(rid, new_url)
                        with c2:
                            if st.form_submit_button("Revert to original Cover Art"):
                                reset_cover_override(rid)
            else:
                with st.expander("Click to view tracklist"):
                    st.dataframe(group[['Track Title', 'Artist', 'CD', 'Track Number']].rename(columns={
                        'Track Title': 'Song', 'CD': 'Disc', 'Track Number': 'Track'
                    }).reset_index(drop=True), use_container_width=True, hide_index=True)
else:
    st.caption("Please enter a search query above.")

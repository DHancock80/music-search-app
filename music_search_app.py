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

import unicodedata
import re

def normalize(text):
    if not isinstance(text, str):
        return ""
    text = text.lower()
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('utf-8')
    text = re.sub(r"[^\w\s]", "", text)  # remove punctuation
    return text.strip()

# === UI ===
st.title("Music Search App")

if st.button("🔄 New Search (Clear)"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

search_type = st.radio("Search by:", ["All", "Song Title", "Artist", "Album"], horizontal=True, key="search_type")
df = load_data()

# === Improved Autocomplete Function with Normalization ===
import unicodedata
import re

def normalize(text):
    if not isinstance(text, str):
        return ""
    text = text.lower()
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('utf-8')
    text = re.sub(r"[^\w\s]", "", text)  # remove punctuation
    return text.strip()

def get_autocomplete_suggestions(prefix):
    prefix_norm = normalize(prefix)
    if not prefix_norm:
        return []

    all_values = set(df['Track Title'].dropna().tolist() + df['Artist'].dropna().tolist() + df['Title'].dropna().tolist())

    norm_to_originals = {}
    for val in all_values:
        norm = normalize(val)
        if norm:
            norm_to_originals.setdefault(norm, set()).add(val)

    suggestions = {}
    for norm_val, originals in norm_to_originals.items():
        similarity = fuzz.partial_ratio(prefix_norm, norm_val)

        # Always allow exact match, prefix, or strong partial match
        if norm_val == prefix_norm:
            score = 100
        elif norm_val.startswith(prefix_norm):
            score = 95
        elif similarity >= 85:
            score = similarity
        else:
            continue  # skip unrelated suggestions

        score += min(len(norm_val), 30)  # slight boost for longer, specific names

        for original in originals:
            if original not in suggestions or score > suggestions[original]:
                suggestions[original] = score

    sorted_matches = sorted(suggestions.items(), key=lambda x: -x[1])
    return [x[0] for x in sorted_matches[:20]]

# === Search Input ===
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

    elif search_type == "Artist":
        artist_col = df["Artist"].fillna("")
        exact_matches = df[artist_col.str.lower() == search_query.lower()]

        if not exact_matches.empty:
            results = exact_matches
        else:
            partial_matches = df[artist_col.str.lower().str.contains(search_query.lower())]
            if not partial_matches.empty:
                results = partial_matches
            else:
                fuzzy_matches = df[artist_col.apply(lambda x: fuzzy_match(x, search_query))]
                results = fuzzy_matches

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
        simple_view = st.checkbox("📱 Enable Simple View (Mobile-Friendly List)", value=False)

        sort_options = ["A-Z", "Z-A", "Oldest", "Newest"]
        sort_choice = st.radio("Sort by:", sort_options, horizontal=True)

        def get_date(row):
            date = str(row).strip()
            if '/' in date:
                try:
                    parts = date.split('/')
                    if len(parts) == 3:
                        return f"{int(parts[2]):04d}-{int(parts[1]):02d}-{int(parts[0]):02d}"
                except:
                    return "0000-00-00"
            elif date.isdigit():
                return f"{int(date):04d}-01-01"
            return "0000-00-00"

        if 'Released' in results.columns:
            results['sort_date'] = results['Released'].apply(get_date)
        else:
            results['sort_date'] = "0000-00-00"

        album_representatives = results.drop_duplicates("release_id", keep="first").copy()

        if sort_choice == "A-Z":
            sorted_ids = album_representatives.sort_values(by="Title", ascending=True)["release_id"]
        elif sort_choice == "Z-A":
            sorted_ids = album_representatives.sort_values(by="Title", ascending=False)["release_id"]
        elif sort_choice == "Oldest":
            sorted_ids = album_representatives.sort_values(by="sort_date", ascending=True)["release_id"]
        elif sort_choice == "Newest":
            sorted_ids = album_representatives.sort_values(by="sort_date", ascending=False)["release_id"]
        else:
            sorted_ids = album_representatives["release_id"]

        results = pd.concat([results[results["release_id"] == rid] for rid in sorted_ids])

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

        .stDataFrame > div {
            font-size: 10px !important;
        }

        .stDataFrame table td, .stDataFrame table th {
            padding: 2px 4px !important;
            font-size: 10px !important;
        }

        .stDataFrame table th:nth-child(3),
        .stDataFrame table td:nth-child(3),
        .stDataFrame table th:nth-child(4),
        .stDataFrame table td:nth-child(4) {
            min-width: 30px !important;
            max-width: 30px !important;
            width: 30px !important;
        }

        @media (min-width: 768px) {
            .album-info-title {
                font-size: 20px !important;
            }
            .album-info-artist {
                font-size: 15px !important;
            }
        }
        </style>
        """, unsafe_allow_html=True)

        for release_id in sorted_ids:
            group = results[results["release_id"] == release_id]
            first = group.iloc[0]
            cover_url = first.get("cover_art_final") or PLACEHOLDER_COVER
            artist = "Various Artists" if group["Artist"].nunique() > 1 else group["Artist"].iloc[0]
            title = first["Title"]

            if simple_view:
                st.markdown(f"<div style='margin-bottom:0.5rem;font-size:18px;font-weight:bold;'>{title}</div>", unsafe_allow_html=True)
                st.markdown(f"<div style='margin-bottom:0.5rem;font-size:14px;'>– {artist}</div>", unsafe_allow_html=True)
            else:
                cols = st.columns([1.2, 5])
                with cols[0]:
                    st.markdown(f"""
                        <a href="{cover_url}" target="_blank">
                            <img src="{cover_url}" width="100" style="border-radius:6px;" />
                        </a>
                    """, unsafe_allow_html=True)
                with cols[1]:
                    theme = st.get_option("theme.base")
                    icon_url = DISCOGS_ICON_BLACK if theme == "light" else DISCOGS_ICON_WHITE
                    st.markdown(f"""
                        <div style="display:flex;justify-content:space-between;align-items:center;">
                            <div class="album-info-title" style="font-weight:600;">{title}</div>
                            <a href="https://www.discogs.com/release/{release_id}" target="_blank">
                                <img src="{icon_url}" width="22" style="margin-left:10px;" />
                            </a>
                        </div>
                        <div class="album-info-artist"><strong>Artist:</strong> {artist}</div>
                    """, unsafe_allow_html=True)

            if not simple_view and st.button("Edit Cover Art", key=f"edit_btn_{release_id}"):
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

            with st.expander("Click to view tracklist"):
                df_display = group[['Track Title', 'Artist', 'CD', 'Track Number']].rename(columns={
                    'Track Title': 'Song', 'Artist': 'Artist', 'CD': 'CD', 'Track Number': 'Trk'
                }).reset_index(drop=True)

                st.dataframe(df_display, use_container_width=True, hide_index=True)
else:
    st.caption("Please enter a search query above.")

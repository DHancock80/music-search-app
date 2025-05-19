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

# === UI ===
st.title("Music Search App")
search_type = st.radio("Search by:", ["Song Title", "Artist", "Album"], horizontal=True)
suggestion_column = "Track Title" if search_type == "Song Title" else ("Artist" if search_type == "Artist" else "Title")
df_suggestions = pd.read_csv(CSV_FILE, encoding='utf-8', on_bad_lines='skip') if os.path.exists(CSV_FILE) else pd.DataFrame()
search_query = st.text_input("Enter your search:", "")

sort_option = st.selectbox("Sort results by:", ["Alphabetical (A-Z)", "Release Year (Newest First)"])

if search_query:
    suggestions = get_auto_suggestions(df_suggestions, suggestion_column, search_query)
    if suggestions:
        st.markdown("**Did you mean:**")
        suggestion_cols = st.columns(len(suggestions))
        for i, suggestion in enumerate(suggestions):
            if suggestion_cols[i].button(suggestion, key=f"suggestion_{i}"):
                search_query = suggestion
                st.experimental_rerun()

    df = load_data()
    if not df.empty:
        results = df[df[suggestion_column].apply(lambda x: fuzzy_match(str(x), search_query))]

        if not results.empty:
            if sort_option == "Alphabetical (A-Z)":
                results = results.sort_values(by="Title")
            elif "Year" in results.columns:
                results["Year"] = pd.to_numeric(results["Year"], errors='coerce')
                results = results.sort_values(by=["Year", "Title"], ascending=[False, True])

            st.success(f"{len(results)} results found.")

            st.markdown(f"""
            <script>
            document.addEventListener('DOMContentLoaded', function () {{
                const logos = document.querySelectorAll('[data-discogs-icon]');
                const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
                logos.forEach(el => {{
                    el.src = isDark ? '{DISCOGS_ICON_WHITE}' : '{DISCOGS_ICON_BLACK}';
                }});
            }});
            </script>
            """, unsafe_allow_html=True)

            for release_id, group in results.groupby("release_id"):
                first_row = group.iloc[0]
                title = first_row["Title"]
                artist = "Various Artists" if group["Artist"].nunique() > 1 else group["Artist"].iloc[0]
                cover_url = first_row.get('cover_art_final') or PLACEHOLDER_COVER

                cols = st.columns([1, 5])
                with cols[0]:
                    st.markdown(f"""
                        <a href="{cover_url}" target="_blank">
                            <img src="{cover_url}" width="120" style="border-radius:8px;" />
                        </a>
                    """, unsafe_allow_html=True)

                with cols[1]:
                    st.markdown(f"""
                        <div style='display:flex;justify-content:space-between;align-items:center;'>
                            <div style='font-size:20px;font-weight:600;'>{title}</div>
                            <a href="https://www.discogs.com/release/{release_id}" target="_blank">
                                <img data-discogs-icon src="{DISCOGS_ICON_WHITE}" width="24" style="margin-left:10px;" />
                            </a>
                        </div>
                        <div><strong>Artist:</strong> {artist}</div>
                    """, unsafe_allow_html=True)

                if st.button("Edit Cover Art", key=f"edit_btn_{release_id}"):
                    st.session_state['open_expander_id'] = release_id if st.session_state.get('open_expander_id') != release_id else None

                if st.session_state.get('open_expander_id') == release_id:
                    with st.expander("Update Cover Art", expanded=True):
                        with st.form(f"form_{release_id}"):
                            new_url = st.text_input("Custom cover art URL:", key=f"url_{release_id}")
                            cols_form = st.columns(2)
                            with cols_form[0]:
                                if st.form_submit_button("Upload custom URL"):
                                    update_cover_override(release_id, new_url)
                            with cols_form[1]:
                                if st.form_submit_button("Revert to original Cover Art"):
                                    reset_cover_override(release_id)
                else:
                    with st.expander("Click to view tracklist"):
                        st.dataframe(group[["Track Title", "Artist", "CD", "Track Number"]].rename(columns={
                            "Track Title": "Song", "CD": "Disc", "Track Number": "Track"
                        }).reset_index(drop=True), use_container_width=True, hide_index=True)
else:
    st.caption("Please enter a search query above.")

import pandas as pd
import base64
import requests
import os
import shutil
import re
import unicodedata
from datetime import datetime
import streamlit as st

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

def normalize(text):
    if pd.isna(text): return ''
    text = str(text).lower()
    text = ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c))
    return text

def clean_artist_variants(artist):
    artist = normalize(artist)
    artist = re.sub(r'\s*(feat\.|ft\.|featuring)\s*', ' ', artist)
    artist = re.sub(r'[,/&]+', ' ', artist)
    return re.sub(r'\s+', ' ', artist).strip().split()

def search(df, query, search_type):
    norm_query = normalize(query.strip())
    if search_type == 'Song Title':
        return df[df['Track Title'].apply(normalize).str.contains(norm_query, na=False)]
    elif search_type == 'Artist':
        mask = df['Artist'].apply(lambda artists: any(norm_query in clean_artist_variants(str(artists))))
        return df[mask]
    elif search_type == 'Album':
        return df[df['Title'].apply(normalize).str.contains(norm_query, na=False)]
    return df

# --------------------------- MAIN UI ---------------------------

st.title('Music Search App')
search_query = st.text_input('Enter your search:', '')
search_type = st.radio('Search by:', ['Song Title', 'Artist', 'Album'], horizontal=True)

if search_query:
    df = load_data()
    results = search(df, search_query, search_type)

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

    unique_releases = results[['release_id', 'Format']].drop_duplicates()
    format_counts = {
        'All': len(results),
        'Album': unique_releases['Format'].str.contains("album|compilation|comp", case=False, na=False).sum(),
        'Single': unique_releases['Format'].str.contains("single", case=False, na=False).sum(),
        'Video': unique_releases['Format'].str.contains("video", case=False, na=False).sum()
    }

    format_filter = st.radio('Format:', [f"All ({format_counts['All']})", f"Album ({format_counts['Album']})", f"Single ({format_counts['Single']})", f"Video ({format_counts['Video']})"], horizontal=True)
    format_clean = format_filter.split()[0]

    if format_clean != 'All':
        pattern = 'album|compilation|comp' if format_clean == 'Album' else format_clean.lower()
        results = results[results['Format'].str.lower().str.contains(pattern, na=False)]

    if results.empty:
        st.info("No results found.")
    else:
        for release_id, group in results.groupby('release_id'):
            first_row = group.iloc[0]
            title = first_row['Title']
            artist = "Various Artists" if group['Artist'].nunique() > 1 else group['Artist'].iloc[0]
            cover_url = first_row.get('cover_art_final') or PLACEHOLDER_COVER

            cols = st.columns([1, 5])
            with cols[0]:
                st.markdown(f"""
                    <a href="{cover_url}" target="_blank">
                        <img src="{cover_url}" width="120" style="border-radius:8px;" />
                    </a>
                    <div style="margin-top:4px;font-size:14px;">
                        <a href="?expand={release_id}" style="color:#1f77b4;text-decoration:underline;">Edit Cover Art</a>
                    </div>
                """, unsafe_allow_html=True)

            with cols[1]:
                st.markdown(f"""
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <div style="font-size:20px;font-weight:600;">{title}</div>
                        <a href="https://www.discogs.com/release/{release_id}" target="_blank">
                            <img data-discogs-icon src="{DISCOGS_ICON_WHITE}" alt="Discogs" width="24" style="margin-left:10px;" />
                        </a>
                    </div>
                    <div><strong>Artist:</strong> {artist}</div>
                """, unsafe_allow_html=True)

            if st.session_state.get('open_expander_id') == release_id:
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
                st.dataframe(group[['Track Title', 'Artist', 'CD', 'Track Number']].rename(columns={
                    'Track Title': 'Song', 'CD': 'Disc', 'Track Number': 'Track'
                }).reset_index(drop=True), use_container_width=True, hide_index=True)
else:
    st.caption("Please enter a search query above.")

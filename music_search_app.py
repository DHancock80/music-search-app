import streamlit as st
import pandas as pd
import re
import requests
import time
import base64
import shutil
import os
from datetime import datetime

# Constants
CSV_FILE = 'expanded_discogs_tracklists.csv'
COVER_OVERRIDES_FILE = 'cover_overrides.csv'
BACKUP_FOLDER = 'backups'
PLACEHOLDER_COVER = 'https://upload.wikimedia.org/wikipedia/commons/thumb/6/65/No-Image-Placeholder.svg/2048px-No-Image-Placeholder.svg.png'
DISCOGS_API_TOKEN = st.secrets["DISCOGS_API_TOKEN"]
DISCOGS_ICON_DARK = 'https://raw.githubusercontent.com/DHancock80/music-search-app/main/discogs_white.png'
DISCOGS_ICON_LIGHT = 'https://raw.githubusercontent.com/DHancock80/music-search-app/main/discogs_black.png'

# Utility functions
@st.cache_data
def load_data():
    try:
        df = pd.read_csv(CSV_FILE, encoding='latin1')
        if df.columns[0].startswith("Unnamed"):
            df = df.drop(columns=[df.columns[0]])
        if 'cover_art' not in df.columns:
            df['cover_art'] = None
        try:
            overrides = pd.read_csv(COVER_OVERRIDES_FILE, encoding='latin1', on_bad_lines='skip')
            overrides.columns = overrides.columns.str.strip().str.lower()
            if not {'release_id', 'cover_url'}.issubset(overrides.columns):
                st.warning("Overrides file missing required columns. Skipping override merge.")
                df['cover_art_final'] = df['cover_art']
            else:
                overrides = overrides.drop_duplicates(subset='release_id', keep='last')
                df = df.merge(overrides, on='release_id', how='left', suffixes=('', '_override'))
                df['cover_art_final'] = df['cover_url'].combine_first(df['cover_art'])
        except:
            df['cover_art_final'] = df['cover_art']
    except Exception as e:
        st.error(f"Error loading the CSV file: {e}")
        return pd.DataFrame()
    return df

def clean_artist_name(artist):
    if pd.isna(artist): return ''
    artist = artist.lower()
    artist = re.sub(r'[\*\(\)\[#]', '', artist)
    artist = re.sub(r'\s*(feat\.|ft\.|featuring)\s*', ' ', artist)
    artist = artist.replace('&', ' ').replace(',', ' ')
    artist = re.sub(r'\s+', ' ', artist).strip()
    return artist

def backup_csv():
    if not os.path.exists(BACKUP_FOLDER):
        os.makedirs(BACKUP_FOLDER)
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    shutil.copy(COVER_OVERRIDES_FILE, os.path.join(BACKUP_FOLDER, f'cover_overrides_backup_{timestamp}.csv'))

def fetch_discogs_cover(release_id):
    headers = {"Authorization": f"Discogs token={DISCOGS_API_TOKEN}"}
    try:
        response = requests.get(f"https://api.discogs.com/releases/{release_id}", headers=headers)
        if response.status_code == 200:
            data = response.json()
            if 'images' in data and data['images']:
                return data['images'][0]['uri']
    except:
        pass
    return None

def get_discogs_icon():
    return DISCOGS_ICON_LIGHT if st.get_option("theme.base") == "light" else DISCOGS_ICON_DARK

# Main app
st.set_page_config(page_title="Music Search App", layout="wide")
df = load_data()
if df.empty:
    st.stop()

st.title("Music Search App")

search_query = st.text_input("Enter your search:", "")
search_type = st.radio("Search by:", ["Song Title", "Artist", "Album"], horizontal=True)
format_filter = st.radio("Format:", ["All", "Album", "Single", "Video"], horizontal=True)

if search_query:
    query = search_query.lower().strip()
    results = df.copy()

    if search_type == 'Song Title':
        results = results[results['Track Title'].str.lower().str.contains(query, na=False)]
    elif search_type == 'Artist':
        results['artist_clean'] = results['Artist'].apply(clean_artist_name)
        results = results[results['artist_clean'].str.contains(query, na=False)]
    elif search_type == 'Album':
        results = results[results['Title'].str.lower().str.contains(query, na=False)]

    if format_filter != 'All':
        results = results[results['Format'].str.lower() == format_filter.lower()]

    grouped = results.groupby('release_id')
    counts = {
        'All': len(results),
        'Album': (results['Format'].str.lower() == 'album').sum(),
        'Single': (results['Format'].str.lower() == 'single').sum(),
        'Video': (results['Format'].str.lower() == 'video').sum()
    }

    st.markdown(f"""
        **Results:**  
        All: {counts['All']} &nbsp; |  
        Album: {counts['Album']} &nbsp; |  
        Single: {counts['Single']} &nbsp; |  
        Video: {counts['Video']}
    """, unsafe_allow_html=True)

    for release_id, group in grouped:
        first = group.iloc[0]
        title = first['Title']
        artist = first['Artist']
        cover = first.get('cover_art_final') or PLACEHOLDER_COVER
        discogs_url = f"https://www.discogs.com/release/{release_id}"

        col1, col2, col3 = st.columns([1, 5, 1])
        with col1:
            st.markdown(f'<a href="{cover}" target="_blank"><img src="{cover}" width="100"></a>', unsafe_allow_html=True)

        with col2:
            st.markdown(f"### {title}")
            st.markdown(f"**Artist:** {artist}")
            show_edit = st.button("Edit Cover Art", key=f"showedit_{release_id}")
        with col3:
            icon_url = get_discogs_icon()
            st.markdown(f'<a href="{discogs_url}" target="_blank"><img src="{icon_url}" width="80"></a>', unsafe_allow_html=True)

        if show_edit:
            with st.expander("Update Cover Art", expanded=True):
                new_url = st.text_input("Enter new cover art URL:", key=f"url_{release_id}")
                upload, revert = st.columns(2)
                with upload:
                    if st.button("Upload custom URL", key=f"upload_{release_id}"):
                        try:
                            overrides = pd.read_csv(COVER_OVERRIDES_FILE, encoding='latin1')
                            overrides = overrides[overrides['release_id'] != release_id]
                        except:
                            overrides = pd.DataFrame(columns=['release_id', 'cover_url'])
                        new_entry = pd.DataFrame([[release_id, new_url]], columns=['release_id', 'cover_url'])
                        final_df = pd.concat([overrides, new_entry])
                        final_df.to_csv(COVER_OVERRIDES_FILE, index=False, encoding='latin1')
                        backup_csv()
                        st.success("Custom URL uploaded and synced!")
                        st.rerun()
                with revert:
                    if st.button("Revert to original Cover Art", key=f"revert_{release_id}"):
                        try:
                            overrides = pd.read_csv(COVER_OVERRIDES_FILE, encoding='latin1')
                            overrides = overrides[overrides['release_id'] != release_id]
                            overrides.to_csv(COVER_OVERRIDES_FILE, index=False, encoding='latin1')
                            backup_csv()
                            st.success("Cover reverted to Discogs original!")
                            st.rerun()
                        except:
                            st.warning("No override to revert.")

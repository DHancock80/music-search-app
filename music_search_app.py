import streamlit as st
import pandas as pd
import re
import requests

# Constants
CSV_FILE = 'expanded_discogs_tracklist.csv'
COVER_OVERRIDES_FILE = 'cover_overrides.csv'
DISCOGS_API_URL = 'https://api.discogs.com/releases/'

@st.cache_data
def load_data():
    try:
        df = pd.read_csv(CSV_FILE, encoding='latin1')
        
        # Add cover_art column if missing
        if 'cover_art' not in df.columns:
            df['cover_art'] = None  # No default cover art yet
        
        # Load cover overrides if available
        try:
            overrides = pd.read_csv(COVER_OVERRIDES_FILE, encoding='latin1')
            if 'release_id' in overrides.columns and 'cover_url' in overrides.columns:
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

def search(df, query, search_type, format_filter):
    if df.empty:
        return df
    query = query.lower().strip()
    results = df.copy()

    if search_type == 'Song Title':
        if 'Track Title' not in results.columns:
            st.error("The CSV does not contain a 'Track Title' column.")
            return pd.DataFrame()
        results = results[results['Track Title'].str.lower().str.contains(query, na=False)]
    elif search_type == 'Artist':
        if 'Artist' not in results.columns:
            st.error("The CSV does not contain an 'Artist' column.")
            return pd.DataFrame()
        results['artist_clean'] = results['Artist'].apply(clean_artist_name)
        results = results[results['artist_clean'].str.contains(query, na=False)]
    elif search_type == 'Album':
        if 'Title' not in results.columns:
            st.error("The CSV does not contain a 'Title' column.")
            return pd.DataFrame()
        results = results[results['Title'].str.lower().str.contains(query, na=False)]

    if format_filter != 'All':
        if 'Format' in results.columns:
            results = results[results['Format'].str.lower() == format_filter.lower()]
        else:
            st.warning("Format column missing; ignoring format filter.")

    return results

def fetch_discogs_cover(release_id):
    try:
        response = requests.get(f"{DISCOGS_API_URL}{release_id}")
        if response.status_code == 200:
            data = response.json()
            if 'images' in data and len(data['images']) > 0:
                return data['images'][0]['uri']
    except Exception as e:
        st.warning(f"Failed to fetch from Discogs: {e}")
    return None

# Streamlit app
st.title('🎵 Music Search App')

# Add CSS for card styling
st.markdown("""
    <style>
    .album-card {
        border: 2px solid #ddd;
        border-radius: 10px;
        padding: 15px;
        margin-bottom: 25px;
        background-color: #f9f9f9;
    }
    .album-header {
        display: flex;
        align-items: center;
        margin-bottom: 15px;
    }
    .album-cover {
        margin-right: 20px;
    }
    </style>
""", unsafe_allow_html=True)

df = load_data()

if df.empty:
    st.stop()

search_query = st.text_input('Enter your search:', '')
search_type = st.radio('Search by:', ['Song Title', 'Artist', 'Album'], horizontal=True)
format_filter = st.selectbox('Format filter:', ['All', 'Album', 'Single'])

if search_query:
    results = search(df, search_query, search_type, format_filter)
    st.write(f"### Found {len(results)} result(s)")
    
    if results.empty:
        st.info("No results found.")
    else:
        cover_cache = {}
        grouped = results.groupby('release_id')

        for release_id, group in grouped:
            first_row = group.iloc[0]
            album_title = first_row['Title']
            artist = first_row['Artist']
            cover = first_row.get('cover_art_final') or first_row.get('cover_art')
            
            if pd.isna(cover) and pd.notna(release_id):
                if release_id not in cover_cache:
                    cover = fetch_discogs_cover(release_id)
                    cover_cache[release_id] = cover
                else:
                    cover = cover_cache[release_id]
            else:
                cover_cache[release_id] = cover

            with st.container():
                st.markdown('<div class="album-card">', unsafe_allow_html=True)

                # Album header with cover + info
                st.markdown('<div class="album-header">', unsafe_allow_html=True)
                cols = st.columns([1, 5])
                with cols[0]:
                    if cover:
                        st.markdown(
                            f'<a href="{cover}" target="_blank">'
                            f'<img src="{cover}" width="120" class="album-cover"></a>',
                            unsafe_allow_html=True
                        )
                        # Small button to report/update cover
                        with st.expander("Report or update cover art"):
                            new_url = st.text_input(f"Enter new cover art URL for this album (Release ID: {release_id}):", key=f"url_{release_id}")
                            if st.button("Submit new cover art", key=f"submit_{release_id}"):
                                if new_url:
                                    new_entry = pd.DataFrame([{'release_id': release_id, 'cover_url': new_url}])
                                    try:
                                        existing = pd.read_csv(COVER_OVERRIDES_FILE, encoding='latin1')
                                        updated = pd.concat([existing, new_entry], ignore_index=True)
                                    except FileNotFoundError:
                                        updated = new_entry
                                    updated.to_csv(COVER_OVERRIDES_FILE, index=False, encoding='latin1')
                                    st.success("Cover art override saved! Please reload the app to see changes.")
                                else:
                                    st.error("Please enter a valid URL.")
                    else:
                        st.text("No cover art")

                with cols[1]:
                    st.markdown(f"### {album_title}")
                    st.markdown(f"**Artist:** {artist}")
                st.markdown('</div>', unsafe_allow_html=True)

                tracklist = group[[
                    'Track Title', 'Artist', 'CD', 'Track Number', 'Format'
                ]].rename(columns={
                    'Track Title': 'Song',
                    'CD': 'Disc',
                    'Track Number': 'Track',
                }).reset_index(drop=True)

                st.table(tracklist.style.hide(axis='index'))

                st.markdown('</div>', unsafe_allow_html=True)

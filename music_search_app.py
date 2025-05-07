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
        
        if 'cover_art' not in df.columns:
            df['cover_art'] = None
        
        try:
            overrides = pd.read_csv(COVER_OVERRIDES_FILE, encoding='latin1')
            # Deduplicate: keep latest override for each release_id
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

def search(df, query, search_type, format_filter):
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

    if format_filter != 'All':
        if 'Format' in results.columns:
            results = results[results['Format'].str.lower() == format_filter.lower()]

    return results

def fetch_discogs_cover(release_id):
    try:
        response = requests.get(f"{DISCOGS_API_URL}{release_id}")
        if response.status_code == 200:
            data = response.json()
            if 'images' in data and len(data['images']) > 0:
                return data['images'][0]['uri']
    except Exception:
        pass
    return None

# Streamlit app
st.title('🎵 Music Search App')

# ✅ CSS: keep full width lock & clip horizontal overflow
st.markdown("""
    <style>
    .block-container {
        width: 100% !important;
        max-width: 100% !important;
        min-width: 100% !important;
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

    unique_results = results.drop_duplicates()
    st.write(f"### Found {len(unique_results)} result(s)")

    if unique_results.empty:
        st.info("No results found.")
    else:
        cover_cache = {}
        grouped = results.groupby('release_id')

        for release_id, group in grouped:
            first_row = group.iloc[0]
            album_title = first_row['Title']
            artist = first_row['Artist']
            cover = first_row.get('cover_art_final')

            # ✅ Extra check: if cover is missing, empty, or NaN, fetch from Discogs
            if (pd.isna(cover) or str(cover).strip() == '') and pd.notna(release_id):
                if release_id not in cover_cache:
                    cover = fetch_discogs_cover(release_id)
                    cover_cache[release_id] = cover
                else:
                    cover = cover_cache[release_id]
            else:
                cover_cache[release_id] = cover

            with st.container():
                # Album header
                cols = st.columns([1, 5])
                with cols[0]:
                    if cover:
                        st.markdown(
                            f'<a href="{cover}" target="_blank">'
                            f'<img src="{cover}" width="120"></a>',
                            unsafe_allow_html=True
                        )
                    else:
                        st.text("No cover art")

                with cols[1]:
                    st.markdown(f"### {album_title}")
                    st.markdown(f"**Artist:** {artist}")

                # Update Cover Art expander (below header, above table)
                with st.expander("Update Cover Art"):
                    new_url = st.text_input("Paste a new cover art URL:", key=f"url_{release_id}")
                    submit_col, reset_col = st.columns(2)

                    with submit_col:
                        if st.button("Submit new cover art", key=f"submit_{release_id}"):
                            if new_url:
                                new_entry = pd.DataFrame([{'release_id': release_id, 'cover_url': new_url}])
                                try:
                                    existing = pd.read_csv(COVER_OVERRIDES_FILE, encoding='latin1')
                                    if 'release_id' not in existing.columns or 'cover_url' not in existing.columns:
                                        existing = pd.DataFrame(columns=['release_id', 'cover_url'])
                                    existing = existing[existing['release_id'] != release_id]
                                    updated = pd.concat([existing, new_entry], ignore_index=True)
                                except FileNotFoundError:
                                    updated = new_entry

                                updated.to_csv(COVER_OVERRIDES_FILE, index=False, encoding='latin1')
                                st.success("Cover art override saved! Reloading to apply changes...")
                                st.cache_data.clear()
                                st.rerun()
                            else:
                                st.error("Please enter a valid URL.")

                    with reset_col:
                        if st.button("Reset to original cover", key=f"reset_{release_id}"):
                            try:
                                # ✅ Always attempt removal, even if no entry exists
                                existing = pd.read_csv(COVER_OVERRIDES_FILE, encoding='latin1')
                                if 'release_id' not in existing.columns or 'cover_url' not in existing.columns:
                                    existing = pd.DataFrame(columns=['release_id', 'cover_url'])
                                updated = existing[existing['release_id'] != release_id]
                                updated.to_csv(COVER_OVERRIDES_FILE, index=False, encoding='latin1')
                                st.success("Cover override removed (if it existed). Reloading to apply changes...")
                                st.cache_data.clear()
                                st.rerun()
                            except FileNotFoundError:
                                # File didn't exist at all—just reload
                                st.success("Cover override removed (if it existed). Reloading to apply changes...")
                                st.cache_data.clear()
                                st.rerun()

                # ✅ Tracklist table using st.dataframe (auto-height + interactive)
                tracklist = group[[
                    'Track Title', 'Artist', 'CD', 'Track Number', 'Format'
                ]].rename(columns={
                    'Track Title': 'Song',
                    'CD': 'Disc',
                    'Track Number': 'Track',
                }).reset_index(drop=True)

                st.dataframe(
                    tracklist,
                    use_container_width=True,
                    hide_index=True,
                )

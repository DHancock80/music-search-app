import streamlit as st
import pandas as pd
import re

# Constants
CSV_FILE = 'expanded_discogs_tracklist.csv'
COVER_OVERRIDES_FILE = 'cover_overrides.csv'

@st.cache_data
def load_data():
    try:
        df = pd.read_csv(CSV_FILE, encoding='latin1')
        
        # Check if cover art is in the main CSV
        if 'cover_art' not in df.columns:
            df['cover_art'] = None  # Add empty column if missing
        
        # Load cover overrides if available
        try:
            overrides = pd.read_csv(COVER_OVERRIDES_FILE, encoding='latin1')
            if 'release_id' in overrides.columns and 'cover_url' in overrides.columns:
                df = df.merge(overrides, on='release_id', how='left', suffixes=('', '_override'))
                # Use override if available
                df['cover_art_final'] = df['cover_url'].combine_first(df['cover_art'])
            else:
                df['cover_art_final'] = df['cover_art']
        except FileNotFoundError:
            st.warning("Cover overrides file not found. Proceeding without overrides.")
            df['cover_art_final'] = df['cover_art']
            
    except Exception as e:
        st.error(f"Error loading the CSV file: {e}")
        df = pd.DataFrame()  # Return empty DataFrame on error
    return df

def clean_artist_name(artist):
    if pd.isna(artist):
        return ''
    # Lowercase, remove special characters, handle feat./ft./&/, variations
    artist = artist.lower()
    artist = re.sub(r'[\*\(\)\[\]#]', '', artist)
    artist = re.sub(r'\s*(feat\.|ft\.|featuring)\s*', ' ', artist)
    artist = artist.replace('&', ' ').replace(',', ' ')
    artist = re.sub(r'\s+', ' ', artist).strip()
    return artist

def search(df, query, search_type, format_filter):
    if df.empty:
        return df  # Return empty if no data loaded
    
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

# Streamlit app
st.title('🎵 Music Search App')

df = load_data()

if df.empty:
    st.stop()

search_query = st.text_input('Enter your search:', '')
search_type = st.radio('Search by:', ['Song Title', 'Artist', 'Album'])
format_filter = st.selectbox('Format filter:', ['All', 'Album', 'Single'])

if search_query:
    results = search(df, search_query, search_type, format_filter)
    st.write(f"### Found {len(results)} result(s)")
    
    if results.empty:
        st.info("No results found.")
    else:
        for _, row in results.iterrows():
            st.subheader(f"{row['Track Title']} - {row['Artist']}")
            st.write(f"**Album:** {row['Title']}")
            st.write(f"**Disc:** {row.get('CD', 'N/A')} | **Track:** {row.get('Track Number', 'N/A')}")
            st.write(f"**Format:** {row.get('Format', 'N/A')}")
            
            cover = row.get('cover_art_final') or row.get('cover_art')
            if pd.notna(cover):
                st.image(cover, caption='Cover Art', use_column_width=True)
            else:
                st.text('No cover art available.')

# Optional: File uploader for cover art corrections
st.write("---")
st.write("### Submit cover art correction")

cover_url = st.text_input("Paste an image URL")
release_id = st.text_input("Enter the release ID to update")

if cover_url and release_id:
    try:
        # Append the new override to the CSV
        new_entry = pd.DataFrame([{'release_id': release_id, 'cover_url': cover_url}])
        try:
            existing = pd.read_csv(COVER_OVERRIDES_FILE, encoding='latin1')
            updated = pd.concat([existing, new_entry], ignore_index=True)
        except FileNotFoundError:
            updated = new_entry
        updated.to_csv(COVER_OVERRIDES_FILE, index=False, encoding='latin1')
        st.success("Cover art override saved! Please reload the app to see changes.")
    except Exception as e:
        st.error(f"Failed to save override: {e}")

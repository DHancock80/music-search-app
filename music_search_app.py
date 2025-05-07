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
        # Load cover overrides if available
        try:
            overrides = pd.read_csv(COVER_OVERRIDES_FILE, encoding='latin1')
            if 'release_id' in overrides.columns and 'cover_url' in overrides.columns:
                df = df.merge(overrides, on='release_id', how='left')
                df['cover_art'] = df['cover_url'].combine_first(df['cover_art'])
        except FileNotFoundError:
            st.warning("Cover overrides file not found. Proceeding without overrides.")
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

def fuzzy_match(query, target):
    # Simple fuzzy match: check if query is in target with minor typo tolerance
    return query in target or re.sub(r'\s+', '', query) in re.sub(r'\s+', '', target)

def search(df, query, search_type, format_filter):
    if df.empty:
        return df  # Return empty if no data loaded
    
    query = query.lower().strip()
    results = df.copy()

    if search_type == 'Song Title':
        results = results[results['track_title'].str.lower().str.contains(query, na=False)]
    elif search_type == 'Artist':
        results['artist_clean'] = results['artist'].apply(clean_artist_name)
        results = results[results['artist_clean'].str.contains(query, na=False)]
    elif search_type == 'Album':
        results = results[results['album'].str.lower().str.contains(query, na=False)]

    if format_filter != 'All':
        results = results[results['format'].str.lower() == format_filter.lower()]

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
    st.write(f"### Found {len(results)} results")
    
    for _, row in results.iterrows():
        st.subheader(f"{row['track_title']} - {row['artist']}")
        st.write(f"**Album:** {row['album']}")
        st.write(f"**Disc:** {row.get('disc_number', 'N/A')} | **Track:** {row.get('track_number', 'N/A')}")
        st.write(f"**Format:** {row['format']}")
        
        if pd.notna(row.get('cover_art')):
            st.image(row['cover_art'], caption='Cover Art', use_column_width=True)
        else:
            st.text('No cover art available.')

# Optional: File uploader for cover art corrections
st.write("---")
st.write("### Submit cover art correction")

uploaded_file = st.file_uploader("Upload new cover art", type=["png", "jpg", "jpeg"])
cover_url = st.text_input("Or paste an image URL")
release_id = st.text_input("Enter the release ID to update")

if (uploaded_file or cover_url) and release_id:
    if uploaded_file:
        st.warning("Uploading images directly is not yet supported in this simple app version. Please use a URL for now.")
    if cover_url:
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

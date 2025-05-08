import streamlit as st
import pandas as pd
import requests
import os

# ---------- CONFIG ----------
CSV_FILE = 'expanded_discogs_tracklists.csv'
COVER_OVERRIDES_FILE = 'cover_overrides.csv'
DISCOGS_API_BASE = 'https://api.discogs.com/releases/'
DISCOGS_API_TOKEN = os.getenv('DISCOGS_API_TOKEN')  # set your Discogs token as environment variable

# ---------- FUNCTIONS ----------
@st.cache_data
def load_data():
    try:
        df = pd.read_csv(CSV_FILE)
    except UnicodeDecodeError:
        df = pd.read_csv(CSV_FILE, encoding='latin1')
    if 'release_id' not in df.columns:
        st.error("CSV file must include 'release_id' column.")
    return df

@st.cache_data
def load_cover_overrides():
    try:
        return pd.read_csv(COVER_OVERRIDES_FILE)
    except:
        return pd.DataFrame(columns=['release_id', 'cover_url'])

def save_cover_override(release_id, url):
    overrides = load_cover_overrides()
    overrides = overrides[overrides['release_id'] != release_id]
    overrides = pd.concat([overrides, pd.DataFrame({'release_id': [release_id], 'cover_url': [url]})])
    overrides.to_csv(COVER_OVERRIDES_FILE, index=False)

def remove_cover_override(release_id):
    overrides = load_cover_overrides()
    overrides = overrides[overrides['release_id'] != release_id]
    overrides.to_csv(COVER_OVERRIDES_FILE, index=False)

def fetch_cover_from_discogs(release_id):
    try:
        headers = {'Authorization': f'Discogs token={DISCOGS_API_TOKEN}'} if DISCOGS_API_TOKEN else {}
        res = requests.get(DISCOGS_API_BASE + str(release_id), headers=headers)
        if res.status_code == 200:
            data = res.json()
            return data['images'][0]['uri'] if 'images' in data and data['images'] else None
    except:
        pass
    return None

# ---------- MAIN APP ----------
st.title('Music Search App')

df = load_data()
covers_df = load_cover_overrides()

search_query = st.text_input("Enter your search:")
search_type = st.radio("Search by:", ('Song Title', 'Artist', 'Album'), horizontal=True)
format_filter = st.selectbox("Format filter:", options=['All', 'Album'])

if search_query:
    # --- Filter results ---
    if search_type == 'Song Title':
        results = df[df['Track Title'].str.contains(search_query, case=False, na=False)]
    elif search_type == 'Artist':
        results = df[df['Artist'].str.contains(search_query, case=False, na=False)]
    else:
        results = df[df['Title'].str.contains(search_query, case=False, na=False)]

    # --- Apply format filter ---
    if format_filter == 'Album':
        album_keywords = ['album', 'compilation', 'comp', 'cd']
        results = results[results['Format'].str.contains('|'.join(album_keywords), case=False, na=False)]

    if results.empty:
        st.warning("No results found.")
    else:
        if search_type == 'Album' or format_filter == 'Album':
            grouped = results.groupby(['release_id', 'Title'])
            st.subheader(f"Found {grouped.ngroups} album(s)")

            for (release_id, album_title), group in grouped:
                album_artist = group['Artist'].iloc[0]
                unique_artists = group['Artist'].dropna().unique()

                display_artist = album_artist
                if len(unique_artists) > 1:
                    display_artist = "Various Artists"

                # Cover art
                cover_url_row = covers_df[covers_df['release_id'] == release_id]
                if not cover_url_row.empty:
                    cover_url = cover_url_row['cover_url'].values[0]
                else:
                    cover_url = fetch_cover_from_discogs(release_id)
                    if cover_url:
                        save_cover_override(release_id, cover_url)

                cols = st.columns([1, 4])
                with cols[0]:
                    if cover_url:
                        st.image(cover_url, width=120)
                    else:
                        st.write("No cover available")

                with cols[1]:
                    st.markdown(f"**{album_title}**")
                    st.markdown(f"*Artist: {display_artist}*")

                    with st.expander("Click to view tracklist"):
                        display_cols = ['Track Title', 'Artist', 'CD', 'Track Number']
                        tracklist_df = group[display_cols].rename(columns={
                            'Track Title': 'Song',
                            'CD': 'Disc',
                            'Track Number': 'Track'
                        }).reset_index(drop=True)
                        st.dataframe(tracklist_df, hide_index=True)

                    with st.expander("Update Cover Art"):
                        new_url = st.text_input("Paste a new cover art URL:", key=f"url_{release_id}")
                        submit = st.button("Submit new cover art", key=f"submit_{release_id}")
                        reset = st.button("Reset to original cover", key=f"reset_{release_id}")

                        if submit and new_url:
                            save_cover_override(release_id, new_url)
                            st.success("Cover art updated. Reload the page to see changes.")
                        if reset:
                            remove_cover_override(release_id)
                            st.success("Cover art reset. Reload the page to fetch original cover.")
        else:
            st.subheader(f"Found {len(results)} result(s)")
            st.dataframe(results.reset_index(drop=True))

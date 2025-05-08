import streamlit as st
import pandas as pd
import os

# Load CSVs
DATA_CSV = 'expanded_discogs_tracklists.csv'
COVER_CSV = 'cover_overrides.csv'

# Load main data
@st.cache_data
def load_data():
    return pd.read_csv(DATA_CSV, encoding='latin1')

# Load cover overrides
@st.cache_data
def load_covers():
    if os.path.exists(COVER_CSV):
        return pd.read_csv(COVER_CSV)
    else:
        return pd.DataFrame(columns=['release_id', 'cover_url'])

# App title
st.markdown("""
# 🎵 **Music Search App**
""")

# Search inputs
search_query = st.text_input("Enter your search:")
search_by = st.radio("Search by:", ["Song Title", "Artist", "Album"], horizontal=True)
format_filter = st.selectbox("Format filter:", ["All", "Album", "Single", "Video", "Compilation"])

# Load data
df = load_data()
covers_df = load_covers()

if search_query:
    if search_by == "Song Title":
        filtered = df[df['Track Title'].str.contains(search_query, case=False, na=False)]
    elif search_by == "Artist":
        filtered = df[df['Artist'].str.contains(search_query, case=False, na=False)]
    else:
        filtered = df[df['Title'].str.contains(search_query, case=False, na=False)]

    if format_filter != "All":
        filtered = filtered[filtered['Format'].str.contains(format_filter, case=False, na=False)]

    if search_by == "Album":
        album_groups = filtered.groupby('release_id')
        st.markdown(f"**Found {len(album_groups)} album(s)**")

        for release_id, group in album_groups:
            album_title = group['Title'].iloc[0]
            artist_name = group['Artist'].iloc[0]
            # Show 'Various Artists' if multiple artists exist
            if group['Artist'].nunique() > 1:
                artist_name = "Various Artists"

            cover_url = covers_df[covers_df['release_id'] == release_id]['cover_url'].values
            if len(cover_url) > 0:
                img_url = cover_url[0]
            else:
                img_url = 'https://via.placeholder.com/150x150?text=No+Cover'

            col1, col2 = st.columns([1, 5])

            with col1:
                st.image(img_url, width=120)

            with col2:
                st.markdown(f"<h3 style='margin-bottom:0'>{album_title}</h3>", unsafe_allow_html=True)
                st.markdown(f"**Artist:** {artist_name}")

                with st.expander("Update Cover Art"):
                    new_url = st.text_input(f"Paste a new cover art URL:", key=f"newcover_{release_id}")
                    if st.button("Submit new cover art", key=f"submit_{release_id}"):
                        if new_url:
                            new_entry = pd.DataFrame({"release_id": [release_id], "cover_url": [new_url]})
                            covers_df = pd.concat([covers_df[covers_df['release_id'] != release_id], new_entry], ignore_index=True)
                            covers_df.to_csv(COVER_CSV, index=False)
                            st.success("Cover art updated!")

                with st.expander("Click to view tracklist"):
                    show_cols = ['Track Title', 'Artist', 'CD', 'Track Number']
                    tracklist = group[show_cols].rename(columns={
                        'Track Title': 'Song',
                        'Artist': 'Artist',
                        'CD': 'Disc',
                        'Track Number': 'Track'
                    }).reset_index(drop=True)
                    st.dataframe(tracklist, use_container_width=True)

    else:
        st.markdown(f"**Found {len(filtered)} result(s)**")
        st.dataframe(filtered, use_container_width=True)

else:
    st.info("Enter a search query to begin.")

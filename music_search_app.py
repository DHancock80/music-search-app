import streamlit as st
import pandas as pd

# Load data
@st.cache_data

def load_data():
    df = pd.read_csv("expanded_discogs_tracklists.csv", encoding_errors='replace')
    return df

df = load_data()

# App title (no icon)
st.title("Music Search App")

# Search input
search_term = st.text_input("Enter your search:")
search_by = st.radio("Search by:", ["Song Title", "Artist", "Album"], horizontal=True)
format_filter = st.selectbox("Format filter:", ["All", "Album", "Single", "Video"])

# Search logic
if search_term:
    if search_by == "Song Title":
        results = df[df['Track Title'].str.contains(search_term, case=False, na=False)]
    elif search_by == "Artist":
        results = df[df['Artist'].str.contains(search_term, case=False, na=False)]
    else:  # Album
        results = df[df['Title'].str.contains(search_term, case=False, na=False)]

    # Apply format filter
    if format_filter != "All":
        results = results[results['Format'].str.contains(format_filter, case=False, na=False)]

    # Group results by album (release_id)
    grouped = results.groupby("release_id")
    st.subheader(f"Found {grouped.ngroups} album(s)")

    for release_id, group in grouped:
        album_title = group['Title'].iloc[0]
        cover_url = group['cover_url'].iloc[0] if 'cover_url' in group else None

        # Artist label logic: show full if only one artist, else "Various Artists"
        unique_artists = group['Artist'].unique()
        if len(unique_artists) == 1:
            artist_label = unique_artists[0]
        else:
            artist_label = "Various Artists"

        cols = st.columns([1, 4])
        with cols[0]:
            if pd.notna(cover_url):
                st.image(cover_url, use_column_width=True)
            else:
                st.write("No cover available")

        with cols[1]:
            st.subheader(album_title)
            st.markdown(f"**Artist:** {artist_label}")

            # Update cover art expander
            with st.expander("Update Cover Art"):
                new_url = st.text_input(f"Paste a new cover art URL for release_id {release_id}:", key=f"input_{release_id}")
                if st.button("Submit new cover art", key=f"submit_{release_id}"):
                    st.success("Cover art submitted (not implemented in this test code)")

            # Tracklist expander (full width)
            with st.expander("Click to view tracklist", expanded=False):
                tracklist = group[['Track Title', 'Artist', 'CD', 'Track Number']]
                tracklist.columns = ['Song', 'Artist', 'Disc', 'Track']
                st.dataframe(tracklist, hide_index=True)

else:
    st.info("Enter a search term to begin.")

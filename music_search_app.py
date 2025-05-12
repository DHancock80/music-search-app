import streamlit as st
import pandas as pd
import os

# ---------- SETTINGS ----------
CSV_FILE = "expanded_discogs_tracklists.csv"
COVER_OVERRIDE_FILE = "cover_overrides.csv"

# ---------- LOAD DATA ----------
@st.cache_data
def load_data():
    try:
        df = pd.read_csv(CSV_FILE, encoding='latin1')
        cover_overrides = pd.read_csv(COVER_OVERRIDE_FILE)
    except Exception as e:
        st.error(f"Error loading the CSV file: {e}")
        return None, None
    return df, cover_overrides

df, cover_overrides = load_data()
if df is None:
    st.stop()

# ---------- TITLE ----------
st.markdown("# Music Search App")

# ---------- SEARCH BAR ----------
st.write("Enter your search:")
query = st.text_input("", value="")

st.write("Search by:")
search_type = st.radio("", ["Song Title", "Artist", "Album"], index=0)

# ---------- FORMAT FILTER ----------
st.write("Format filter:")
format_filter = st.selectbox("", ["All", "Album", "Single", "Video"])

# ---------- SEARCH LOGIC ----------
if query:
    query_lower = query.lower()

    if search_type == "Song Title":
        results = df[df['Track Title'].str.lower().str.contains(query_lower, na=False)]
    elif search_type == "Artist":
        results = df[df['Artist'].str.lower().str.contains(query_lower, na=False)]
    elif search_type == "Album":
        results = df[df['Title'].str.lower().str.contains(query_lower, na=False)]
    else:
        results = df.copy()

    # Apply format filter
    if format_filter != "All":
        results = results[results['Format'].str.lower().str.contains(format_filter.lower(), na=False)]

    # ---------- DISPLAY RESULTS ----------
    if search_type == "Album" and format_filter == "Album":
        # Group by release_id to show albums only
        album_groups = results.groupby('release_id')
        st.markdown(f"**Found {len(album_groups)} album(s)**")
        for release_id, group in album_groups:
            album_info = group.iloc[0]
            cover_url = None

            # Check cover override first
            override_match = cover_overrides[cover_overrides['release_id'] == release_id]
            if not override_match.empty:
                cover_url = override_match.iloc[0]['cover_url']

            # Display cover art
            cols = st.columns([1, 6])
            with cols[0]:
                if cover_url:
                    st.image(cover_url, width=100)
                else:
                    st.image("https://via.placeholder.com/100x100?text=No+Image", width=100)

            with cols[1]:
                st.subheader(album_info['Title'])
                artist_display = album_info['Artist']
                if artist_display.lower() in ["various", "various artists"]:
                    artist_display = "Various Artists"
                st.markdown(f"**Artist:** {artist_display}")

                # --- Cover Art Update Form ---
                with st.expander("Update Cover Art"):
                    new_cover_url = st.text_input(f"Paste a new cover art URL for Release ID {release_id}:")
                    if st.button(f"Submit new cover art for {release_id}"):
                        if new_cover_url:
                            updated = cover_overrides[cover_overrides['release_id'] != release_id]
                            new_row = pd.DataFrame({
                                'release_id': [release_id],
                                'cover_url': [new_cover_url]
                            })
                            updated = pd.concat([updated, new_row], ignore_index=True)
                            updated.to_csv(COVER_OVERRIDE_FILE, index=False)
                            st.success("✅ Cover art updated! Please reload the app to see changes.")
                        else:
                            st.warning("⚠️ Please enter a valid URL.")

                # --- Tracklist ---
                with st.expander("Click to view tracklist"):
                    tracklist = group[['Track Title', 'Artist', 'CD', 'Track Number']].rename(columns={
                        'Track Title': 'Song',
                        'Artist': 'Artist',
                        'CD': 'Disc',
                        'Track Number': 'Track'
                    }).reset_index(drop=True)
                    st.dataframe(tracklist, hide_index=True, use_container_width=True)

    else:
        # Show full results in table mode
        st.markdown(f"**Found {len(results)} result(s)**")
        st.dataframe(results.drop(columns=['Unnamed: 0'], errors='ignore'), use_container_width=True)


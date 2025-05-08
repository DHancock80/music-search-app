import streamlit as st
import pandas as pd
import requests

# Constants
CSV_FILE = 'expanded_discogs_tracklists.csv'
COVER_OVERRIDES_CSV = 'cover_overrides.csv'

# --- Load data ---
def load_data():
    return pd.read_csv(CSV_FILE, encoding='latin1')

def load_cover_overrides():
    try:
        return pd.read_csv(COVER_OVERRIDES_CSV)
    except FileNotFoundError:
        return pd.DataFrame(columns=['release_id', 'cover_url'])

# --- Save cover override ---
def save_cover_override(release_id, new_url):
    df = load_cover_overrides()
    df = df[df['release_id'] != release_id]
    new_entry = pd.DataFrame([[release_id, new_url]], columns=['release_id', 'cover_url'])
    df = pd.concat([df, new_entry], ignore_index=True)
    df.to_csv(COVER_OVERRIDES_CSV, index=False)

# --- Remove cover override ---
def remove_cover_override(release_id):
    df = load_cover_overrides()
    df = df[df['release_id'] != release_id]
    df.to_csv(COVER_OVERRIDES_CSV, index=False)

# --- Fetch cover art from Discogs ---
def fetch_cover_art(release_id):
    url = f"https://api.discogs.com/releases/{release_id}"
    headers = {"User-Agent": "MusicSearchApp/1.0"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            images = data.get("images", [])
            if images:
                return images[0].get("uri")
    except Exception:
        pass
    return None

# --- Main App ---
def main():
    st.title("🎵 Music Search App")

    df = load_data()
    covers_df = load_cover_overrides()

    search_query = st.text_input("Enter your search:")
    search_type = st.radio("Search by:", ['Song Title', 'Artist', 'Album'], horizontal=True)
    format_filter = st.selectbox("Format filter:", options=["All", "Album", "Single", "Compilation"])

    if search_query:
        search_col = {
            'Song Title': 'Track Title',
            'Artist': 'Artist',
            'Album': 'Title'
        }[search_type]

        results = df[df[search_col].str.contains(search_query, case=False, na=False)]

        if format_filter != "All":
            results = results[results['Format'].str.contains(format_filter, case=False, na=False)]

        if search_type == 'Album' and format_filter == 'Album':
            grouped = results.groupby(['release_id', 'Title'])

            st.subheader(f"Found {len(grouped)} album(s)")

            for (release_id, title), group in grouped:
                st.markdown("---")
                cover_url = None

                # Check for override
                override_row = covers_df[covers_df['release_id'] == release_id]
                if not override_row.empty:
                    cover_url = override_row.iloc[0]['cover_url']
                else:
                    cover_url = fetch_cover_art(release_id)
                    if cover_url:
                        save_cover_override(release_id, cover_url)

                # Album info: choose display artist smartly
                unique_artists = group['Artist'].dropna().unique()
                unique_artists = [a.strip() for a in unique_artists if a.strip()]
                if len(set(unique_artists)) == 1:
                    display_artist = unique_artists[0]
                else:
                    display_artist = "Various Artists"

                # Layout: cover + info side by side
                cols = st.columns([1, 4])
                with cols[0]:
                    if cover_url:
                        st.image(cover_url, width=120)
                    else:
                        st.text("No Cover")

                with cols[1]:
                    st.subheader(title)
                    st.markdown(f"**Artist:** {display_artist}")

                # BELOW: Update Cover Art (full width)
                with st.expander("Update Cover Art"):
                    new_url = st.text_input(f"Paste a new cover art URL for {title} (Release ID: {release_id}):", key=f"input_{release_id}")
                    if st.button("Submit new cover art", key=f"submit_{release_id}"):
                        if new_url:
                            save_cover_override(release_id, new_url)
                            st.success("Cover art updated! Please refresh to see changes.")
                    if st.button("Reset to original cover", key=f"reset_{release_id}"):
                        remove_cover_override(release_id)
                        st.success("Cover art reset to original! Please refresh to see changes.")

                # Expander for tracklist
                with st.expander("Click to view tracklist"):
                    show_cols = ['Track Title', 'Artist', 'CD', 'Track Number']
                    tracklist = group[show_cols].rename(columns={
                        'Track Title': 'Song',
                        'Artist': 'Artist',
                        'CD': 'Disc',
                        'Track Number': 'Track'
                    })
                    st.dataframe(tracklist, use_container_width=True, hide_index=True)

        else:
            st.subheader(f"Found {len(results)} result(s)")
            st.dataframe(results, use_container_width=True)

if __name__ == "__main__":
    main()

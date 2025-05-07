import streamlit as st
import pandas as pd
import requests
import os

# Load dataset
df = pd.read_csv("expanded_discogs_tracklists.csv", dtype=str, encoding="ISO-8859-1").fillna("")
st.write("CSV Columns:", df.columns.tolist())

# Load cover overrides
overrides_file = "cover_overrides.csv"
if os.path.exists(overrides_file):
    overrides_df = pd.read_csv(overrides_file, dtype=str).fillna("")
else:
    overrides_df = pd.DataFrame(columns=["release_id", "image_url"])

# Function to get cover art (override → Discogs → fallback)
@st.cache_data
def get_cover_url(release_id):
    # 1. Check override
    override_row = overrides_df[overrides_df["release_id"] == str(release_id)]
    if not override_row.empty:
        return override_row.iloc[0]["image_url"]

    # 2. Try Discogs API
    DISCOGS_TOKEN = st.secrets["discogs_token"]
    try:
        response = requests.get(
            f"https://api.discogs.com/releases/{release_id}",
            headers={"Authorization": f"Discogs token={DISCOGS_TOKEN}"}
        )
        if response.status_code == 200:
            data = response.json()
            if "images" in data and data["images"]:
                return data["images"][0]["uri"]
    except Exception:
        pass

    # 3. Default fallback image
    return "https://via.placeholder.com/100?text=No+Cover"

# Title
st.title("🎵 Music Collection Search")

# Search type
search_type = st.radio("Search by:", ["Song Title", "Artist"], horizontal=True)

# Search input
query = st.text_input("Enter search term:")

# Format filter as radio buttons side-by-side
format_col1, format_col2, format_col3 = st.columns(3)
with format_col1:
    include_album = st.checkbox("Album", value=True, key="format_album")
with format_col2:
    include_single = st.checkbox("Single", value=True, key="format_single")
with format_col3:
    include_video = st.checkbox("Video", value=True, key="format_video")

selected_formats = []
if include_album:
    selected_formats.append("Album")
if include_single:
    selected_formats.append("Single")
if include_video:
    selected_formats.append("Video")

# Search results
if query:
    if search_type == "Song Title":
        result = df[df["Track Title"].str.contains(query, case=False, na=False)]
    else:
        result = df[df["artist"].str.contains(query, case=False, na=False)]

    # Apply format filter
    if selected_formats:
        result = result[result["format"].isin(selected_formats)]

    # Display results
    for idx, row in result.iterrows():
        st.markdown("---")
        cols = st.columns([1, 3])

        with cols[0]:
            cover_url = get_cover_url(row["release_id"])
            st.image(cover_url, width=100)

        with cols[1]:
            st.markdown(f"**{row['Track_Title']}** by *{row['artist']}*")
            st.markdown(f"*Album:* {row['album_title']}")
            st.markdown(f"*Label:* {row['label']} | *Year:* {row['release_date']}")
            st.markdown(f"CD {row['disc_number']} - Track {row['track_number']}")

            # Cover image override upload
            with st.expander("Update cover art"):
                new_url = st.text_input(
                    f"Paste new image URL for release ID {row['release_id']}",
                    key=f"url_input_{row['release_id']}"
                )
                if new_url:
                    updated = overrides_df[overrides_df["release_id"] == row["release_id"]]
                    if not updated.empty:
                        overrides_df.loc[overrides_df["release_id"] == row["release_id"], "image_url"] = new_url
                    else:
                        overrides_df.loc[len(overrides_df.index)] = [row["release_id"], new_url]
                    overrides_df.to_csv(overrides_file, index=False)
                    st.success("Cover image updated — refresh to see change.")

# Footer
st.markdown("---")
st.caption("Built with ❤️ using Streamlit | Discogs API Integration")

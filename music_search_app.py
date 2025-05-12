import streamlit as st
import pandas as pd
from fuzzywuzzy import fuzz
from fuzzywuzzy import process
import base64

# Load data
df = pd.read_csv("expanded_discogs_tracklists.csv").fillna("")

# Clean artist names for better matching
def clean_artist_name(name):
    name = name.lower()
    name = name.replace("feat.", "").replace("ft.", "").replace("featuring", "")
    name = name.replace("&", ",").replace(" and ", ",")
    name = ''.join(c for c in name if c.isalnum() or c.isspace() or c == ',')
    return [part.strip() for part in name.split(",") if part.strip()]

df["clean_artists"] = df["Artist"].apply(clean_artist_name)

# Allow storing user-corrected cover art
if "cover_art_overrides" not in st.session_state:
    st.session_state.cover_art_overrides = {}

def fuzzy_search(query, choices, limit=10):
    return process.extract(query, choices, scorer=fuzz.token_sort_ratio, limit=limit)

def display_cover_art(release_id, default_url):
    url = st.session_state.cover_art_overrides.get(release_id, default_url)
    st.image(url, width=100)
    
    with st.expander("Update Cover Art"):
        new_url = st.text_input(f"Paste image URL for {release_id}", key=f"url_{release_id}")
        uploaded_image = st.file_uploader(f"Or upload an image", type=["png", "jpg", "jpeg"], key=f"upload_{release_id}")

        if new_url:
            st.session_state.cover_art_overrides[release_id] = new_url
            st.success("Cover art URL updated.")
        elif uploaded_image:
            image_data = base64.b64encode(uploaded_image.read()).decode()
            image_url = f"data:image/jpeg;base64,{image_data}"
            st.session_state.cover_art_overrides[release_id] = image_url
            st.success("Cover art uploaded.")

# UI Layout
st.title("🎵 Music Collection Search")

query = st.text_input("Search your collection...")
search_type = st.radio("Search by", ["Song", "Artist"], horizontal=True)
format_filter = st.multiselect("Filter by format", ["Album", "Single", "Video"], default=["Album", "Single"])

if st.button("Search") and query:
    result = df[df["Format"].isin(format_filter)]

    if search_type == "Song":
        matches = fuzzy_search(query, result["Track Title"].tolist())
        matched_titles = [match[0] for match in matches if match[1] > 70]
        result = result[result["Track Title"].isin(matched_titles)]
        result = result.sort_values("Track Title")
    else:
        result = result[result["clean_artists"].apply(lambda x: any(fuzz.partial_ratio(query.lower(), a) > 70 for a in x))]
        result = result.sort_values("Track Title")

    for _, row in result.iterrows():
        st.markdown("---")
        st.subheader(row["Track Title"])
        st.write(f"**Artist:** {row['Artist']}")
        st.write(f"**Album:** {row['Title']}")
        st.write(f"**Format:** {row['Format']} | **Disc:** {row['CD']} | **Track #:** {row['Track Number']}")
        display_cover_art(row["release_id"], f"https://api.discogs.com/releases/{row['release_id']}/images")

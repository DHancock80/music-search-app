import streamlit as st
import pandas as pd
import difflib
import os

st.set_page_config(page_title="Music Collection Search", layout="wide")

# Load main dataset
df = pd.read_csv("expanded_discogs_tracklists.csv", dtype=str, encoding="utf-8-sig").fillna("")

# Load cover overrides if available
COVER_OVERRIDE_FILE = "cover_overrides.csv"
if os.path.exists(COVER_OVERRIDE_FILE):
    cover_overrides = pd.read_csv(COVER_OVERRIDE_FILE, dtype=str).fillna("")
else:
    cover_overrides = pd.DataFrame(columns=["release_id", "cover_url"])

# Function to get cover art (with override)
def get_cover_art(release_id, default_url):
    override = cover_overrides[cover_overrides["release_id"] == str(release_id)]
    if not override.empty:
        return override["cover_url"].values[0]
    return default_url

# Save cover override
def save_cover_override(release_id, new_url):
    global cover_overrides
    cover_overrides = cover_overrides[cover_overrides["release_id"] != str(release_id)]
    cover_overrides = pd.concat([cover_overrides, pd.DataFrame([{"release_id": release_id, "cover_url": new_url}])], ignore_index=True)
    cover_overrides.to_csv(COVER_OVERRIDE_FILE, index=False)

st.title("🎵 Music Collection Search")

# Search input
search_type = st.radio("Search by:", ["Song Title", "Artist"], horizontal=True)
search_query = st.text_input("Enter your search query")

# Format filter (multi-select checkboxes instead of dropdown)
format_options = ["Album", "Single", "Video"]
selected_formats = st.multiselect("Filter by Format", options=format_options, default=format_options)

# Perform search if query is entered
if search_query:
    query = search_query.lower()
    result = df.copy()

    if search_type == "Song Title":
        result = result[result["Track Title"].str.lower().str.contains(query, na=False)]
    else:
        result = result[result["Artist"].str.lower().str.contains(query, na=False)]

    # Filter by format
    if selected_formats:
        result = result[
            result["Format"].str.contains("|".join(selected_formats), case=False, na=False)
        ]

    # Display results
    if not result.empty:
        for _, row in result.iterrows():
            with st.container():
                st.subheader(f"{row['Track Title']} - {row['Artist']}")
                st.markdown(f"**Album:** {row['Title']} ({row['Format']})")
                st.markdown(f"**Label:** {row['Label']}")
                st.markdown(f"**Released:** {row['Released']}")
                st.markdown(f"**CD:** {row['CD']} | **Track #:** {row['Track Number']}")

                # Show cover
                cover_url = get_cover_art(row["release_id"], f"https://api.discogs.com/releases/{row['release_id']}/images/0")
                st.image(cover_url, width=200)

                # Cover override
                with st.expander("Suggest a better cover image"):
                    new_url = st.text_input(f"Paste new image URL for release {row['release_id']}", key=f"url_{row['release_id']}")
                    uploaded_file = st.file_uploader("...or upload an image", type=["png", "jpg", "jpeg"], key=f"upload_{row['release_id']}")
                    if st.button("Submit Cover Update", key=f"submit_{row['release_id']}"):
                        if new_url:
                            save_cover_override(row["release_id"], new_url)
                            st.success("Cover updated with URL.")
                        elif uploaded_file:
                            # This uploads to Streamlit's temporary location; in a real app, use cloud storage instead
                            img_bytes = uploaded_file.read()
                            temp_path = f"temp_cover_{row['release_id']}.jpg"
                            with open(temp_path, "wb") as f:
                                f.write(img_bytes)
                            save_cover_override(row["release_id"], temp_path)
                            st.success("Cover updated with uploaded image.")

                st.markdown("---")
    else:
        st.warning("No results found. Try a different search or spelling.")

# Display search history (basic)
if "history" not in st.session_state:
    st.session_state.history = []
if search_query and search_query not in st.session_state.history:
    st.session_state.history.append(search_query)
if st.session_state.history:
    st.sidebar.subheader("🔍 Search History")
    for past_query in reversed(st.session_state.history[-10:]):
        st.sidebar.write(past_query)

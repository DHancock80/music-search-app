import streamlit as st
import pandas as pd
import difflib
import os

# --- Load your main music collection CSV ---
df = pd.read_csv("expanded_discogs_tracklists.csv", dtype=str).fillna("")

# --- Normalize data for fuzzy search ---
def normalize(text):
    if not isinstance(text, str):
        return ""
    text = text.lower()
    for sep in ['feat.', 'ft.', 'featuring', '&', ',', ' and ', '(', ')', '*', '[', ']', '#']:
        text = text.replace(sep, ' ')
    return ' '.join(text.split())

df['norm_artist'] = df['Artist'].apply(normalize)
df['norm_track'] = df['Track Title'].apply(normalize)

# --- Load or create override cover art ---
cover_override_path = "cover_overrides.csv"
if os.path.exists(cover_override_path):
    cover_overrides = pd.read_csv(cover_override_path, dtype=str).fillna("")
else:
    cover_overrides = pd.DataFrame(columns=["release_id", "custom_cover_url"])

# --- Save override cover art ---
def save_override(release_id, url):
    global cover_overrides
    cover_overrides = cover_overrides[cover_overrides["release_id"] != release_id]
    cover_overrides = pd.concat([cover_overrides, pd.DataFrame([{"release_id": release_id, "custom_cover_url": url}])])
    cover_overrides.to_csv(cover_override_path, index=False)

# --- Fuzzy search helper ---
def fuzzy_filter(query, choices):
    query = normalize(query)
    results = difflib.get_close_matches(query, choices, n=100, cutoff=0.4)
    return set(results)

# --- Streamlit UI ---
st.title("🎵 Music Collection Search")

query = st.text_input("Search for a song or artist:")

search_type = st.radio("Search by:", ["Song", "Artist"], horizontal=True)
format_filter = st.multiselect("Filter by Format:", ["Album", "Single", "Video"], default=["Album", "Single", "Video"])

if query:
    norm_query = normalize(query)

    if search_type == "Song":
        matches = fuzzy_filter(norm_query, df['norm_track'].unique())
        result = df[df['norm_track'].isin(matches)]
    else:
        matches = fuzzy_filter(norm_query, df['norm_artist'].unique())
        result = df[df['norm_artist'].isin(matches)]

    if format_filter:
        result = result[result["Format"].str.contains('|'.join(format_filter), case=False, na=False)]

    if not result.empty:
        for _, row in result.sort_values("Track Title").iterrows():
            st.markdown(f"### 🎶 {row['Track Title']}")
            st.markdown(f"- **Artist:** {row['Artist']}")
            st.markdown(f"- **Album:** {row['Title']}")
            st.markdown(f"- **Format:** {row['Format']}")
            st.markdown(f"- **Disc:** {row['CD']}  |  **Track #:** {row['Track Number']}")

            # --- Show cover image ---
            release_id = row["release_id"]
            override = cover_overrides[cover_overrides["release_id"] == release_id]
            if not override.empty:
                st.image(override["custom_cover_url"].values[0], width=200)
            else:
                st.image(f"https://img.discogs.com/{release_id}.jpg", width=200)

            # --- Cover image update form ---
            with st.expander("🖼️ Update Cover Art"):
                with st.form(key=f"cover_form_{release_id}"):
                    new_url = st.text_input("Paste new image URL:")
                    new_file = st.file_uploader("Or upload an image file:", type=["jpg", "png"])
                    submit = st.form_submit_button("Update Cover")

                    if submit:
                        if new_url:
                            save_override(release_id, new_url)
                            st.success("✅ Cover art updated via URL!")
                        elif new_file:
                            # Save uploaded file (simulate hosting)
                            save_path = f"https://your.image.host/{release_id}.jpg"
                            save_override(release_id, save_path)
                            st.success("✅ Cover art will be updated (simulation)")
    else:
        st.warning("No results found.")

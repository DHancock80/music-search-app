import streamlit as st
import pandas as pd
import re
import requests
import time
import base64
import shutil
import os
from datetime import datetime

# Constants
CSV_FILE = 'expanded_discogs_tracklists.csv'
COVER_OVERRIDES_FILE = 'cover_overrides.csv'
BACKUP_FOLDER = 'backups'
PLACEHOLDER_COVER = 'https://upload.wikimedia.org/wikipedia/commons/thumb/6/65/No-Image-Placeholder.svg/2048px-No-Image-Placeholder.svg.png'
DISCOGS_API_TOKEN = st.secrets["DISCOGS_API_TOKEN"]
GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
GITHUB_REPO = 'DHancock80/music-search-app'
GITHUB_BRANCH = 'main'
DISCOGS_ICON_PNG = 'https://upload.wikimedia.org/wikipedia/commons/thumb/f/fb/Discogs_Logo.png/120px-Discogs_Logo.png'

@st.cache_data
def load_data():
    try:
        df = pd.read_csv(CSV_FILE, encoding='latin1')
        if df.columns[0].startswith("Unnamed"):
            df = df.drop(columns=[df.columns[0]])
        if 'cover_art' not in df.columns:
            df['cover_art'] = None
        try:
            overrides = pd.read_csv(COVER_OVERRIDES_FILE, encoding='latin1', on_bad_lines='skip')
            overrides.columns = overrides.columns.str.strip().str.lower()
            if not {'release_id', 'cover_url'}.issubset(overrides.columns):
                st.warning("Overrides file missing required columns. Skipping override merge.")
                df['cover_art_final'] = df['cover_art']
            else:
                overrides = overrides.drop_duplicates(subset='release_id', keep='last')
                df = df.merge(overrides, on='release_id', how='left', suffixes=('', '_override'))
                df['cover_art_final'] = df['cover_url'].combine_first(df['cover_art'])
        except Exception as e:
            st.warning(f"Could not read cover overrides: {e}")
            df['cover_art_final'] = df['cover_art']
    except Exception as e:
        st.error(f"Error loading the CSV file: {e}")
        df = pd.DataFrame()
    return df

def upload_to_github(file_path, repo, token, branch, commit_message):
    api_url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    with open(file_path, "rb") as f:
        content = f.read()
    content_b64 = base64.b64encode(content).decode()
    get_resp = requests.get(api_url, headers=headers, params={"ref": branch})
    sha = get_resp.json()['sha'] if get_resp.status_code == 200 else None
    data = {
        "message": commit_message,
        "content": content_b64,
        "branch": branch
    }
    if sha:
        data["sha"] = sha
    response = requests.put(api_url, headers=headers, json=data)
    return response

def clean_artist_name(artist):
    if pd.isna(artist): return ''
    artist = artist.lower()
    artist = re.sub(r'[\*\(\)\[#]', '', artist)
    artist = re.sub(r'\s*(feat\.|ft\.|featuring)\s*', ' ', artist)
    artist = artist.replace('&', ' ').replace(',', ' ')
    return re.sub(r'\s+', ' ', artist).strip()

def search(df, query, search_type):
    query = query.lower().strip()
    if search_type == 'Song Title':
        return df[df['Track Title'].str.lower().str.contains(query, na=False)]
    elif search_type == 'Artist':
        df['artist_clean'] = df['Artist'].apply(clean_artist_name)
        return df[df['artist_clean'].str.contains(query, na=False)]
    elif search_type == 'Album':
        return df[df['Title'].str.lower().str.contains(query, na=False)]
    return df

def fetch_discogs_cover(release_id):
    headers = {"Authorization": f"Discogs token={DISCOGS_API_TOKEN}"}
    try:
        response = requests.get(f"https://api.discogs.com/releases/{release_id}", headers=headers)
        if response.status_code == 200:
            data = response.json()
            if 'images' in data and len(data['images']) > 0:
                return data['images'][0]['uri']
    except Exception as e:
        st.warning(f"Discogs fetch failed for {release_id}: {e}")
    return None

def update_cover_override(release_id, new_url):
    try:
        if not os.path.exists(BACKUP_FOLDER):
            os.makedirs(BACKUP_FOLDER)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = os.path.join(BACKUP_FOLDER, f"cover_overrides_backup_{timestamp}.csv")
        shutil.copy(COVER_OVERRIDES_FILE, backup_file)
        backups = sorted(os.listdir(BACKUP_FOLDER))
        if len(backups) > 10:
            os.remove(os.path.join(BACKUP_FOLDER, backups[0]))
    except Exception as e:
        st.error(f"Backup failed: {e}")

    try:
        overrides = pd.read_csv(COVER_OVERRIDES_FILE, encoding='latin1')
        overrides.columns = overrides.columns.str.strip().str.lower()
    except:
        overrides = pd.DataFrame(columns=['release_id', 'cover_url'])

    overrides = overrides[overrides['release_id'] != release_id]
    overrides = pd.concat([overrides, pd.DataFrame([{'release_id': release_id, 'cover_url': new_url}])], ignore_index=True)
    overrides.to_csv(COVER_OVERRIDES_FILE, index=False, encoding='latin1')
    upload_to_github(COVER_OVERRIDES_FILE, GITHUB_REPO, GITHUB_TOKEN, GITHUB_BRANCH, f"Update cover for {release_id}")
    st.success("✅ Custom cover art uploaded and synced to GitHub!")
    st.cache_data.clear()
    st.rerun()

def reset_cover_override(release_id):
    try:
        overrides = pd.read_csv(COVER_OVERRIDES_FILE, encoding='latin1')
        overrides.columns = overrides.columns.str.strip().str.lower()
        overrides = overrides[overrides['release_id'] != release_id]
        overrides.to_csv(COVER_OVERRIDES_FILE, index=False, encoding='latin1')
        upload_to_github(COVER_OVERRIDES_FILE, GITHUB_REPO, GITHUB_TOKEN, GITHUB_BRANCH, f"Reset cover for {release_id}")
        st.success("✅ Reverted to original cover art and synced to GitHub!")
        st.cache_data.clear()
        st.rerun()
    except Exception as e:
        st.error(f"Reset failed: {e}")

st.title('Music Search App')

search_query = st.text_input('Enter your search:', '')
search_type = st.radio('Search by:', ['Song Title', 'Artist', 'Album'], horizontal=True)

if search_query:
    df = load_data()
    results = search(df, search_query, search_type)

    unique_releases = results[['release_id', 'Format']].drop_duplicates()
    format_counts = {
        'All': len(results),
        'Album': unique_releases['Format'].str.contains("album|compilation|comp", case=False, na=False).sum(),
        'Single': unique_releases['Format'].str.contains("single", case=False, na=False).sum(),
        'Video': unique_releases['Format'].str.contains("video", case=False, na=False).sum()
    }

    format_filter = st.radio('Format:', [f"All ({format_counts['All']})", f"Album ({format_counts['Album']})", f"Single ({format_counts['Single']})", f"Video ({format_counts['Video']})"], horizontal=True)
    format_clean = format_filter.split()[0]

    if format_clean != 'All':
        pattern = 'album|compilation|comp' if format_clean == 'Album' else format_clean.lower()
        results = results[results['Format'].str.lower().str.contains(pattern, na=False)]

    if results.empty:
        st.info("No results found.")
    else:
        for release_id, group in results.groupby('release_id'):
            first_row = group.iloc[0]
            title = first_row['Title']
            artist = "Various Artists" if group['Artist'].nunique() > 1 else group['Artist'].iloc[0]
            cover_url = first_row.get('cover_art_final') or fetch_discogs_cover(release_id) or PLACEHOLDER_COVER

            cols = st.columns([1, 5])
            with cols[0]:
                st.markdown(f"""
                    <a href="{cover_url}" target="_blank">
                        <img src="{cover_url}" width="120" style="border-radius:8px;" />
                    </a>
                    <div style="margin-top:4px;font-size:14px;">
                        <a href="#" onclick="window.dispatchEvent(new CustomEvent('expandCoverArt', {{ detail: {release_id} }})); return false;" style="color:#1f77b4;text-decoration:underline;">Edit Cover Art</a>
                    </div>
                """, unsafe_allow_html=True)

            with cols[1]:
                st.markdown(f"""
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <div style="font-size:20px;font-weight:600;">{title}</div>
                        <a href="https://www.discogs.com/release/{release_id}" target="_blank">
                            <img src="{DISCOGS_ICON_PNG}" alt="Discogs" width="20" style="margin-left:10px;" />
                        </a>
                    </div>
                    <div><strong>Artist:</strong> {artist}</div>
                """, unsafe_allow_html=True)

            if f'show_expander_{release_id}' not in st.session_state:
                st.session_state[f'show_expander_{release_id}'] = False

            if st.session_state.get(f'show_expander_{release_id}', False):
                with st.expander("Update Cover Art", expanded=True):
                    with st.form(f"form_{release_id}"):
                        new_url = st.text_input("Custom cover art URL:", key=f"url_{release_id}")
                        cols = st.columns(2)
                        with cols[0]:
                            if st.form_submit_button("Upload custom URL"):
                                update_cover_override(release_id, new_url)
                        with cols[1]:
                            if st.form_submit_button("Revert to original Cover Art"):
                                reset_cover_override(release_id)

            st.markdown(f"""
                <script>
                    window.addEventListener('expandCoverArt', function(e) {{
                        fetch(window.location.href, {{
                            method: 'POST',
                            headers: {{ 'Content-Type': 'application/json' }},
                            body: JSON.stringify({{ action: 'toggle_expander', release_id: e.detail }})
                        }}).then(() => window.location.reload());
                    }});
                </script>
            """, unsafe_allow_html=True)

            with st.expander("Click to view tracklist"):
                st.dataframe(group[['Track Title', 'Artist', 'CD', 'Track Number']].rename(columns={
                    'Track Title': 'Song', 'CD': 'Disc', 'Track Number': 'Track'
                }).reset_index(drop=True), use_container_width=True, hide_index=True)
else:
    st.caption("Please enter a search query above.")

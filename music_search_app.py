import streamlit as st
import pandas as pd
from utils import load_data, get_suggestions, verify_secrets, normalize
from ui_components import (
    setup_page, render_header, render_search_box, render_format_filter,
    render_sort_options, render_album_card, display_suggestions
)

def initialize_session_state():
    """Initialize session state variables"""
    if 'open_expander_id' not in st.session_state:
        st.session_state['open_expander_id'] = None
    if 'last_search' not in st.session_state:
        st.session_state['last_search'] = None

def filter_by_format(results, format_filter):
    """Filter results by format"""
    if format_filter == 'All':
        return results
    elif format_filter == 'Album':
        pattern = 'album|compilation|comp'
    else:
        pattern = format_filter.lower()
    
    return results[results['Format'].str.lower().str.contains(pattern, na=False)]

def prepare_format_counts(results):
    """Count results by format type"""
    if results.empty:
        return {'All': 0, 'Album': 0, 'Single': 0, 'Video': 0}
    
    unique_releases = results[['release_id', 'Format']].drop_duplicates()
    return {
        'All': len(unique_releases),
        'Album': unique_releases['Format'].str.contains("album|compilation|comp", case=False, na=False).sum(),
        'Single': unique_releases['Format'].str.contains("single", case=False, na=False).sum(),
        'Video': unique_releases['Format'].str.contains("video", case=False, na=False).sum()
    }

def sort_results(releases_data, sort_option):
    """Sort releases based on selected sort option"""
    if sort_option == "Relevance":
        # Default order (no change)
        return releases_data
    
    # Extract the sort key and direction
    if "Album Title" in sort_option:
        key = "title"
    elif "Artist" in sort_option:
        key = "artist"
    elif "Release Date" in sort_option:
        key = "released"
    else:
        return releases_data
    
    # Determine sort direction
    ascending = "(A-Z)" in sort_option or "(Oldest)" in sort_option
    
    # Sort the releases
    return sorted(
        releases_data,
        key=lambda x: str(x.get(key, "")) if x.get(key) is not None else "",
        reverse=not ascending
    )

def group_by_release(results):
    """Group results by release ID and prepare data for display"""
    releases_data = []
    
    for release_id, group in results.groupby('release_id'):
        first = group.iloc[0]
        # Convert release date to datetime for proper sorting
        release_date = pd.to_datetime(first.get('Released'), errors='coerce')
        
        releases_data.append({
            'release_id': release_id,
            'cover_art_final': first.get('cover_art_final'),
            'artist': "Various Artists" if group['Artist'].nunique() > 1 else group['Artist'].iloc[0],
            'title': first['Title'],
            'released': first.get('Released'),
            'release_date': release_date,  # For sorting
            'format': first.get('Format', ''),
            'tracks': group
        })
    
    return releases_data

def main():
    """Main application function"""
    secrets = verify_secrets()
    setup_page()
    initialize_session_state()
    
    # Load data once at the beginning
    df = load_data(secrets)
    
    render_header()
    
    # Handle search
    search_params = render_search_box(df)
    query = search_params["query"]
    search_type = search_params["type"]
    field = search_params["field"]
    
    # Show suggestions if typing
    if st.session_state.get('show_suggestions', False) and len(query) >= 2:
        suggestions = get_suggestions(df, field, query)
        display_suggestions(suggestions)
    
    # Process search results
    if query and len(query) >= 2:
        # Apply fuzzy search on the specified field
        mask = df[field].apply(lambda x: normalize(str(x))).str.contains(normalize(query), na=False)
        results = df[mask]
        
        # Update session state to remember this search
        st.session_state['last_search'] = {
            "query": query,
            "type": search_type,
            "results_count": len(results)
        }
        
        if results.empty:
            st.warning("No results found. Try a different search term or category.")
        else:
            # Format counts for filter
            format_counts = prepare_format_counts(results)
            
            # Create a container for controls
            with st.container():
                st.markdown("<div class='controls-container'>", unsafe_allow_html=True)
                col1, col2 = st.columns(2)
                
                with col1:
                    format_filter = render_format_filter(format_counts)
                
                with col2:
                    sort_option = render_sort_options()
                
                st.markdown("</div>", unsafe_allow_html=True)
            
            # Filter by format
            results = filter_by_format(results, format_filter)
            
            if results.empty:
                st.warning(f"No results found for format: {format_filter}")
            else:
                # Group by release
                releases_data = group_by_release(results)
                
                # Sort releases
                sorted_releases = sort_results(releases_data, sort_option)
                
                # Display results
                st.markdown(f"### Found {len(sorted_releases)} releases")
                
                for idx, release in enumerate(sorted_releases):
                    render_album_card(release, secrets, idx)
    else:
        st.markdown("""
        <div style="text-align: center; padding: 3rem 1rem;">
            <h3>Welcome to your Music Collection Search!</h3>
            <p>Enter a search term above to find music in your collection.</p>
            <p>You can search by song title, artist, or album name.</p>
        </div>
        """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()

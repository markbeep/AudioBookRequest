# MAM & ARR-like Enhancements Plan

This plan outlines the steps to transform AudioBookRequest into a more comprehensive "Arr-like" application with automated download handling, media management, and enhanced metadata integration.

## Phase 1: Infrastructure & Configuration
- [ ] **Database Schema Updates:**
    - Add `Config` entries for qBittorrent: `qbit_host`, `qbit_port`, `qbit_user`, `qbit_pass`, `qbit_category`, `qbit_save_path`.
    - Add `Config` entries for Media Management: `library_path`, `folder_pattern` (e.g., `{author}/{series}/{series} - {index} - {title} ({year})`), `use_series_folders`.
- [ ] **Settings UI:**
    - Create a new "Download Client" settings page for qBittorrent configuration.
    - Create a "Media Management" settings page.

## Phase 2: qBittorrent Integration
- [ ] **Client Implementation:**
    - Implement `app/internal/download_clients/qbittorrent.py` using `aiohttp`.
    - Support: `add_torrent`, `get_torrent_status`, `remove_torrent`, `set_category`.
- [ ] **Download Orchestration:**
    - Update `start_download` in `app/internal/prowlarr/prowlarr.py` (or a new wrapper) to optionally bypass Prowlarr's internal client handling if we want direct control via qBittorrent API (for better tagging/tracking).

## Phase 3: Post-Processing Pipeline
- [ ] **Background Worker:**
    - Implement a periodic task (e.g., every 1-5 minutes) that:
        1. Queries qBittorrent for completed torrents in the specified category.
        2. Identifies the corresponding `AudiobookRequest` or `ManualBookRequest`.
- [ ] **Metadata Enrichment:**
    - Ensure MAM metadata is fully fetched (including Series, Year, Description).
    - Fetch Audible metadata if available for high-quality covers and additional info.
- [ ] **File Management:**
    - Implement `app/internal/processing/processor.py`.
    - Move/Rename files from the download directory to the `library_path` based on the naming pattern.
    - Clean up temporary files/folders.
- [ ] **Metadata File Generation:**
    - Generate `metadata.json` in Audiobookshelf format.
    - Generate `metadata.opf` for broader compatibility.
    - Save `cover.jpg` in the book folder.

## Phase 4: Audiobookshelf Integration
- [ ] **Library Sync:**
    - Automatically trigger an ABS library scan via `abs_trigger_scan` once processing is complete.
    - Mark the book as `downloaded` in the local database.

## Phase 5: UI/UX Improvements
- [ ] **Download Progress:**
    - Update the Wishlist/Downloaded pages to show real-time progress for active downloads (via qBittorrent API).
- [ ] **Manual Overrides:**
    - Add a "Re-process" button for books to regenerate metadata or fix folder structures.
- [ ] **Logs/Status:**
    - Add a status dashboard to see what's currently being searched, downloaded, or processed.

## Phase 6: MAM Specific Polish
- [ ] **Enhanced Scraping:**
    - Improve MAM scraping to handle various edge cases in series naming and multi-book torrents.
    - Support for MAM "Personal Freeleech" tokens if applicable.

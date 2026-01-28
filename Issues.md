# Issues / TODO

- [ ] Default matching is matching to the incorrect language. (tentative fix: import match/manual rematch now use user default region; verify)
- [ ] Manual search page: "massive forehead on the manule search page" (tentative fix: removed center layout; verify)
- [ ] Buttons don't fit on books wishlist on mobile. (tentative fix: actions wrap/stack on mobile; verify)
- [ ] There shouldn't be multiple series for one book. (tentative fix: normalize to a single series entry; verify)
- [ ] Books should have a number for their order in the series. (tentative fix: added series_index field + filename/metadata/UI display; verify data source)
- [ ] Manual search on mobile shows weird buttons. (tentative fix: stacked header/form; verify)
- [ ] Radio switching button in some settings doesn't fit on the page on mobile. (tentative fix: qBittorrent toggle stacks on mobile; verify)
- [ ] No indication of autodownload; user reports it likely doesn't work. (tentative fix: better error for misconfigured Prowlarr; verify)
- [ ] Handle download already being complete in the client. (tentative fix: if torrent already exists, track it instead of failing; verify)
- [ ] Handle settings change while downloading. (tentative fix: monitor falls back to all torrents if hash not found; verify)
- [ ] Don't track audiobooks already seeding in the download client's category for audiobooks. (tentative fix: ignore torrents without asin tag; verify)
- [ ] Percentage downloading not updating as quickly as speed on the downloading page.
- [ ] "Download complete" option should be copy or hardlinks (setting), not moved. (tentative fix: added explicit complete-action setting; verify)
- [ ] Send a library scan or rematch scan to Audiobookshelf when needed. (tentative fix: rematch now triggers ABS scan; verify)
- [ ] Ensure metadata and renaming happens when rematching a book after import. (tentative fix: rematch now reorganizes files + metadata; verify)
- [ ] Web UI freezes on import. (tentative fix: importer now runs as async task to avoid blocking UI; verify)
- [ ] Manual match on import shows blurred screen and no popup. (tentative fix: dialog now opens with `open` attribute; verify)

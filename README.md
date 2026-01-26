# Narrarr

Self-hosted audiobook requests + automation with a polished UI and improved import matching.

<img width="2333" height="1251" alt="image" src="https://github.com/user-attachments/assets/48f167fd-5cf6-418d-a0ed-dfe5e9ccac34" />
<img width="1624" height="1132" alt="image" src="https://github.com/user-attachments/assets/5ae568f5-d3d4-4d2c-bda6-f55f3acc8308" />


Original project and credit: `https://github.com/markbeep/AudioBookRequest`

## Features
- Request and wishlist flow
- Automated downloads (Prowlarr + qBittorrent)
- Manual and automatic matching for imports
- Audiobookshelf integration
- Import/reconcile library tools
- Stats and basic admin settings

## Quick Start (Docker)
```bash
docker run -p 8000:8000 \
  -v ./config:/config \
  -v ./library:/library \
  ghcr.io/zippy-boy/narrarr:latest
```

## Docker Compose
```yaml
services:
  audiobookrequest:
    image: ghcr.io/zippy-boy/narrarr:latest
    ports:
      - "8000:8000"
    environment:
      - ABR_APP__CONFIG_DIR=/config
    volumes:
      - ./config:/config
      - ./library:/library
```

## Configuration
Common env vars:
```text
ABR_APP__CONFIG_DIR=/config
ABR_APP__DEBUG=false
ABR_APP__OPENAPI_ENABLED=false
ABR_APP__DEFAULT_REGION=us
```

## Optional Services
- Postgres (use when you want a dedicated DB):
  ```text
  ABR_DB__USE_POSTGRES=true
  ABR_DB__POSTGRES_HOST=postgres
  ABR_DB__POSTGRES_PORT=5432
  ABR_DB__POSTGRES_USER=postgres
  ABR_DB__POSTGRES_PASSWORD=postgres
  ABR_DB__POSTGRES_DB=postgres
  ```
- Gotify (only if you want notifications):
  Configure in the app settings after the container is running.

## License
Same license as the original project. See `LICENSE`.

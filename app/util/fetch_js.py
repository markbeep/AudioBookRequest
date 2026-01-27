"""
To fetch javascript files for local development
"""

import requests
from pathlib import Path

files = {
    "htmx-preload.js": "https://unpkg.com/htmx-ext-preload@2.1.0/preload.js",
    "htmx.js": "https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js",
    "alpine.js": "https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js",
    "toastify.js": "https://cdn.jsdelivr.net/npm/toastify-js",
    "toastify.css": "https://cdn.jsdelivr.net/npm/toastify-js/src/toastify.min.css",
}


def fetch_scripts(debug: bool) -> None:
    root = Path("static")
    root.mkdir(parents=True, exist_ok=True)

    if debug:
        if all((root / file_name).exists() for file_name in files.keys()):
            return

        for file_name, url in files.items():
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
            except requests.RequestException as e:
                raise Exception(f"Failed to fetch {file_name} from {url}: {e}") from e
            with open(root / file_name, "w") as f:
                f.write(response.text)

    else:
        for file_name in files.keys():
            if not (root / file_name).exists():
                raise FileNotFoundError(
                    f"{file_name} must be present in static directory for production. This is most likely an error with the docker image."
                )


if __name__ == "__main__":
    fetch_scripts(True)

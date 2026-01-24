import aiohttp

from app.internal.env_settings import Settings


async def get_connection():
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(30)) as session:
        yield session


USER_AGENT = (
    f"Narrarr/{Settings().app.version} (+https://github.com/markbeep/AudioBookRequest)"
)

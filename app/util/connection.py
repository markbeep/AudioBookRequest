import aiohttp


async def get_connection():
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(30)) as session:
        yield session

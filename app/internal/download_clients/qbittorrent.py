import aiohttp
from typing import Optional, List, Dict, Any
from app.util.log import logger
from app.internal.download_clients.config import download_client_config
from sqlmodel import Session


class QbittorrentClient:
    def __init__(
        self,
        session: Session,
        host: Optional[str] = None,
        port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.session = session

        # Use provided values or fall back to config
        host = host or download_client_config.get_qbit_host(session) or "localhost"
        port = port or download_client_config.get_qbit_port(session)
        self.username = (
            username
            if username is not None
            else download_client_config.get_qbit_user(session)
        )
        self.password = (
            password
            if password is not None
            else download_client_config.get_qbit_pass(session)
        )

        # Robustly handle host/port/protocol
        if "://" in host:
            self.base_url = host.rstrip("/")
        else:
            self.base_url = f"http://{host}:{port}".rstrip("/")

        self.host = host
        self.port = port
        self.cookies = None

    async def _login(self, client: aiohttp.ClientSession) -> tuple[bool, int, str]:
        url = f"{self.base_url}/api/v2/auth/login"
        # logger.debug("qBittorrent: Attempting login", url=url, user=self.username)
        data = {"username": self.username, "password": self.password}
        self.headers = {
            "User-Agent": "Narrarr",
        }
        try:
            async with client.post(url, data=data, headers=self.headers) as resp:
                text = await resp.text()
                if resp.status == 200:
                    self.cookies = resp.cookies
                    return True, resp.status, text
                logger.error(
                    "qBittorrent login failed",
                    status=resp.status,
                    url=url,
                    response=text,
                )
                return False, resp.status, text
        except Exception as e:
            logger.error("qBittorrent login exception", error=str(e), url=url)
            return False, 0, str(e)

    async def add_torrent(
        self,
        torrent_data: str,
        is_magnet: bool = True,
        category: Optional[str] = None,
        save_path: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> bool:
        if not self.host:
            return False

        async with aiohttp.ClientSession() as client:
            success, _, _ = await self._login(client)
            if not success:
                return False

            url = f"{self.base_url}/api/v2/torrents/add"
            data = aiohttp.FormData()

            if is_magnet:
                data.add_field("urls", torrent_data)
            else:
                data.add_field("torrents", torrent_data, filename="torrent.torrent")

            if category:
                data.add_field("category", category)
            elif default_cat := download_client_config.get_qbit_category(self.session):
                data.add_field("category", default_cat)

            final_save_path = None
            if save_path:
                final_save_path = save_path
            elif default_path := download_client_config.get_qbit_save_path(
                self.session
            ):
                final_save_path = default_path

            if final_save_path:
                logger.debug("qBittorrent: Using save path", path=final_save_path)
                data.add_field("savepath", final_save_path)
                data.add_field("useAutoTMM", "false")  # Force respect of savepath

            if tags:
                data.add_field("tags", ",".join(tags))

            try:
                async with client.post(url, data=data, cookies=self.cookies) as resp:
                    if resp.status == 200:
                        logger.info(
                            "Successfully added torrent to qBittorrent",
                            path=final_save_path,
                        )
                        return True
                    logger.error(
                        "Failed to add torrent to qBittorrent",
                        status=resp.status,
                        text=await resp.text(),
                    )
                    return False
            except Exception as e:
                logger.error("qBittorrent add_torrent exception", error=str(e))
                return False

    async def get_torrents(
        self, category: Optional[str] = None, filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        if not self.host:
            return []

        async with aiohttp.ClientSession() as client:
            success, _, _ = await self._login(client)
            if not success:
                return []

            url = f"{self.base_url}/api/v2/torrents/info"
            params = {}
            if category:
                params["category"] = category
            if filter:
                params["filter"] = filter

            try:
                async with client.get(url, params=params, cookies=self.cookies) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    return []
            except Exception as e:
                logger.error("qBittorrent get_torrents exception", error=str(e))
                return []

    async def test_connection(self) -> tuple[bool, int, str]:
        if not self.host:
            return False, 0, "No host configured"
        async with aiohttp.ClientSession() as client:
            return await self._login(client)

    async def add_torrent_tags(self, hash: str, tags: List[str]) -> bool:
        if not self.host:
            return False
        async with aiohttp.ClientSession() as client:
            success, _, _ = await self._login(client)
            if not success:
                return False
            url = f"{self.base_url}/api/v2/torrents/addTags"
            data = {"hashes": hash, "tags": ",".join(tags)}
            async with client.post(url, data=data, cookies=self.cookies) as resp:
                return resp.status == 200

    async def delete_torrent(self, hash: str, delete_files: bool = False) -> bool:
        if not self.host:
            return False
        async with aiohttp.ClientSession() as client:
            success, _, _ = await self._login(client)
            if not success:
                return False
            url = f"{self.base_url}/api/v2/torrents/delete"
            data = {"hashes": hash, "deleteFiles": "true" if delete_files else "false"}
            async with client.post(url, data=data, cookies=self.cookies) as resp:
                if resp.status == 200:
                    logger.info(
                        "Successfully deleted torrent from qBittorrent",
                        hash=hash,
                        delete_files=delete_files,
                    )
                    return True
                logger.error(
                    "Failed to delete torrent from qBittorrent",
                    status=resp.status,
                    hash=hash,
                )
                return False

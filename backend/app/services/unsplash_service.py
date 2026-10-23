"""Unsplash图片服务"""

import httpx
from typing import List, Optional
from ..config import get_settings
from .external_calls import CallPolicy, ExternalServiceError, invoke_external

class UnsplashService:
    """Unsplash图片服务类"""

    def __init__(self):
        """初始化服务"""
        settings = get_settings()
        self.access_key = settings.unsplash_access_key
        self.base_url = "https://api.unsplash.com"

    async def search_photos(self, query: str, per_page: int = 5) -> List[dict]:
        """
        搜索图片

        Args:
            query: 搜索关键词
            per_page: 每页数量

        Returns:
            图片列表
        """
        if not self.access_key:
            return []
        try:
            return await invoke_external('unsplash', 'search_photos',
                lambda: self._search_photos(query, per_page),
                policy=CallPolicy(total_timeout=10, attempt_timeout=8, max_attempts=1, concurrency=2))
        except ExternalServiceError:
            print("❌ Unsplash搜索失败，暂不显示封面图片")
            return []

    async def _search_photos(self, query, per_page):
        url = f"{self.base_url}/search/photos"
        params = {
            "query": query,
            "per_page": per_page,
            "client_id": self.access_key
        }

        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.get(url, params=params)
        response.raise_for_status()

        data = response.json()
        results = data.get("results", [])

        # 提取图片URL
        photos = []
        for photo in results:
            photos.append({
                "id": photo.get("id"),
                "url": photo.get("urls", {}).get("regular"),
                "thumb": photo.get("urls", {}).get("thumb"),
                "description": photo.get("description") or photo.get("alt_description"),
                "photographer": photo.get("user", {}).get("name")
            })

        return photos


    async def get_photo_url(self, query: str) -> Optional[str]:
        """
        获取单张图片URL

        Args:
            query: 搜索关键词

        Returns:
            图片URL
        """
        photos = await self.search_photos(query, per_page=1)
        if photos:
            return photos[0].get("url")
        return None


# 全局服务实例
_unsplash_service = None


def get_unsplash_service() -> UnsplashService:
    """获取Unsplash服务实例(单例模式)"""
    global _unsplash_service

    if _unsplash_service is None:
        _unsplash_service = UnsplashService()

    return _unsplash_service


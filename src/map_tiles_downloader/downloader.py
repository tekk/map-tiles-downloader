from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence, Callable

import aiohttp
import aiofiles
from tqdm import tqdm


@dataclass
class TileRequest:
    zoom: int
    x: int
    y: int
    area_label: Optional[str] = None


class TileDownloader:
    def __init__(
        self,
        output_dir: Path,
        url_builder: Callable[[int, int, int], str],
        headers: Optional[dict] = None,
        concurrent_requests: int = 20,
        request_timeout_seconds: float = 10.0,
        retry_attempts: int = 3,
        inter_request_delay_seconds: float = 0.05,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.url_builder = url_builder
        self.headers = headers or {}
        self.concurrent_requests = concurrent_requests
        self.request_timeout_seconds = request_timeout_seconds
        self.retry_attempts = retry_attempts
        self.inter_request_delay_seconds = inter_request_delay_seconds

        os.makedirs(self.output_dir, exist_ok=True)

        # Control flags for interactive UIs
        self.paused: bool = False
        self.cancelled: bool = False

    def _tile_url(self, zoom: int, x: int, y: int) -> str:
        return self.url_builder(zoom, x, y)

    def _tile_path(self, zoom: int, x: int, y: int) -> Path:
        return self.output_dir / str(zoom) / str(x) / f"{y}.png"

    async def _download_one(
        self,
        session: aiohttp.ClientSession,
        semaphore: asyncio.Semaphore,
        req: TileRequest,
        pbar: Optional[tqdm],
        on_progress: Optional[Callable[[str, TileRequest, int], None]],
    ) -> bool:
        tile_dir = self._tile_path(req.zoom, req.x, req.y).parent
        tile_path = self._tile_path(req.zoom, req.x, req.y)

        # Honor pause/cancel
        while self.paused and not self.cancelled:
            await asyncio.sleep(0.1)
        if self.cancelled:
            return False

        if tile_path.exists():
            if pbar:
                pbar.update(1)
            if on_progress:
                on_progress("skipped", req, 0)
            return True

        async with semaphore:
            try:
                os.makedirs(tile_dir, exist_ok=True)
                for attempt in range(self.retry_attempts):
                    try:
                        timeout = aiohttp.ClientTimeout(total=self.request_timeout_seconds)
                        # Re-check pause/cancel between attempts
                        while self.paused and not self.cancelled:
                            await asyncio.sleep(0.1)
                        if self.cancelled:
                            return False

                        async with session.get(
                            self._tile_url(req.zoom, req.x, req.y),
                            headers=self.headers,
                            timeout=timeout,
                        ) as response:
                            if response.status == 200:
                                content = await response.read()
                                async with aiofiles.open(tile_path, "wb") as f:
                                    await f.write(content)
                                await asyncio.sleep(self.inter_request_delay_seconds)
                                if pbar:
                                    pbar.update(1)
                                if on_progress:
                                    on_progress("success", req, len(content))
                                return True
                            elif response.status == 429:
                                await asyncio.sleep(2**attempt)
                                continue
                            else:
                                # Non-retryable HTTP error
                                if on_progress:
                                    on_progress("failed", req, 0)
                                return False
                    except asyncio.TimeoutError:
                        if attempt < self.retry_attempts - 1:
                            await asyncio.sleep(1)
                        continue
                    except Exception:
                        # Unexpected error; don't keep retrying
                        if on_progress:
                            on_progress("failed", req, 0)
                        return False
                return False
            except Exception:
                if pbar:
                    pbar.update(1)
                if on_progress:
                    on_progress("failed", req, 0)
                return False

    async def download(
        self,
        requests: Sequence[TileRequest],
        on_progress: Optional[Callable[[str, TileRequest, int], None]] = None,
    ) -> None:
        semaphore = asyncio.Semaphore(self.concurrent_requests)
        async with aiohttp.ClientSession() as session:
            if on_progress is None:
                with tqdm(total=len(requests), desc="Downloading tiles") as pbar:
                    tasks = [
                        self._download_one(session, semaphore, req, pbar, None) for req in requests
                    ]
                    await asyncio.gather(*tasks)
            else:
                tasks = [
                    self._download_one(session, semaphore, req, None, on_progress)
                    for req in requests
                ]
                await asyncio.gather(*tasks)

    # Control methods for interactive UIs
    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self.paused = False

    def cancel(self) -> None:
        self.cancelled = True

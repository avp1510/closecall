#!/usr/bin/env python3
"""Small, dependency-free client for the VAST VSS video API."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_API_URL = "https://team-15-vss.thecosmoslabs.com/api/v1"


class VSSAPIError(RuntimeError):
    """An error returned by the VSS API."""


class VSSClient:
    def __init__(
        self,
        api_url: str = DEFAULT_API_URL,
        token: str | None = None,
        *,
        timeout: float = 60,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._opener = opener

    def login(self, username: str, password: str) -> str:
        response = self._request(
            "POST",
            "/auth/login",
            json_body={"username": username, "password": password},
            authenticated=False,
        )
        token = response.get("access_token") if isinstance(response, dict) else None
        if not token:
            raise VSSAPIError("Login succeeded but the response had no access_token")
        self.token = str(token)
        return self.token

    def explore(
        self,
        *,
        scope: str = "all",
        limit: int = 48,
        offset: int = 0,
        date: str | None = None,
        location: str | None = None,
    ) -> Any:
        params: dict[str, str | int] = {
            "scope": scope,
            "limit": limit,
            "offset": offset,
        }
        if date:
            params["date"] = date
        if location:
            params["location"] = location
        return self._request("GET", "/videos/explore", params=params)

    def metadata(self, source: str) -> Any:
        return self._request("GET", "/videos/metadata", params={"source": source})

    def detections(self, source: str) -> Any:
        return self._request("GET", "/videos/detections", params={"source": source})

    def search(self, query: str, *, top_k: int = 12) -> Any:
        return self._request(
            "POST",
            "/search",
            json_body={
                "query": query,
                "top_k": top_k,
                "tags": [],
                "include_public": True,
            },
        )

    def playback_url(self, source: str, *, expires_in: int = 3600) -> Any:
        token = self._require_token()
        return self._request(
            "GET",
            "/videos/playback-url",
            params={"source": source, "token": token, "expires_in": expires_in},
        )

    def download(self, source: str, destination: Path) -> Path:
        """Download a video atomically through the authenticated stream endpoint."""
        token = self._require_token()
        url = self._url(
            "/videos/stream",
            {"source": source, "token": token},
        )
        request = Request(url, headers={"Authorization": f"Bearer {token}"})
        destination = destination.expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)

        temporary_path: Path | None = None
        try:
            with self._opener(request, timeout=self.timeout) as response:
                with tempfile.NamedTemporaryFile(
                    dir=destination.parent,
                    prefix=f".{destination.name}.",
                    delete=False,
                ) as temporary:
                    temporary_path = Path(temporary.name)
                    shutil.copyfileobj(response, temporary)
            temporary_path.replace(destination)
            return destination
        except (HTTPError, URLError, OSError) as error:
            if temporary_path:
                temporary_path.unlink(missing_ok=True)
            raise self._friendly_error(error) from error

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        authenticated: bool = True,
    ) -> Any:
        headers = {"Accept": "application/json"}
        if authenticated:
            headers["Authorization"] = f"Bearer {self._require_token()}"

        body = None
        if json_body is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(json_body).encode("utf-8")

        request = Request(
            self._url(path, params),
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with self._opener(request, timeout=self.timeout) as response:
                payload = response.read()
                return json.loads(payload) if payload else None
        except (HTTPError, URLError, json.JSONDecodeError) as error:
            raise self._friendly_error(error) from error

    def _url(self, path: str, params: dict[str, Any] | None = None) -> str:
        url = f"{self.api_url}/{path.lstrip('/')}"
        return f"{url}?{urlencode(params)}" if params else url

    def _require_token(self) -> str:
        if not self.token:
            raise VSSAPIError(
                "No bearer token available. Set VSS_TOKEN or provide "
                "VSS_USERNAME and VSS_PASSWORD."
            )
        return self.token

    @staticmethod
    def _friendly_error(error: Exception) -> VSSAPIError:
        if isinstance(error, HTTPError):
            detail = ""
            try:
                payload = json.loads(error.read())
                detail = payload.get("detail", "") if isinstance(payload, dict) else ""
            except (json.JSONDecodeError, OSError):
                pass
            suffix = f": {detail}" if detail else ""
            return VSSAPIError(f"VSS API returned HTTP {error.code}{suffix}")
        return VSSAPIError(f"Could not reach VSS API: {error}")


def authenticated_client() -> VSSClient:
    client = VSSClient(
        api_url=os.getenv("VSS_API_URL", DEFAULT_API_URL),
        token=os.getenv("VSS_TOKEN"),
    )
    if not client.token:
        username = os.getenv("VSS_USERNAME")
        password = os.getenv("VSS_PASSWORD")
        if not username or not password:
            client._require_token()
        client.login(username, password)
    return client


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    explore = commands.add_parser("list", help="List indexed videos")
    explore.add_argument("--scope", default="all")
    explore.add_argument("--limit", type=int, default=48)
    explore.add_argument("--offset", type=int, default=0)
    explore.add_argument("--date")
    explore.add_argument("--location")

    search = commands.add_parser("search", help="Search indexed video clips")
    search.add_argument("query")
    search.add_argument("--top-k", type=int, default=12)

    for name in ("metadata", "detections", "playback-url"):
        command = commands.add_parser(name)
        command.add_argument("source")
    commands.choices["playback-url"].add_argument("--expires-in", type=int, default=3600)

    download = commands.add_parser("download", help="Download a video")
    download.add_argument("source")
    download.add_argument("destination", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        client = authenticated_client()
        if args.command == "list":
            result = client.explore(
                scope=args.scope,
                limit=args.limit,
                offset=args.offset,
                date=args.date,
                location=args.location,
            )
        elif args.command == "search":
            result = client.search(args.query, top_k=args.top_k)
        elif args.command == "metadata":
            result = client.metadata(args.source)
        elif args.command == "detections":
            result = client.detections(args.source)
        elif args.command == "playback-url":
            result = client.playback_url(args.source, expires_in=args.expires_in)
        else:
            path = client.download(args.source, args.destination)
            print(path)
            return 0
        print(json.dumps(result, indent=2))
        return 0
    except VSSAPIError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

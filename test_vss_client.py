import io
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from vss_client import VSSAPIError, VSSClient


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = io.BytesIO(body)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self, size: int = -1) -> bytes:
        return self.body.read(size)


class RecordingOpener:
    def __init__(self, response: bytes) -> None:
        self.response = response
        self.requests = []

    def __call__(self, request, **kwargs):
        self.requests.append((request, kwargs))
        return FakeResponse(self.response)


class VSSClientTests(unittest.TestCase):
    def test_login_sets_token_without_authorization_header(self):
        opener = RecordingOpener(
            json.dumps({"access_token": "secret", "username": "user"}).encode()
        )
        client = VSSClient("https://example.test/api/v1", opener=opener)

        token = client.login("user", "password")

        request, _ = opener.requests[0]
        self.assertEqual(token, "secret")
        self.assertEqual(client.token, "secret")
        self.assertIsNone(request.get_header("Authorization"))
        self.assertEqual(
            json.loads(request.data),
            {"username": "user", "password": "password"},
        )

    def test_explore_sends_bearer_token_and_filters(self):
        opener = RecordingOpener(b'{"videos":[]}')
        client = VSSClient(
            "https://example.test/api/v1",
            token="secret",
            opener=opener,
        )

        result = client.explore(
            scope="mine",
            limit=10,
            offset=20,
            date="2026-10-09",
            location="lobby",
        )

        request, _ = opener.requests[0]
        query = parse_qs(urlparse(request.full_url).query)
        self.assertEqual(result, {"videos": []})
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")
        self.assertEqual(query["scope"], ["mine"])
        self.assertEqual(query["limit"], ["10"])
        self.assertEqual(query["offset"], ["20"])
        self.assertEqual(query["date"], ["2026-10-09"])
        self.assertEqual(query["location"], ["lobby"])

    def test_download_writes_stream_atomically(self):
        opener = RecordingOpener(b"video bytes")
        client = VSSClient(
            "https://example.test/api/v1",
            token="secret",
            opener=opener,
        )
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "result.mp4"

            result = client.download("folder/source.mp4", destination)

            request, _ = opener.requests[0]
            query = parse_qs(urlparse(request.full_url).query)
            self.assertEqual(result, destination)
            self.assertEqual(destination.read_bytes(), b"video bytes")
            self.assertEqual(query["source"], ["folder/source.mp4"])
            self.assertEqual(query["token"], ["secret"])

    def test_protected_request_requires_token(self):
        client = VSSClient("https://example.test/api/v1")

        with self.assertRaisesRegex(VSSAPIError, "No bearer token"):
            client.explore()


if __name__ == "__main__":
    unittest.main()

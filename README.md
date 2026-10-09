# closecall

## VSS video pipeline client

`vss_client.py` provides a dependency-free command-line client for the VAST
Video Search & Summarization API. Credentials are read only from environment
variables and are never written to the repository.

Set either an existing bearer token:

```bash
export VSS_TOKEN="..."
```

or credentials that the client can exchange for an in-memory token:

```bash
export VSS_USERNAME="..."
export VSS_PASSWORD="..."
```

Common pipeline operations:

```bash
# List videos available to the authenticated account
python3 vss_client.py list --scope all

# Search indexed clips
python3 vss_client.py search "person entering the lobby"

# Inspect one source returned by list/search
python3 vss_client.py metadata "SOURCE"
python3 vss_client.py detections "SOURCE"

# Request a temporary playback URL or download the source
python3 vss_client.py playback-url "SOURCE"
python3 vss_client.py download "SOURCE" ./video.mp4
```

Override `VSS_API_URL` only when targeting another VSS deployment. The default
is `https://team-15-vss.thecosmoslabs.com/api/v1`.

Run the unit tests with:

```bash
python3 -m unittest -v
```
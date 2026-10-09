# CloseCall

A one-day video agent that finds close calls in first-person bicycle footage and draws a green corridor with red highlights. The browser page includes a glasses-style crop. It is a demo of retrieved riding events, not a navigation or safety system.

The build uses the [VAST Builders Challenge](https://github.com/vast-data/vast-builders-challenge#vast-builders-challenge-video-agents) stack that is already running: search, Cosmos Reason captions, YOLO boxes, and a Weights & Biases LLM. It does not train a trajectory model.

**Design:** [DESIGN.md](DESIGN.md)

## Demo path

1. Search the whole team index, with no camera filter, for a bicycle rider’s point of view. Keep a clip only when the view is from the rider.
2. Re-ingest that clip only if the caption never mentions closeness or which side the object is on. Use scenario `egocentric`.
3. Ask the LLM once per clip for a small JSON event: summary, corridor label, and avoid boxes that YOLO already returned.
4. Play the clip with a narrower green trapezoid and red boxes on those objects. Glasses mode crops the same frame.
5. Deploy the page to the team Ingress at `/app`.

The listed packs are car dashcams, highway cameras, and fixed street cameras. Do not relabel those as a bicycle. NYC bicycle travel is the product story. The demo uses a licensed rider-view clip from the index, named as the city it actually comes from.

## What is implemented

```text
Browser
  ├─ POST /api/search ─────── VSS hybrid search
  ├─ GET  /api/video ──────── authenticated clip stream
  ├─ GET  /api/detections ─── stored YOLO sidecar
  └─ POST /api/event ──────── caption + YOLO evidence
                                  │
                                  └─ green corridor + supported red box
```

The Python server keeps the VSS password and bearer token out of the browser. Event generation is deliberately conservative: an object gets a red box only when its class appears in both the caption and stored detections, and the caption contains a proximity term. The green corridor is a HUD label, not measured geometry.

## Run a local UI check

Python 3.11 or newer is sufficient; there are no third-party dependencies.

```bash
python3 main.py
```

Open `http://localhost:8080`. The page and `/health` work without credentials. Live search requires:

```bash
export VSS_URL="https://team-15-vss.thecosmoslabs.com"
export VSS_USERNAME="team-15"
export VSS_PASSWORD="..."
python3 main.py
```

Never commit those values. On the workshop VM they are read from `/config/*.config` by the deployment script.

## Test

```bash
python3 -m unittest -v
node --check public/app.js
```

## Deploy on the workshop VM

Copy or clone this repository onto the authenticated workshop VM, then run:

```bash
chmod +x deploy.sh
./deploy.sh
```

The script:

1. Reads the one team config in `/config`.
2. Creates a ConfigMap for this small application.
3. injects VSS credentials through a Kubernetes Secret.
4. Deploys the app in the current team namespace.
5. exposes only `/app` on the existing team host.
6. waits for the rollout.

After it succeeds, open [workshop.thecosmoslabs.com](https://workshop.thecosmoslabs.com) and click **App**.

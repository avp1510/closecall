# CloseCall — MVP design

A one-day video agent for the [VAST Builders Challenge](https://github.com/vast-data/vast-builders-challenge#vast-builders-challenge-video-agents). CloseCall finds close calls in first-person bicycle footage and draws them as a green corridor with red highlights, in a browser view that stands in for smart glasses.

The longer research plan (camera poses, depth, road segmentation, a trained waypoint model) stays in [After the hackathon](#after-the-hackathon). It is not the build for today.

## Product

The camera is on a person riding a bicycle. Show the path ahead of the rider, and mark whatever comes close to them.

- **Green** is a corridor over the street ahead of the rider: a visualization of the open path in the clip, not a claim that the path is safe or legal.
- **Red** is only an object the clip and the detector both support as close to the rider: a car, truck, motorcycle, pedestrian, or another bicycle. A parked car is not red unless the caption says it is close or a door is opening. Empty road, sidewalk, and “everything outside the green shape” stay unmarked. Handlebars in the foreground are the camera, not an obstacle.
- The demo plays in a browser. A glasses mode crops the same frame to a visor band with one caption line. Meta glasses, or any wearable SDK, wait until a device and display API are confirmed.

This is a hackathon demo of retrieved riding events. It is not a navigation system and not a collision-avoidance system.

## What ships today

The builders stack is already running. Cosmos Reason, YOLO11, and Cosmos Embed index video. Search, clip playback, and an LLM for app logic are available. Training a trajectory model, running visual odometry, and uploading new internet video do not fit the day, and new internet video is out of bounds for this event.

| Keep | Drop for the MVP |
| --- | --- |
| Search the indexed archive for a bicycle point of view | Collecting and labeling new NYC bike videos |
| Re-ingest a few clips so captions mention closeness and side | DPVO, Depth Anything, SegFormer, DINOv2 training |
| YOLO boxes already stored on each segment | Per-frame live detection as a requirement |
| One LLM call per clip that emits a small JSON event | A learned waypoint head |
| A fixed green trapezoid, shifted by that JSON | Projecting future camera poses into the frame |
| Red boxes copied from detections the agent named | Painting the rest of the frame red |
| Browser page plus a glasses crop, deployed at `/app` | Wearable hardware |

## Demo corpus

Use footage that is already indexed. Do not ingest video from the internet.

The published packs do not list a bike-mounted camera. They list a car windshield (`pie_cam-3`), fixed street cameras, highway cameras, and indoor cameras. A fixed camera watching a cyclist from the sidewalk is the wrong point of view. A car dashcam is also the wrong point of view. Do not relabel either as a bicycle.

First search the whole index with no `camera_id` filter. Keep a hit only when the caption or the frames show the rider’s own view: handlebars, a helmet-mounted or chest-mounted camera, the street moving under the front wheel.

| Result of that search | What to do |
| --- | --- |
| A clip is actually from the rider | That clip is the demo. Note its real `camera_id`. |
| Nothing is from the rider | Stop. Tell the team the archive has no bicycle point of view. Do not switch the demo to `pie_cam-3` and call it a bike. |

NYC bicycle travel is the product story. The demo uses whichever licensed clip in the team index is actually a rider’s view. Say the city the clip is from. Do not relabel it as New York.

## Inputs and outputs

**Build input:** segments already in the team index. Optional re-ingest of those same segments with a rider close-call prompt.

**Query input:** a short natural-language search. Add `camera_id` only after the first hit names one.

**Agent output:** one JSON event per selected clip.

**Screen output:** the clip, a green corridor, red boxes on named objects, and a one-line caption. Glasses mode shows the same overlay in a visor crop.

## Architecture

```text
Indexed segments, no camera filter yet
        |
        v
Search for a bicycle rider's point of view
retrieval/search, retrieval/videos
        |
        +--> a real rider-view clip exists --> keep it
        |
        +--> no rider-view clip --> stop and say so
        |
        v
Captions already mention what is close, and on which side?
        |
        +--> yes --> use them
        |
        +--> no --> re-ingest that clip only
                    scenario: egocentric
                    Cosmos Reason + YOLO11 + Cosmos Embed
        |
        v
Close-call agent (Weights & Biases LLM)
captions + stored YOLO boxes --> one JSON event
        |
        v
Browser player
green trapezoid + red boxes + caption
        |
        v
Glasses crop of the same frame
deployed at Ingress /app
```

The DataEngine graph stays as deployed. Do not rebuild the segmenter, detector, reasoner, or embedder.

## Stack

| Piece | Use |
| --- | --- |
| VastDB index + `retrieval/search` | Rank segments for a rider-view close call |
| `retrieval/agent-qa` | Optional “what happened in this clip?” check while building |
| `retrieval/videos` | Clip URL, timestamps, captions, stored detections |
| `ingest/reingest-chunk` | Rewrite captions for a handful of segments |
| Cosmos Reason | Writes the caption the search will match |
| YOLO11 | Object class, count, and boxes already on the segment |
| Cosmos Embed | Vectors behind search; the app does not call it directly |
| Weights & Biases LLM | Turns one clip’s caption and boxes into the JSON event |
| `deployment/deploy-app-no-registry` | Ships the page to the team Ingress at `/app` |

Credentials and URLs are already in the VM environment (`/config/.config`). The app reads `INGRESS_URL` and the `WANDB_` variables. It does not embed secrets.

## Close-call prompt

Search the existing index first. Re-ingest only when a real rider-view close call comes back with a caption that never mentions distance or side. One person re-ingests, and only a few segments. Re-ingest takes minutes per batch.

Scenario preset: `egocentric`.

Prompt to store on those segments:

> This is a first-person view from someone riding a bicycle. Describe the street ahead. Say whether the path in front of the rider looks open. Name every car, truck, motorcycle, pedestrian, or other bicycle that is close to the rider, which side it is on, and whether it is entering the rider’s path. Mention opening doors, passing vehicles, braking, and crossings. Describe only what is visible. Do not call a region safe or legal.

Queries to try before and after re-ingest:

- first person view from a bicycle, handlebars visible, riding along a street
- car passing close to a bicycle rider
- pedestrian stepping toward a cyclist
- vehicle door opening near a bicycle

Do not filter on `pie_cam-3` for these queries. Confirm any filter with `retrieval/list-metadata` before treating an empty result as “no bicycle footage.”

## Event schema

The LLM runs once per chosen clip, not per frame. Input is the segment caption, timestamps, and the stored detection list. Output is JSON only:

```json
{
  "clip_id": "bike_segment_04",
  "camera_id": "from-the-hit",
  "start_s": 4.0,
  "end_s": 9.0,
  "summary": "A car on the left passes close as the rider approaches the intersection.",
  "corridor": "shift_right",
  "avoid": [
    {
      "label": "car",
      "side": "left",
      "reason": "Caption places a passing car close on the rider's left."
    }
  ],
  "confidence": "medium"
}
```

`corridor` is one of `center`, `shift_left`, `shift_right`, `slow`. `avoid[].label` must be a class YOLO actually returned on that segment (`person`, `bicycle`, `car`, `truck`, `bus`, `motorcycle`). If the caption and the boxes disagree, drop the avoid entry and lower confidence. The model must not invent a box. Do not put the rider’s own bicycle in `avoid` just because a bicycle box exists.

## Overlay rules

Draw on the paused or playing frame. No geometry pipeline.

**Green.** A trapezoid in the lower middle of the frame, wide at the bottom edge and narrow toward the horizon (about 45% of the frame height). Keep it narrower than a car-lane drawing: this is a bicycle path, not a full lane. `shift_left` and `shift_right` move it by roughly 12% of the frame width. `slow` keeps it centered and draws it shorter. The trapezoid is a HUD hint from the agent’s label, not a measured rideable region.

**Red.** For each `avoid` entry, draw the stored YOLO box of that class whose bottom sits in the lower 60% of the frame (closer to a forward-facing camera). If several boxes match, take the largest. If none match, show the caption and no red box.

**Do not** tint the sidewalk, the sky, or the area outside the trapezoid. Unmarked means “not called out,” not “safe.”

**Caption.** The `summary` string, one or two lines, under the frame.

**Glasses mode.** Same frame and overlay, cropped to a wide band, larger type, no search chrome. A toggle, not a second model.

## App

One page.

1. A search box with the four queries above as chips. No default camera filter until a rider-view hit names one.
2. A result list: thumbnail, time range, score, caption, `camera_id`.
3. A player for the selected segment. The overlay appears for `[start_s, end_s]` from the event. Outside that window the frame is clean.
4. The JSON summary, corridor label, and confidence, visible so a judge can see the agent’s evidence.
5. Glasses toggle.

The page calls the team search and video APIs. The structuring call goes to the Weights & Biases inference endpoint with the team `WANDB_` settings. Cache the JSON on the segment id so scrubbing the timeline does not re-call the LLM.

Deploy with `deploy-app-no-registry` to Ingress path `/app`. After deploy, open the App tab on the workshop host.

## Build order

Do these in order. Stop when the current step is visible on a real clip.

| Order | Step | Done when |
| --- | --- | --- |
| 1 | Search the whole index for a bicycle rider’s point of view | A clip plays and the view is from the rider, or you have confirmed that no such clip is indexed |
| 2 | Read stored detections on that clip | A car, person, or other bicycle box exists, and it is not just the rider |
| 3 | Re-ingest that clip only if the caption omits closeness and side | A new caption names a side and an object. Scenario `egocentric` |
| 4 | LLM emits the JSON event for that clip | `corridor` and `avoid` match the caption and a real box |
| 5 | Draw the trapezoid and at most those red boxes | A judge can see green, red, and the caption on one frame |
| 6 | Glasses toggle and `/app` deploy | The same clip plays on the deployed page |

If step 1 is empty, check login, dashboard health, and `list-metadata` before re-ingesting. Re-ingest cannot create a bicycle point of view that was never recorded. If step 2 has no boxes, pick another rider-view segment.

## Definition of done

- A search returns a real indexed clip from a bicycle rider’s point of view.
- The page plays that clip with a green corridor and, when the agent named one, a red box on a detected object.
- The caption states what the model saw. It does not say the path is safe.
- Glasses mode is the same overlay, cropped.
- The page is reachable at the team `/app` path.
- The spoken demo distinguishes retrieved events from riding advice.

## Risks

- **The archive may not contain a rider’s point of view.** The listed packs are car, highway, and fixed cameras. An empty search is a data fact, not a broken query.
- **Retrieved behavior is not a safety rating.** Clips show what happened in front of a camera, including close passes.
- **Captions only contain what the prompt asked.** A miss on a real rider-view clip means re-ingest, not a new download.
- **Boxes are segment-level.** The red rectangle may not sit on the exact frame of the closest approach. Show the time range honestly.
- **The green shape is a HUD, not a measured lane.** Scale, camera mount, and the true path are unknown.
- **Intersections have more than one reasonable path.** `corridor` is a single label for the demo, not a route planner.
- **Re-ingest is shared.** A few segments only, one person kicking it off.

## After the hackathon

The original research goal still stands, and it is a different system: learn a traversable corridor from first-person bicycle video without hand-drawn paths, then test it on video the model has not seen.

That path needs, in order:

1. Rights-cleared first-person bicycle rides. Stay on bicycles. Do not mix in car video.
2. Frame extraction with timestamps (FFmpeg, OpenCV).
3. Monocular ego-motion (DPVO) and a stated scale assumption. Camera height on the rider is a scale anchor. Monocular poses alone are not metric.
4. Depth (Depth Anything V2) and road segmentation (SegFormer), checked on the target city because bike lanes, intersections, and lighting break pretrained road classes.
5. Automatic labels: project future camera positions into the current frame, expand a corridor by an assumed bicycle width, and clip it to the road or bike-lane mask. A camera path is not a safe or legal riding line.
6. A frozen visual encoder (DINOv2) and a small waypoint head, trained and tested split by route, not by adjacent frames.
7. Only then, a glasses runtime, after the device SDK can show a camera-aligned overlay.

CloseCall’s event JSON is the seam. A later waypoint model can replace `corridor: shift_right` with projected points. The page, the red-box rule, and the “unmarked is not safe” copy stay.

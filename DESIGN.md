# CloseCall — MVP design

A one-day video agent for the [VAST Builders Challenge](https://github.com/vast-data/vast-builders-challenge#vast-builders-challenge-video-agents). CloseCall finds near-miss moments in already indexed driving and street footage and draws them as a green corridor with red highlights, in a browser view that stands in for smart glasses.

The longer research plan (camera poses, depth, road segmentation, a trained waypoint model) stays in [After the hackathon](#after-the-hackathon). It is not the build for today.

## Product

Given dashcam and street video, show where the camera vehicle kept traveling, and mark people, cyclists, and vehicles that came close.

- **Green** is a corridor over the road ahead: a visualization of the open path in the clip, not a claim that the path is safe or legal.
- **Red** is only an object the clip and the detector both support: a person, bicycle, or vehicle described as close to the camera vehicle. Empty road, sidewalk, and “everything outside the green shape” stay unmarked.
- The demo plays in a browser. A glasses mode crops the same frame to a visor band with one caption line. Meta glasses, or any wearable SDK, wait until a device and display API are confirmed.

This is a hackathon demo of retrieved driving events. It is not a navigation system and not a collision-avoidance system.

## What ships today

The builders stack is already running. Cosmos Reason, YOLO11, and Cosmos Embed index video. Search, clip playback, and an LLM for app logic are available. Training a trajectory model, running visual odometry, and uploading new internet video do not fit the day, and new internet video is out of bounds for this event.

| Keep | Drop for the MVP |
| --- | --- |
| Search the indexed archive for close calls | Collecting and labeling new NYC videos |
| Re-ingest a few clips so captions mention closeness and side | DPVO, Depth Anything, SegFormer, DINOv2 training |
| YOLO boxes already stored on each segment | Per-frame live detection as a requirement |
| One LLM call per clip that emits a small JSON event | A learned waypoint head |
| A fixed green trapezoid, shifted by that JSON | Projecting future camera poses into the frame |
| Red boxes copied from detections the agent named | Painting the rest of the frame red |
| Browser page plus a glasses crop, deployed at `/app` | Wearable hardware |

## Demo corpus

Use footage that is already indexed. Do not ingest video from the internet.

| Pack | `camera_id` | Why it is in the demo |
| --- | --- | --- |
| Live driving (PIE, Toronto) | `pie_cam-3` | Forward-facing drives. This is the first-person stand-in. |
| SF streets, once indexed | `sf_streets_cam-1` … `sf_streets_cam-4` | Urban intersections from fixed cameras. |
| Neighborhood streets | `neighborhood_cam-1` | Cars passing and stopping at a curb. |
| Highway (I-24), optional | `i24_cam-1` | Vehicle-to-vehicle closes, not pedestrians. |

NYC first-person driving is the product story. The demo uses Toronto dashcam and city street cameras because those are the licensed clips in the archive. Say that on the page. Do not relabel Toronto or San Francisco as New York.

Start with two or three PIE segments. Add a street camera only after the first clips play with an overlay.

## Inputs and outputs

**Build input:** segments already in the team index. Optional re-ingest of those same segments with a close-call prompt.

**Query input:** a short natural-language search, plus filters (`camera_id`, `location`).

**Agent output:** one JSON event per selected clip.

**Screen output:** the clip, a green corridor, red boxes on named objects, and a one-line caption. Glasses mode shows the same overlay in a visor crop.

## Architecture

```text
Indexed driving and street segments
(PIE, neighborhood, SF streets, optional I-24)
        |
        v
Search what is already written
retrieval/search, retrieval/videos
        |
        +--> captions already mention a close call --> use them
        |
        +--> captions never say closeness or side
                 |
                 v
             Re-ingest a few segments only
             Cosmos Reason + YOLO11 + Cosmos Embed
             (reingest-chunk, not the whole archive)
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
| VastDB index + `retrieval/search` | Rank segments for a close-call query |
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

Search the existing index first. Re-ingest only when a real close call comes back with a caption that never mentions distance or side. One person re-ingests, and only a few segments. Re-ingest takes minutes per batch.

Scenario preset: `live_driving` for PIE, `traffic` for I-24, `surveillance` for street cameras.

Prompt to store on those segments:

> Describe the road from this camera. Say whether the lane or street ahead looks open. Name every pedestrian, cyclist, or vehicle that is close to the camera vehicle or to the curb, which side they are on, and whether they are entering the roadway. Mention braking, turning, and crossings. Describe only what is visible. Do not call a region safe or legal.

Queries to try before and after re-ingest:

- pedestrian stepping toward the road while a vehicle is moving
- cyclist close to the car
- vehicle ahead braking
- person close to a moving vehicle

Filter PIE with `camera_id=pie_cam-3`. Confirm filter values with `retrieval/list-metadata` before treating an empty result as “no close calls.”

## Event schema

The LLM runs once per chosen clip, not per frame. Input is the segment caption, timestamps, and the stored detection list. Output is JSON only:

```json
{
  "clip_id": "set03_segment_12",
  "camera_id": "pie_cam-3",
  "start_s": 4.0,
  "end_s": 9.0,
  "summary": "A person on the left steps toward the lane as the car approaches the crosswalk.",
  "corridor": "shift_right",
  "avoid": [
    {
      "label": "person",
      "side": "left",
      "reason": "Caption places a pedestrian entering from the left."
    }
  ],
  "confidence": "medium"
}
```

`corridor` is one of `center`, `shift_left`, `shift_right`, `slow`. `avoid[].label` must be a class YOLO actually returned on that segment (`person`, `bicycle`, `car`, `truck`, `bus`, `motorcycle`). If the caption and the boxes disagree, drop the avoid entry and lower confidence. The model must not invent a box.

## Overlay rules

Draw on the paused or playing frame. No geometry pipeline.

**Green.** A trapezoid in the lower middle of the frame, wide at the bottom edge and narrow toward the horizon (about 45% of the frame height). `shift_left` and `shift_right` move it by roughly 12% of the frame width. `slow` keeps it centered and draws it shorter. The trapezoid is a HUD hint from the agent’s label, not a measured drivable region.

**Red.** For each `avoid` entry, draw the stored YOLO box of that class whose bottom sits in the lower 60% of the frame (closer to a forward-facing camera). If several boxes match, take the largest. If none match, show the caption and no red box.

**Do not** tint the sidewalk, the sky, or the area outside the trapezoid. Unmarked means “not called out,” not “safe.”

**Caption.** The `summary` string, one or two lines, under the frame.

**Glasses mode.** Same frame and overlay, cropped to a wide band, larger type, no search chrome. A toggle, not a second model.

## App

One page.

1. A search box with the four queries above as chips, and a camera filter defaulting to `pie_cam-3`.
2. A result list: thumbnail, time range, score, caption.
3. A player for the selected segment. The overlay appears for `[start_s, end_s]` from the event. Outside that window the frame is clean.
4. The JSON summary, corridor label, and confidence, visible so a judge can see the agent’s evidence.
5. Glasses toggle.

The page calls the team search and video APIs. The structuring call goes to the Weights & Biases inference endpoint with the team `WANDB_` settings. Cache the JSON on the segment id so scrubbing the timeline does not re-call the LLM.

Deploy with `deploy-app-no-registry` to Ingress path `/app`. After deploy, open the App tab on the workshop host.

## Build order

Do these in order. Stop when the current step is visible on a real clip.

| Order | Step | Done when |
| --- | --- | --- |
| 1 | Search the index for the four queries on `pie_cam-3` | At least one clip plays and the caption is about a road scene |
| 2 | Read stored detections on that clip | Person, bicycle, or vehicle boxes exist, or you have picked a different clip that has them |
| 3 | Re-ingest that clip only if the caption omits closeness and side | A new caption names a side and an object |
| 4 | LLM emits the JSON event for that clip | `corridor` and `avoid` match the caption and a real box |
| 5 | Draw the trapezoid and at most those red boxes | A judge can see green, red, and the caption on one frame |
| 6 | Glasses toggle and `/app` deploy | The same clip plays on the deployed page |

If step 1 is empty, check login, dashboard health, and `list-metadata` before re-ingesting. If step 2 has no boxes, pick another segment. Do not spend the day on highway footage when the story is a person near a car.

## Definition of done

- A search returns a real indexed driving or street clip.
- The page plays that clip with a green corridor and, when the agent named one, a red box on a detected object.
- The caption states what the model saw. It does not say the path is safe.
- Glasses mode is the same overlay, cropped.
- The page is reachable at the team `/app` path.
- The spoken demo distinguishes retrieved events from driving advice.

## Risks

- **Retrieved behavior is not a safety rating.** Clips show what happened in front of a camera, including bad driving.
- **Captions only contain what the prompt asked.** A miss often means re-ingest, not a broken search.
- **Boxes are segment-level.** The red rectangle may not sit on the exact frame of the closest approach. Show the time range honestly.
- **The green shape is a HUD, not a measured lane.** Scale, camera mount, and the true vehicle path are unknown.
- **Intersections have more than one reasonable path.** `corridor` is a single label for the demo, not a route planner.
- **SF street cameras may still be ingesting.** Demo PIE first.
- **Re-ingest is shared.** A few segments only, one person kicking it off.

## After the hackathon

The original research goal still stands, and it is a different system: learn a traversable corridor from first-person driving video without hand-drawn paths, then test it on video the model has not seen.

That path needs, in order:

1. Rights-cleared first-person drives, one travel mode at a time.
2. Frame extraction with timestamps (FFmpeg, OpenCV).
3. Monocular ego-motion (DPVO) and a stated scale assumption. Camera height is a scale anchor. Monocular poses alone are not metric.
4. Depth (Depth Anything V2) and road segmentation (SegFormer), checked on the target city because bikes, intersections, and lighting break pretrained road classes.
5. Automatic labels: project future camera positions into the current frame, expand a corridor by an assumed width, and clip it to the road mask. A camera path is not the vehicle footprint, and driving through a pixel does not make it safe or legal.
6. A frozen visual encoder (DINOv2) and a small waypoint head, trained and tested split by route, not by adjacent frames.
7. Only then, a glasses runtime, after the device SDK can show a camera-aligned overlay.

CloseCall’s event JSON is the seam. A later waypoint model can replace `corridor: shift_right` with projected points. The page, the red-box rule, and the “unmarked is not safe” copy stay.

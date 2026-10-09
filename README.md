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

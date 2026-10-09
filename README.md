# CloseCall

A one-day video agent that finds near-miss moments in indexed driving and street footage and draws a green corridor with red highlights. The browser page includes a glasses-style crop. It is a demo of retrieved events, not a driving or safety system.

The build uses the [VAST Builders Challenge](https://github.com/vast-data/vast-builders-challenge#vast-builders-challenge-video-agents) stack that is already running: search, Cosmos Reason captions, YOLO boxes, and a Weights & Biases LLM. It does not train a trajectory model.

**Design:** [DESIGN.md](DESIGN.md)

## Demo path

1. Search the team index for a close call on `pie_cam-3` (forward-facing drives). Street cameras are optional after that works.
2. Re-ingest a few segments only if the captions never mention closeness or which side the object is on.
3. Ask the LLM once per clip for a small JSON event: summary, corridor label, and avoid boxes that YOLO already returned.
4. Play the clip with a green trapezoid and red boxes on those objects. Glasses mode crops the same frame.
5. Deploy the page to the team Ingress at `/app`.

NYC first-person driving is the product story. The hackathon demo uses the licensed archive (Toronto dashcam, neighborhood and San Francisco street cameras), not newly downloaded video.

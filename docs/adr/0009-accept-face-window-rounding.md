# Accept the face engine's window rounding

InfiniteTalk renders whole 81-frame windows, stepping 72 frames, so each Face section renders up to one window more than its frames need. On the 5 s test clips this is 22% extra; on `script-01`'s real Face sections (555 and 265 frames) it is 30 and 32 frames, about 7% of the rendered total, or roughly one extra window (about 2 minutes) per Video.

The decision is to accept this waste. Three alternatives were weighed:
- Move the card cuts so each Face section fits whole windows. Rejected: it moves the phrase-triggered cuts that ADR 0007 fixes, for a saving of about 2 minutes.
- Change the window length or the overlap. Rejected: that changes the model's output quality, and it needs a full review before it is considered.
- Merge or drop Face sections. Rejected: it changes the approved layout, with the front and back Face sections (ADR 0008).

Recorded by the agent on the Operator's instruction to decide the best answers (option 1 of the exploration in the session). Open to supersession if a Script with many short Face sections makes the waste matter.

Consequences: the 22% applies to the short test clips only.

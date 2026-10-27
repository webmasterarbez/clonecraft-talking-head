# Face section targets in seconds, checked against the Voiceover

ADR 0007 triggers every card and Face section by a spoken phrase, so a remade Voiceover still lines up. That leaves the length of the front and back Face sections to whoever writes the Slides list, and nothing checks the lengths against the real timings. The Operator wants the Script to decide them from its content.

The decision is to give the Script two targets in seconds, `face_front_s` for the opening Face section and `face_back_s` for the closing one, in the front matter. The drafter sets them from the content: the opening covers the hook and the first claim, and the closing covers the call to action. The Video then checks each Face section against its target using the Voiceover's word timings. A section that misses by more than 1.5 s produces a warning that names the nearest sentence start, and the Operator moves the phrase in a revised proposal (ADR 0008).

The targets never trigger a cut. The cuts stay phrases in the Slides list, so ADR 0007's reason still holds.

Alternatives weighed:
- Cut on the longest pause nearest the target. Rejected: pauses do not always fall between sentences, so a card can land mid-thought.
- Let the Video move the cut itself to the nearest sentence start. Rejected: it would change the Slides list without the Operator's approval (ADR 0008).
- Refuse a Video whose section misses its target. Rejected: a warning matches how the Video already reports other checks, such as a card that is too long to read.

Decisions the agent took under the Operator's instruction to decide the best answers: the targets go in the front matter, so the Script carries them; the proposal estimates the lengths from the word count, and the Video checks the real ones after the Voiceover; the tolerance is 1.5 s, and a miss is a warning. Open to supersession.

Consequences: `FRONT_KEYS` in `script.py` gains `face_front_s` and `face_back_s`. The check lives in `face_targets.py`. The operator guide's front-matter list names both keys.

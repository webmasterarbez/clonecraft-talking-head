# A Script's wording may change, with the Operator's approval

CloneCraft used to treat a Script as final: it never changed its words, and writing Scripts was outside its scope. The Operator now wants to give it a plain-text draft with no Delivery Cues and no Slide cards, and get back a Script with speech-friendly wording, Delivery Cues, a Slides list and Face sections placed at the front and back, ready for a Voiceover.

The Script's wording may now change, but only in a proposal the Operator approves once, as a whole, before anything is written. The proposal shows every wording change next to the original line, plus the Delivery Cues, the Slides list and the Face placement. Nothing is written to `scripts/<name>.md` until the Operator approves it. The plain-text draft is kept, unchanged, in a `drafts/` folder beside `scripts/`.

Drafting is done by a repo skill, not by the `clonecraft` command, so the code keeps its current job: parsing, placing and rendering. Its proposal follows the rules already in the codebase: front-matter keys, the `<!-- slides -->` marker, `kind: face` entries, and the 45 s warning for a Face section.

Alternatives weighed:
- Keep words fixed and only add formatting: rejected, because the Operator wants speech-friendly wording as well.
- Write the Script without approval: rejected, because a changed Script changes the Voiceover and the Video.
- Edit the Script in place: rejected, because the plain-text draft would be lost.

Consequences: `GLOSSARY.md` now allows wording changes with approval. Any approved change to a Script's words makes its current Voiceover out of date, so the Operator remakes it before a new Video.

## Decisions

Answered by the Operator:
- Wording may change, with approval, for speech (Q5a).
- Delivery Cues are added now (Q6a).
- Face at the front is about 15 s and at the back about 10 s, with cards between (Q7a).
- One approval of the whole proposal before anything is written (Q8a).
- Plain-text drafts go in `drafts/`, and the Script goes to `scripts/<name>.md` (Q9a).
- Round 1 stands: a repo skill, the drafter decides cards and Face sections, and "Slides list" is the glossary term (Q10a).

Taken by the agent under the Operator's "accept all", open to supersession:
- Q11c: an approved wording change marks the Voiceover out of date, and the Video is refused until the Voiceover is remade.
- Q12a: the proposal is a diff file in `drafts/` with the original and proposed line side by side, plus a short summary in chat.
- Q13a: the drafter makes only speech-friendly changes on its own (digits to words, abbreviations spelled out, symbols removed), each listed in the proposal. Any other wording change is a suggestion for the Operator.

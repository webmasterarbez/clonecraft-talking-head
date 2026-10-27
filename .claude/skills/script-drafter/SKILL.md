---
name: script-drafter
description: Use when turning a plain-text draft into a CloneCraft Script with Delivery Cues, a Slides list and Face sections, for the Operator to approve.
category: video-production
---

# Draft a Script from plain text for the Operator to approve (ADR 0008)

Read the plain-text draft, then write a proposal. Never write `scripts/<name>.md` yourself: the Operator approves the proposal, and only then is the Script written.

## Inputs and outputs

- Input: `platform/<platform>/channels/@<handle>/drafts/<name>.txt`, the Operator's text, unchanged. If the Script already exists and the Operator asks for a redraft, read `scripts/<name>.md` as the draft instead, and never edit it.
- Output: `platform/<platform>/channels/@<handle>/drafts/<name>.proposal.md`, holding the proposed Script at the top, then a diff of every wording change against the draft, then a short list of the decisions behind the Slides list and Face sections.
- After writing the proposal, give the Operator a short summary in chat and the path of the file. Do not paste the whole proposal in chat.

## Wording

- Make only speech-friendly changes on your own, and list each one in the diff: digits to words (`10` to `ten`), abbreviations spelled out, symbols removed.
- Any other change to the wording, such as a rewritten sentence or a fixed stammer, is a suggestion. Put it in a "Suggestions" section, leave the words as they are, and let the Operator decide.
- Never change the meaning, the claims, or the order of the words.

## Delivery Cues

- Add a cue in square brackets at the start of a paragraph when its delivery changes, such as `[warmly]`. A cue applies to its paragraph and the paragraph after, until the next cue.
- The Persona's Voice Reference may have a transcript, in which case cues change nothing when spoken (ADR 0004). Check `persona/<name>/voice-reference.txt` and say so in the proposal.

## Slides list

- Each card's `at:` phrase must be the exact opening words of the spoken line, in the same order as the Script, and must be in the Script's wording as it will read after the diff.
- Choose a `kind` from `title`, `bullet`, `stat`, `posting`, `checklist`, `cta` or `face`, and give a `stat` its `value`.
- Keep each card's text short enough to read in the time it holds: about 15 characters a second, plus 1.5 s.

## Face sections

- The Persona's face opens the Video and closes it. Aim for about 15 s at the front and about 10 s at the back (the Operator's decision, ADR 0008).
- The front Face section ends where the first card cuts in. Use `kind: face` at the phrase that brings the Persona back for the closing.
- Choose each Face section's length from the content: the opening Face section covers the hook and the first claim, and the closing covers the call to action (ADR 0010). Put it in seconds in `face_front_s` and `face_back_s`.
- Estimate the lengths in the proposal from the draft's word count (about 2.5 words a second). After the Voiceover exists, the Video reports the real lengths and names the nearest sentence start to each target; if a Face section misses by more than 1.5 s, the Operator moves its phrase in a revised proposal.
- Warn in the proposal if a Face section is over 45 s.

## Front matter

- Do not add `hook`, `hook_hold` or `face_ends_after`. The Operator sets those.
- Set `face_front_s` and `face_back_s` (seconds) to the length of the opening and closing Face sections, as decided under "Face sections" (ADR 0010). The Video checks them against the real Voiceover and warns when a Face section misses by more than 1.5 s.

## Flag-only pattern check

Check the wording against the patterns below and flag any hit in the "Suggestions" section, with its number. Flags never change the words. Each pattern is numbered as in the source, and patterns marked *weak alone* count only when several hit the same passage.

Adapted from the 26 patterns in [blader/humanizer](https://github.com/blader/humanizer) (MIT licence, Copyright blader). Its guide for written prose is aimed at readers, so apply it with the speech rules in mind: a short line is fine in a talking head, and a rhetorical turn is only a flag, not a fault.

- **1 Not X but Y:** "it's not X, it's Y".
- **2 One-line closers:** "That is the real win." and similar lines that restate the section.
- **3 Deep-sounding sayings:** "At its core, what matters is..."
- **4 Staged run-up:** "Here's the thing." "Honestly?" "Let's dive in."
- **5 Arguing with no one:** "I'm not saying X, but..."
- **6 Forced triads:** three items where the meaning needs two or four.
- **7 Repeated openings:** several sentences in a row starting the same way.
- **8 Dashes as the connector** (*weak alone*), and **9 stacked qualifiers** (*weak alone*).
- **10 Hyphenated pairs** (*weak alone*) and **11 passive voice with no subject** (*weak alone*).
- **12 Overused AI words:** "delve", "testament", "landscape", "showcasing".
- **13 Inflated significance:** "a pivotal moment", "the future looks bright".
- **14 Vague association:** "associated with", "in connection with".
- **15 Shallow -ing riders:** "symbolizing...", "reflecting...".
- **16 Sales language:** "breathtaking", "nestled within".
- **17 Borrowed authority:** "experts believe", "studies show" with no source named.
- **18 Avoiding is, are, has:** "serves as", "features", "boasts".
- **19 Bold or labels as decoration**, **20 decorative headings**, **21 curly quotes** (*weak alone*), **24 a heading repeated in the first sentence**: for scripts, flag only if they appear in the draft.
- **22 Chatbot residue:** "Great question!", "I hope this helps".
- **23 Disclaimers and guesses:** "it appears", "details are limited".
- **25 Writing about the document:** "This section covers...", "The table below...".
- **26 Re-explaining what the viewer knows:** a line that restates the one before it.

## Check before writing the proposal

- Every `at:` phrase appears in the proposed Script, in order.
- No card has an empty `text`, and every `cta` has a `button`.
- Every Face section is 45 s or less.
- The proposed Script contains no front matter keys other than the ones the Operator allows.
- Every pattern hit is listed under "Suggestions" with its number, and no hit has changed the words.

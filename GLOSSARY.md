# CloneCraft

CloneCraft turns a Script into a talking-head Video of a Persona, using the Persona's Likeness and Voice Clone. It can also draft and edit a Script from plain text, but only the Operator approves what it writes (ADR 0008). Publishing Videos is outside its scope.

## Language

### Where videos go

**Platform**:
A social media service where Videos are published, such as YouTube, TikTok or LinkedIn.
_Avoid_: Channel, network, site

**Channel**:
An outlet on one Platform, named by its handle (such as @examplechannel on YouTube), that owns a set of Scripts and is fronted by exactly one Persona. The same handle on another Platform is a different Channel.
_Avoid_: Account, brand, show

**Format**:
An aspect ratio, resolution and frame rate that a Channel's Videos are made in, such as vertical 9:16 at 1080×1920 and 30 fps. A Channel has one or more Formats.
_Avoid_: Size, layout, preset

### Who appears

**Persona**:
The person whose Likeness and voice appear in a Channel's Videos. One Persona can front several Channels.
_Avoid_: Avatar, character, talent, host

**Likeness**:
A still portrait of a Persona, in one orientation (vertical or horizontal), that is animated into the talking head. A Persona has at most one Likeness per orientation and needs the matching one for a Format. It is never edited; each Video uses a crop of it that fits the Format.
_Avoid_: Photo, headshot, avatar image

**Voice Sample**:
A long recording of the Persona's real voice, from which the Voice Reference is chosen.
_Avoid_: Reference audio, voice file

**Voice Reference**:
A short excerpt of the Persona's real voice that the Voice Clone copies. Usually the Operator picks it from three 20-second stretches of the Voice Sample that CloneCraft proposes. It may have a transcript beside it, the exact words spoken in it, and with one the clone copies the voice more closely (ADR 0004).
_Avoid_: Prompt audio, reference clip

**Voice Clone**:
A synthetic voice that speaks like the Voice Reference, reused for every Voiceover. A Persona with no Voice Sample can't have one, so it can't be used to make Videos yet.
_Avoid_: Voice model, TTS voice

### What gets made

**Script**:
The text a Persona speaks in one Video, with its Delivery Cues and Slides list. CloneCraft changes its words only in a change the Operator has approved (ADR 0008).
_Avoid_: Copy, transcript

**Plain-text draft**:
An unedited text the Operator gives CloneCraft to turn into a Script: no Delivery Cues, no Slides list. It is kept beside the Script it became, and never changed.
_Avoid_: Raw script, source, outline

**Slides list**:
The block after a Script's `<!-- slides -->` marker: its Slide cards, and any `kind: face` entries that bring the Persona back.
_Avoid_: Slide plan, card list, cues

**Delivery Cue**:
An instruction in square brackets inside a Script, such as `[warmly]`, for how a line should be spoken. It is never spoken itself, and it changes the delivery only when the Voice Reference has no transcript (ADR 0004). It applies until the end of its paragraph or the next Delivery Cue; text with no cue is spoken in a neutral delivery.
_Avoid_: Tag, direction, emotion marker

**Voiceover**:
The audio of the Voice Clone speaking a whole Script, which the Operator approves before a Video is made. Each Script has at most one current Voiceover, and remaking it replaces the old one.
_Avoid_: Narration, TTS output, audio track

**Speech Check**:
The automatic check of each take of a piece of a Voiceover: a transcriber hears it, and its words are compared with the Script's, to keep the take, try again, or stop (ADR 0005). It catches dropped and garbled words, not how the voice sounds; the Operator still listens.
_Avoid_: Voice check, QC, ASR check

**Video**:
An approved Voiceover played under the Script's Face sections and Slide cards. A Script with no Slide cards gives one continuous talking head; a Video can also be only Slide cards, with no face. The Script's hook, when it has one, shows over the opening Face section, and the Brand pack's badge over every Face section. The Brand pack's disclosure pill shows over its last Slide card, and its end card, when it has one, holds in silence after the Voiceover. Its audio is normalised to the approved look's loudness and fades out at its end, and the Voiceover itself is left as approved (ADR 0007). It has no b-roll or music. Each Script has at most one current Video per Format of its Channel, and remaking one replaces only that one.
_Avoid_: Render, clip, output

**Face section**:
A stretch of a Video in which the Persona's Likeness is seen speaking, such as an opening before the first Slide card or a closing after the last. A Video can have several Face sections, or none.
_Avoid_: Intro, talking-head part, hook

**Slide card**:
A full-screen card of short text, drawn in a Brand pack's look, that cuts in when a given phrase of the Script is spoken and stays until the next Slide card or Face section, while the Voiceover plays on.
_Avoid_: Slide, b-roll, overlay, title card

**Brand pack**:
A Persona's set of colours, fonts, mark and slide template that gives Slide cards their look. A Persona can have several.
_Avoid_: Theme, brand kit, style, template

**Badge**:
The Brand pack's mark and wordmark in a small chip at the bottom left of every Face section, never over a Slide card.
_Avoid_: Logo, watermark, bug, wordmark badge

**End card**:
The Brand pack's closing card (mark, wordmark, a line and a web address) held in silence for a few seconds after the Voiceover ends.
_Avoid_: Outro, end screen, closing slide

### Who runs it

**Operator**:
The one person who runs CloneCraft on their own machine and approves Voiceovers.
_Avoid_: User, admin, creator

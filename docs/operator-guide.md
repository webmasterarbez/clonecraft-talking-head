# Operator guide: making a Voiceover and a Video

This guide is for the Operator, the one person who runs CloneCraft. It assumes the machine is already set up; if it is not, start with [setup-and-maintenance.md](setup-and-maintenance.md). Capitalised terms are defined in [GLOSSARY.md](../GLOSSARY.md). The names below (`example`, `@examplechannel`) are made up; use your own.

Run every command from the repo root. CloneCraft finds its files relative to the folder you run it from.

## 1. Lay out your files

Everything personal lives in two git-ignored folders.

```
persona/
  example/                       one folder per Persona
    likeness.jpg                 the Likeness: one still portrait, for 9:16 (any image type ffmpeg reads)
    likeness-horizontal.jpg      optional: a landscape still of the same Persona, for 16:9
    voice-sample.mp3             the Voice Sample: a long recording of the real voice (any audio or video type)
    voice-reference.wav          the Voice Reference (made for you, or put there by you)
    voice-reference.txt          optional: the exact words spoken in the Voice Reference
    voice-reference-candidates/  the three proposals, written when CloneCraft offers a choice
    brand-packs/                 optional: the looks for Slide cards, one folder per Brand pack
      example-look/              pack.json, slide.html, fonts/ and a mark (start from config/brand-pack-starter)
platform/
  youtube/                       one folder per Platform
    channels/
      @examplechannel/           one folder per Channel
        channel.yaml             which Persona fronts it, and its Formats
        scripts/script-01.md     your Scripts
        voiceovers/script-01.wav made by `clonecraft voiceover`
        voiceovers/script-01.words.json  the Voiceover's word timings, made with it
        videos/script-01.1080x1920.mp4  made by `clonecraft video`, one per Format
        videos/face-sections/            each Video's rendered Face sections, kept for reuse
```

The same handle on another Platform is a different Channel, so it gets its own folder under that Platform.

### channel.yaml

```yaml
persona: example
formats:
  - aspect: "9:16"
    resolution: 1080x1920
    fps: 30
  - aspect: "16:9"
    resolution: 1920x1080
    fps: 30
```

- `persona` is the name of a folder in `persona/`. One Persona can front several Channels.
- `formats` is a list of the Formats the Channel publishes. A Channel with one Format needs nothing else; a Channel with several needs `--format` (see below).
- Each Format has at most one entry per aspect. Only `9:16` (vertical) and `16:9` (horizontal) are supported. Any other aspect stops the Video step with an error that names this file.
- `resolution` is `<width>x<height>` and `fps` is the frame rate of the finished Video.
- A `format:` block from an older version is refused with an error that tells you to change it to `formats:`.
- `brand_pack` (optional) names the Brand pack the Channel's Slide cards are drawn in, such as `brand_pack: example-look`. Leave it out when the Persona has only one Brand pack.

### The Likeness

Each Persona has up to two still portraits, one per orientation:

- `likeness.<extension>` is the vertical Likeness, used for 9:16 Videos.
- `likeness-horizontal.<extension>` is the horizontal Likeness, used for 16:9 Videos. A 16:9 Video needs it; CloneCraft will not make one from the vertical picture, because cropping that to 16:9 cuts off the head.

Each Video uses a centred crop of its Likeness that fits its Format. The file is never edited, so keep the face well inside the centre of the picture. If there are several files for one orientation, the first in alphabetical order is used.

## 2. Write a Script

A Script is a Markdown or plain-text file at `platform/<platform>/channels/@<handle>/scripts/<name>.md`. It is the text the Persona speaks, with its Delivery Cues and its slides list. CloneCraft changes its words only in a change you have approved (ADR 0008). Drafting a Script from plain text is not built yet.

```
Welcome back. Today is about one thing: how to ask for a raise.

[warmly] You deserve to be paid fairly. [firmly] Here is how you ask.
```

- **Pieces.** CloneCraft packs whole sentences into pieces of at most 18 words, and a blank line (a paragraph break) always ends a piece. A single sentence longer than 18 words stays whole. Each piece is spoken and checked on its own.
- **Delivery Cues.** A word in square brackets, such as `[warmly]`, says how a line should be spoken. It is never spoken itself. It applies until the end of its paragraph or the next cue; text with no cue is spoken in a neutral delivery.
- **Cues only work without a transcript.** If the Persona's Voice Reference has a transcript (`voice-reference.txt`), the voice engine would read a cue aloud instead of obeying it, so no cue is sent and cues have no audible effect (ADR 0004). Without a transcript they do affect delivery, but the clone is less close to the real voice (ADR 0004).
- **Numbers.** Spell numbers out in words ("sixty", not "60"). The speech check compares your words with what a transcriber hears, and it spells digits it hears back into words, but a Script that spells them out gives the cleanest match.
- A Script with no words to speak stops with `Script <name> has nothing to speak`.

### Front matter and Slide cards

A Script can open with front matter between two `---` lines, and can end with a list of Slide cards after a `<!-- slides -->` line. Neither is ever spoken.

```
---
title: Ask for a raise
hook: "Underpaid?\nHere is the *ask*."
hook_hold: 2.5
---
Welcome back. Today is about one thing: how to ask for a raise.

Here is how you ask.

<!-- slides -->
- at: Welcome back
  kind: title
  eyebrow: Day one
  text: How to ask for a *raise*
- at: Here is how you ask
  kind: cta
  text: Follow for part two
  button: Follow
```

- **Front matter keys.** `title`, `hook`, `face_ends_after`, `hook_hold`, `face_front_s` and `face_back_s` are accepted. `face_front_s` and `face_back_s` are the target lengths in seconds of the opening and closing Face sections; the Video warns when a section misses its target by more than 1.5 s and names the nearest sentence start (ADR 0010); any other key stops the run with an error naming the Script file and the key. `title` does nothing yet; the others change the Video (see below).
- **`at`** is a phrase from the Script. The card cuts in 0.12 s before that phrase is heard and stays until the next card (ADR 0007). Phrases must appear in the Script in the order of the list; a phrase said twice can trigger two cards.
- **Face sections.** Everything spoken before the first entry's phrase is an opening Face section: the Persona is seen speaking. An entry with `kind: face` (and no `text`) brings the face back from its phrase until the next entry. If the first entry's phrase is the Script's opening words and there is no `kind: face` entry, the Video is Slide cards only, with no face.
- **`hook: "<text>"`** with **`hook_hold: <seconds>`** draws the hook over the opening Face section for that many seconds, in white outlined text below the chin, with `*word*` in the Brand pack's `colors.teal`. `\n` inside the quotes breaks the line; a hook of more than two lines gets a warning, as it crowds the face. A Script with a `hook` must give `hook_hold`, a number above 0; an empty hook is no hook. The hook never shows past the opening Face section, and a Video that opens on a Slide card leaves the hook out with a warning. It is drawn by headless Chrome from the Brand pack's `slide.html` at the approved look's 1080×420 and scaled with the frame, so in 16:9 it takes the same share of the frame's height (ADR 0007).
- **`face_ends_after: <phrase>`** in the front matter ends the opening Face section at the end of that phrase, and the first card cuts in there. The phrase must be in the Script, said before the first card's phrase.
- **`kind`** is one of `title`, `bullet` (the default), `stat`, `posting`, `checklist`, `cta` and `face`. A `cta` card needs `button`; a `stat` card needs `value`, the big number. `text` is needed on every card except `face`; `sub` and `eyebrow` are optional. In the text, `*word*` is drawn in the accent colour and `**word**` in the highlight colour. A `checklist` card splits its text into lines at each ` / `.
- These are checked when the Script is read, before anything is spoken or drawn, and an error names the card's number or phrase and the Script file.

## 3. Choose a Voice Reference

The Voice Reference is a short excerpt of the Persona's real voice that the Voice Clone copies. You do not need to do anything if `persona/<name>/voice-reference.wav` already exists.

If it does not, the first `clonecraft voiceover` for that Persona makes one from the Voice Sample (`voice-sample.*`):

1. CloneCraft proposes up to three 20-second stretches that are steady speech: no gap longer than a second, no clipping, and a loudness near the recording's typical level. It writes them to `persona/<name>/voice-reference-candidates/candidate-1.wav`, `-2.wav`, `-3.wav` and prints where each starts.
2. Listen to them, then type the number of the one to use at the prompt (the times here are examples):
   ```
   candidate 1: starts at 214 s  (persona/example/voice-reference-candidates/candidate-1.wav)
   candidate 2: starts at 511 s  (...)
   candidate 3: starts at 702 s  (...)
   Listen to the files above, then type the number of the one to use (1-3):
   ```
   An invalid answer asks again. It is saved as `voice-reference.wav` and used from then on without asking.
3. To choose differently later, delete `voice-reference.wav` and run the Voiceover again.

If you press Ctrl-C or close input at the prompt, nothing is saved and you are told to run the command again.

### The transcript (recommended)

The approved voice was made from a hand-picked reference spoken *with its exact transcript* (ADR 0004, ADR 0005). To use one, put the exact words spoken in the Voice Reference, word for word, in `persona/<name>/voice-reference.txt`. It is only read if present, and CloneCraft does not write it for you. Because a Voice Reference chosen from candidates has no transcript yet, the simplest route is to make your own 15–20 second excerpt, save it as `voice-reference.wav`, write `voice-reference.txt` beside it, and then run the Voiceover.

## 4. Make the Voiceover

```sh
uv run clonecraft voiceover youtube/@examplechannel script-01
```

The arguments are `<platform>/@<handle>` and the Script's name without `.md`.

What happens:

1. The Script is split into pieces.
2. For each piece the voice engine speaks it, a transcriber hears it back, and the **Speech Check** scores the take against your words. Scores run from 0 to 100:

   | Score | Result |
   |---|---|
   | 92 or more | Kept. |
   | 85 up to 92 | Kept, flagged in the output, and one more take is tried. |
   | Under 85 | Another take is tried, up to three in all. The best take scoring 85 or more is kept. |

   Audio left after the last matched word is cut off if it is between 0.5 s and 1 s, and makes the take bad if it is over 1 s. A take that never passes stops the run with `no take of the piece '…' passed the speech check`, and no Voiceover is written.
3. The kept takes are joined with 0.4 s pauses into `platform/<platform>/channels/@<handle>/voiceovers/<name>.wav`.
4. The transcriber hears the whole Voiceover once and its word timings are saved beside it as `<name>.words.json`. Slide cards are placed from them.
5. It records the words it was made from in `<name>.spoken.sha256`, so a Video can tell whether the Voiceover is still current.
6. It prints `Voiceover: <path> (<seconds> s)`.

Each Script has at most one current Voiceover. Running the command again replaces it.

**Listen to the whole Voiceover before you make a Video.** The Speech Check catches dropped and garbled words, not how the voice sounds, and you approve the Voiceover. If it is wrong, change the Script or the Voice Reference and run it again.

The Voiceover step needs about 8.5 GB of free GPU memory (the speech check's transcriber runs on the GPU too). If that much is free it asks nothing. If not, it lists every program holding 100 MiB or more and asks, the same way the Video step does, which to stop (and which services to start again afterwards). Your answers are saved in `settings.local.yaml` and shared with the Video step. If memory is still short after that, it names what holds it and stops.

## 5. Make the Video

```sh
uv run clonecraft video youtube/@examplechannel script-01
uv run clonecraft video youtube/@examplechannel script-01 --format 16:9
```

If the Channel has one Format, `--format` is optional. If it has several, leave it out and the command lists them and stops; give the one you want with `--format`. Each Format's Video is written to its own file, so making one does not replace the other.

### A Video with Slide cards

When the Script has a slides list (section 2), the Video is its Face sections and Slide cards over the Voiceover. Only the Face sections are rendered on the face engine, so a Video with 15 s of face renders about 15 s (plus 0.2 s at each cut), not the whole Voiceover (ADR 0007).

1. The Brand pack is chosen (`brand_pack:` in `channel.yaml`, or the Persona's only pack) and checked: `pack.json`, `slide.html`, the fonts and the mark must all be there.
2. The Voiceover's word timings are read from `<name>.words.json`, for the Slide cards. If there are none, or they belong to an older Voiceover, the voice engine transcribes it again first; this asks about GPU programs the same way the Voiceover step does, and only when memory is short.
3. Each card and Face section is placed where its phrase is heard, cutting in 0.12 s before it. One that would show for less than 0.6 s is left out, with a warning naming its phrase; Face sections that then meet become one. A Face section longer than 45 s gets a warning, because longer heads have drifted (section 5, What to check).
4. Each card is drawn by headless Chrome from the Brand pack's `slide.html` at the Format's size, slowly zooms in by 3.5% while it shows, and cuts straight to the next (ADR 0007).
5. Each Face section is rendered from its own slice of the Voiceover, running 0.2 s past each edge, and all of them in one face-engine session. Its clip is kept in `videos/face-sections/<name>.<width>x<height>/` and used again while the Likeness and that slice of the Voiceover are unchanged. Changing a card's text or the Brand pack, or moving a card that does not touch a Face section, renders nothing and asks no GPU questions. Clips the Video no longer uses are deleted.
6. The GPU questions (below) are asked only when at least one Face section has to be rendered. A Video of Slide cards only needs no Likeness and never uses the face engine.
7. It prints a line naming the Video, its length, how many Slide cards and Face sections it has, whether it ends on an end card, and how many Face sections were rendered.

Two checks give warnings, starting `clonecraft: warning:`, but still write the Video: a card whose text takes longer to read than it shows (15 characters a second plus 1.5 s), and a card whose text runs outside the frame. A hook on a Video that opens on a Slide card is left out with a warning too. Watch those cards and shorten their text if needed.

The Brand pack's `disclosure` text is drawn as a pill over the Video's last Slide card, centred 1330 px down a 1920 px frame and held for the whole card, as the approved look drew it. It is on whenever the Brand pack has that setting, with no flag. A Video in which no Slide card is drawn has nowhere to hold the pill. When its Brand pack was still drawn on (by a hook, or by a card that was later left out), a warning names the Script file.

Two more marks are optional settings in `pack.json`, and a Brand pack without them draws neither:

- **`wordmark`**, such as `"wordmark": "Example Studio"`, turns on the badge: the mark and the wordmark in a small chip at the bottom left of every Face section, 48 px in and 1500 px down a 1920 px frame. That is below the hook and the chin, and above the strip where the platforms put their own captions. The badge is never drawn over a Slide card.
- **`end_card`**, such as `"end_card": {"line": "Learn it *once*.", "url": "example.com"}`, adds an end card after the Voiceover: the mark, the wordmark, the line and the web address, held for 2.5 s in silence. The Video is that much longer than the Voiceover; the audio still fades out at the end of the speech. `*word*` in the line is emphasised and `\n` breaks it. An end card needs a `wordmark`. The disclosure pill stays on the last Slide card, not the end card.

A Brand pack can also name a serif for its cards' `*words*` with `fonts.artifact`, a font file in its `fonts/` folder. Its `slide.html` uses it through `__FONT_ARTIFACT__`; the starter pack names none.

The Video's audio is normalised to the approved look's loudness (-14 LUFS, peaks held at -2 dBFS) and fades out over its last 0.4 s, as the approved look did. The Voiceover file is never changed. The finished Video is then measured: if its loudness is outside -14 ±1.5 LUFS or its true peak is above -1 dBFS, a warning names the file, and the Video is still written. A take shorter than about 0.4 s cannot be measured, so it passes through unchanged and is warned about. Silence cannot be normalised, so it stays silent and is warned about (ADR 0007).

Slide cards work in both Formats. One `slide.html` draws both: Chrome opens it at the Format's size, and the page's CSS picks the layout from the window's shape. The starter pack keeps its 9:16 rules as they were and adds the 16:9 ones near the end of its `<style>`, in a CSS media query for a window at least as wide as it is tall (`min-aspect-ratio: 1/1`), marked with the comment `16:9 (CloneCraft, ADR 0007)`.

To give a Brand pack of your own a 16:9 look, copy that block from `config/brand-pack-starter/slide.html` into its `slide.html` and adjust it. Without one, 16:9 cards use the 9:16 rules, which fit the landscape frame badly. The starter pack's sizes are in pixels for 1080×1920 and 1920×1080; at other resolutions its text is too big or too small for the frame. The text-fit warning is checked at the Video's size, so text that fits a 9:16 card but not a 16:9 one is still caught.

This needs the Script's current Voiceover, and, when there is a Face section to render, the Persona's Likeness for that Format and the face engine. It checks the Voiceover and the Likeness first and names whatever is missing; the face engine is checked once the cards are drawn, and only when a Face section has no kept clip. A Script with no slides list is one Face section over the whole Voiceover, made the same way.

### The GPU questions

The face engine needs about 10 GB of the card's memory free. Before it starts, CloneCraft lists every program holding 100 MiB or more of GPU compute memory and asks, for each program it has no saved answer for:

```
llama-server, the system service llama-server@11434.service, holds 8200 MiB of GPU memory. Stop it for the Video? (y/n)
Start llama-server@11434.service again when the Video step ends? (y/n)
```

- Answer `y` to stop it. For a system service you are then asked whether to start it again afterwards.
- A program that is not a service can only be stopped; CloneCraft tells you to start it again yourself.
- Everything is asked before anything is stopped. Programs under 100 MiB and the desktop display are left alone.
- Services are stopped and started with `sudo -n systemctl`, which fails at once instead of waiting for a password (see [setup-and-maintenance.md](setup-and-maintenance.md)).
- Your answers are saved in `settings.local.yaml` in the repo root (git-ignored), so you are only asked about programs it has not seen before. To be asked again, delete that file or the program's entry in it.
- When the step ends, whether it worked, failed or you pressed Ctrl-C, every service you asked to restart is started again. If one cannot be, the command exits with an error naming it even though the Video was made.
- If less than about 10,000 MiB is still free after clearing, the step stops and names what holds memory, and starts again what it should. Close those applications yourself and run it again. Never stop your compositor or shell.

The questions need a person at the keyboard. If there is no input, the command stops with `no answer was given, so nothing was stopped`.

### What it does

1. The Likeness for the Format is centre-cropped to its aspect and scaled to what the face engine works at: 480×832 for 9:16, 832×480 for 16:9. The file on disk is not changed.
2. The face engine renders a 25 fps clip of that portrait speaking each Face section's slice of the Voiceover (the whole Voiceover when the Script has no slides list). A clip kept from an earlier run is used instead when nothing it depends on has changed.
3. The clip is upscaled to the Channel's resolution and converted to its frame rate, and the Voiceover becomes the audio.
4. The result is written to `platform/<platform>/channels/@<handle>/videos/<name>.<width>x<height>.mp4`, for example `script-01.1080x1920.mp4`, replacing any earlier Video of that Script in that Format.

It prints one line, like this (the numbers are an example):

```
Video: platform/youtube/channels/@examplechannel/videos/script-01.1080x1920.mp4 (9:16; 95.2 s long; 0 Slide cards, 1 Face sections, 1 rendered; face engine 9100.3 s, whole Video step 9150.8 s)
```

### How long it takes

Rendering is slow and runs the GPU flat out.

- A 5-second test on the RTX 5070 with the tuned settings (fp8 weights, `multitalk` scheduler; see `config/infinitetalk-graph.json`) took 301.9 s for the face engine; on the older Q8 + `dpm++_sde` settings it was 370.0 s engine-only (437.7 s through the whole step). Sampling took about 23 s per 81-frame window before tuning.
- A full-length 77.6-second Video took 4,058 s (about 68 minutes) for the face engine on those older settings; the tuned settings measured about 23% faster on an 8-second 16:9 test, so plan on roughly half a minute of rendering per second of Video. That length has not yet been re-rendered on the tuned settings, and long faces still drift (see below).

### What to check in the Video

Watch the whole thing. You are looking for:

- **Identity drift or colour shift** over its length. The engine warns of colour shift past about a minute, and nothing longer than about 27 s has been confirmed good on this machine yet (ADR 0002).
- **Head motion and blinking** that look natural.
- **Lip sync** that matches the words.

Each Script has at most one current Video. To remake it, run the command again.

## 6. Everyday habits

- Keep Scripts, Voiceovers and Videos in their Channel folders; do not move them by hand, because the commands find files by name.
- Back up `persona/` and `platform/` yourself. They are not in git.
- One Voiceover or Video at a time: both use the GPU.
- If you press Ctrl-C, the command prints `clonecraft: interrupted` and exits with code 130; the GPU programs you agreed to restart are still started again.

## 7. When something goes wrong

Errors are one line starting `clonecraft:`, and exit code 1. The message names the file or program at fault.

| Message starts with | What it means and what to do |
|---|---|
| `The Voiceover … was not made from the current words of …` | The Script's words changed after its Voiceover was made, or the Voiceover predates this check. Run the `clonecraft voiceover` command it names, then the Video again. A change only to Delivery Cues does not need this. |
| `Channel … not found` | The folder `platform/<platform>/channels/@<handle>` does not exist, or you typed the Channel wrongly. Use `platform/@handle`, for example `youtube/@examplechannel`. |
| `Channel … has no channel.yaml` / `… does not name a persona` | Add `channel.yaml` with a `persona:` line. |
| `… needs a formats: list …` | Complete each entry of the `formats:` list in `channel.yaml` (aspect, resolution and fps). |
| `… has a single format: block; change it to a formats: list` | Change `format:` to `formats:` with one `- aspect:` entry. |
| `Channel … has several Formats (…); choose one with --format` | Run the command again with `--format` and one of the aspects it lists. |
| `Format … is not one of this Channel's Formats` | The `--format` aspect is not in `channel.yaml`. Use one of the aspects listed. |
| `Persona … has no Likeness for 16:9` | Add `likeness-horizontal.<ext>` to the Persona's folder. |
| `Script … not found` | Put `<name>.md` in the Channel's `scripts/` folder. |
| `Script … has nothing to speak` | The Script has no words, only cues or blank lines. |
| `Persona … not found` / `has no Likeness` | Add the folder `persona/<name>/` and a `likeness.<ext>` in it. |
| `Persona … has no Voice Reference and no Voice Sample` | Add `voice-sample.<ext>` or a ready `voice-reference.wav`. |
| `No steady, unclipped 20 s stretch was found in …` | The Voice Sample is too noisy, clipped or gappy. Record a cleaner one. |
| `No Voice Reference was chosen for Persona …` | You left the prompt without choosing. Run the command again. |
| `The voice engine is not installed yet (…)` / `The face engine is not installed yet (…)` | Follow the install steps in [setup-and-maintenance.md](setup-and-maintenance.md). The message lists what is missing. |
| `not enough free GPU memory for the voice engine` | Free some GPU memory and run `voiceover` again. Nothing was stopped. |
| `only … MiB of GPU memory is free and the Voiceover needs about 8704 MiB` | The message names what still holds the memory. Close it, or answer `y` when asked about it, and run `voiceover` again. |
| `no take of the piece '…' passed the speech check` | The voice kept dropping or garbling that piece. Reword it or shorten the sentence, or choose a clearer Voice Reference. |
| `Script … has no Voiceover yet` | Run `clonecraft voiceover` for that Script first. |
| `Format … is not supported yet` | The aspect is not 9:16 or 16:9. Change it in `channel.yaml`. |
| `only … MiB of GPU memory is free and the Video needs about 10000 MiB` | Close the programs it names, then run again. |
| `… did not exit within 20 s of being asked to stop` | A program ignored the stop request. Close it yourself. |
| `` `sudo -n systemctl …` failed `` | CloneCraft could not stop or start a service without a password. See [setup-and-maintenance.md](setup-and-maintenance.md). |
| `the Video was made, but … could not be started again` | The Video is fine. Start the named service yourself. |
| `the face clip is shorter than its slice of the Voiceover` / `ComfyUI …` | The face engine failed. Read the engine output printed above the error, then see the face-engine section of [setup-and-maintenance.md](setup-and-maintenance.md). |
| `the front matter in … has unknown key …` | Remove the key, or check its spelling. Allowed keys are listed in the message. |
| `Slide card <n> in … has …` / `… needs …` | That card has a key, kind or missing field the template cannot draw. The message names what to change. |
| `Slide card phrase '…' in … is not in the Script` / `is said before the card above it` | Copy the phrase exactly from the Script, and keep the cards in the order the phrases are spoken. |
| `the front matter in … has a hook but no hook_hold` / `hook_hold in … must be a number of seconds above 0` | Add `hook_hold:` with the seconds the hook shows, such as `hook_hold: 2.5`. |
| `the Video's audio is silent in …, so it cannot be normalised to -14 LUFS` | The Voiceover has no sound in it. Remake the Voiceover; silence cannot be made louder. |
| `loudness … LUFS in …, want -14 ±1.5` / `true peak … dBFS in …, want ≤ -1` | The Video is still written, but its audio is out of range. A take shorter than about 0.4 s cannot be measured, so it is left as it is: remake a longer Voiceover. Otherwise listen for clipping. |
| `the loudness of … could not be measured: …` / `… ffmpeg's report was not read` / `… ffmpeg printed no summary` | ffmpeg could not read the audio of that Voiceover or Video. Check the file plays; remake the Voiceover if it does not. |
| `the disclosure is not shown in …: no Slide card is drawn in it` | No Slide card of the Script is drawn, so the disclosure pill has nowhere to go. Check the cards: one that is spoken too briefly is left out with its own warning. |
| `face_ends_after phrase '…' in … is not in the Script` / `must be said before the first Slide card phrase` | Copy the phrase exactly from the Script, from before the first card's phrase. |
| `face_ends_after phrase '…' was not heard in the Voiceover` | Change the phrase to what is actually said, or remake the Voiceover. |
| `Slide card phrase '…' was not heard in the Voiceover` | The transcriber did not hear that phrase. Listen to the Voiceover there, then change the phrase to what is actually said, or remake the Voiceover. |
| `everything in the slides list would show for less than 0.6 s` | The phrases are too close together. Spread them out. |
| `Persona … has no Brand pack` / `has several Brand packs` | Copy `config/brand-pack-starter` into `persona/<name>/brand-packs/<pack>/`, or name one with `brand_pack:` in `channel.yaml`. |
| `Brand pack … not found` / `has no …` / `… is missing the setting …` / `names font …` / `names mark …` | Fix the Brand pack folder or its `pack.json` as the message says. |
| `… has an end_card but no wordmark` / `… has an empty wordmark` | The end card draws the wordmark: add `"wordmark": "<name>"` to `pack.json`, or remove `end_card`. |
| `google-chrome was not found on PATH; it draws the Slide cards and the hook` / `google-chrome could not draw the Slide card` / `google-chrome did not finish the Slide card` | Install Google Chrome; see [setup-and-maintenance.md](setup-and-maintenance.md). |
| `Voiceover … has no word timings and the voice engine that makes them is not installed` | Install the voice engine, or remake the Voiceover on a machine that has it. |
| `… is not a word timings file` | Delete the named `.words.json`; the next run makes it again. |
| `… is not a valid settings file` | `settings.local.yaml` is damaged. Fix it or delete it to be asked the GPU questions again. |

## What this guide does not cover

Writing Scripts and publishing Videos are outside CloneCraft. B-roll and music are not added. A Video is one continuous talking-head shot, or, when its Script has a slides list, its Face sections and Slide cards (ADR 0007).

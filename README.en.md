# ShinyColorsPet

[繁體中文](README.md) | [日本語](README.ja.md) | [English](README.en.md)

ShinyColorsPet is an unofficial Windows desktop companion inspired by *THE IDOLM@STER SHINY
COLORS*. It combines Spine 3.6 desktop characters with character chat, long-term memory,
affection, voice interaction, and outfit management in one local application.

This repository contains the application, reviewed UI assets, character prompts, and voice
references. It does not contain character Spine models. Users must obtain compatible assets from
a lawful source and import them themselves.

## Highlights

- **Spine 3.6 desktop characters** with transparency, dragging, click interaction, cursor gaze,
  semantic actions, expressions, and lip sync.
- **Process isolation for multiple characters**, preventing one character failure from directly
  taking down the management interface.
- **Character and outfit management** with Spine asset validation, unit/character browsing, and
  per-character default outfits.
- **Character chat** through OpenAI-compatible APIs or an experimental third-party `openai-oauth`
  proxy that requires explicit consent.
- **Relationship and memory** stored independently per character: conversation history, affection,
  relationship summaries, long-term memories, Persona settings, and built-in personalities from
  `souls/`. Producer details can be configured, but the producer's name is never sent in prompts.
- **Voice interaction** through one-click local Irodori-TTS v4.1 or OpenAI-compatible TTS, plus local
  `faster-whisper-large-v3` or OpenAI-compatible speech recognition.

## Main features

| Area | Capabilities |
|---|---|
| Desktop characters | Start/stop multiple characters, show/hide, always-on-top, scale, drag, click-through |
| Motion and appearance | Actions, expressions, gaze, idle/random actions, outfits, rendering settings |
| Models and assets | Import and validate a `dresses.json` folder or an individual Spine 3.6 asset set |
| Chat and AI | Character-scoped chat, OpenAI-compatible LLM, Persona, producer details, and screen context |
| Relationship data | Affection, summaries, long-term memory, history, memory album, and statistics |
| Voice | Irodori-TTS Japanese speech, character reference voices, microphone input, and Whisper ASR |
| Data management | Backup/restore, saved settings, activity log, and system tray controls |

## Importing character models

1. Prepare a Spine 3.6 model. A batch-import folder must contain `dresses.json`; an individual
   asset set must directly contain `data.json` and `data.atlas`.
2. Open **Models & Assets** and select the downloaded, extracted folder.
3. Choose **Update character models**. Validated assets are copied to
   `%LOCALAPPDATA%/ShinyColorsPet/models/`, with generated manifests stored under `manifests/`.
4. After the automatic rescan, launch the model from **Unit → Character**.

## Running and building from source

Requirements: 64-bit Windows 10/11, 64-bit Python 3.10, and a display environment capable of
running Qt WebEngine/OpenGL.

```powershell
git clone https://github.com/jerygood870208/ShinyColorsPet.git
cd ShinyColorsPet
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Build and verify the portable Windows application:

```powershell
.\.venv\Scripts\python.exe packaging\freeze.py build_exe
.\.venv\Scripts\python.exe tools\validate_catalog.py data\catalog.json
.\.venv\Scripts\python.exe tools\validate_release_assets.py
.\.venv\Scripts\python.exe tools\verify_frozen_build.py build\ShinyColorsPet
```

The result is written to `build/ShinyColorsPet/`. Distribute the entire directory, not only
`ShinyColorsPet.exe`.

### Local Irodori-TTS

Select **Built-in Irodori-TTS v4.1** under **TTS Settings** to create an isolated environment and
install the official [Irodori-TTS](https://github.com/Aratako/Irodori-TTS) and
[Irodori-TTS-Server](https://github.com/Aratako/Irodori-TTS-Server) with one click. Local mode
requires Python 3.10 or newer, Git for Windows, a compatible NVIDIA GPU, and approximately 9 GB of
free space. Non-WAV reference audio also requires FFmpeg on the system `PATH`. The runtime and model
are stored under `%LOCALAPPDATA%/ShinyColorsPet/irodori-runtime/`, outside the repository, and the
service listens only on `127.0.0.1:8088`.

## Localization status

The UI fully supports Traditional Chinese, Simplified Chinese, Japanese, and English. Catalogs live
under `shiny_pet/locales/` and cover navigation, pages, forms, hints, chat controls, and dynamic status
text. A language change takes effect after restarting the application.

## Thanks to the open-source community

- [BANDORI-PET-REV](https://github.com/HELPMEEADICE/BANDORI-PET-REV), whose desktop-pet,
  process-isolation, settings, and chibi-mode designs informed parts of this project.
- [ShinyColorsDB](https://github.com/ShinyColorsDB) and
  [shinycolors.moe](https://shinycolors.moe/), which provided an important foundation for
  character data, UI resources, and Spine display research.
- [Irodori-TTS](https://github.com/Aratako/Irodori-TTS),
  [Irodori-TTS-Server](https://github.com/Aratako/Irodori-TTS-Server), and
  [faster-whisper](https://github.com/SYSTRAN/faster-whisper), which power the local voice features.
- [Spine Runtimes](https://github.com/EsotericSoftware/spine-runtimes), Python, Qt for Python,
  cx_Freeze, Pillow, PyYAML, NumPy, python-sounddevice, libsndfile, and the maintainers and
  contributors of all related open-source projects.

## License and rights

Except where explicitly stated otherwise, original project code and GPL-compatible adapted code
are released under [GPL-3.0-only](LICENSE). The GPL does not grant rights to third-party trademarks,
characters, artwork, audio, models, or the Spine Runtime.

`vendor/spine-runtime-3.6/` is not covered by the GPL. It is governed by the bundled
[Spine Runtimes Software License](vendor/spine-runtime-3.6/LICENSE). Source and binary
redistributions must include that license and its terms, and anyone developing or distributing an
application containing the runtime must confirm that they hold any required Spine license. See
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for details.

Rights in the *THE IDOLM@STER SHINY COLORS* name, characters, images, audio, models, trademarks,
and related materials belong to BANDAI NAMCO Entertainment Inc. and their respective rights
holders. This is an unofficial fan project and is not affiliated with, sponsored by, or endorsed
by those rights holders. 

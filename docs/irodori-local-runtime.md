# Managed local Irodori-TTS

ShinyColorsPet supports two OpenAI-compatible Irodori deployment modes:

- `irodori_local`: install and run an application-managed Irodori-TTS-Server.
- `openai_compatible`: connect to an independently managed local or remote server.

These are the only TTS provider modes. Legacy `auto` and `qwen_local` settings migrate to
`irodori_local`; no Qwen runtime or Qwen-bundled FFmpeg is used.

The managed runtime is stored beside the user settings in `irodori-runtime`. It has its own
Python virtual environment, Hugging Face cache, logs, generated server configuration, and
converted reference voices. Large inference dependencies are not imported into the GUI process.

## Installation flow

Select **內建 Irodori-TTS v4.1** on the TTS settings page and run the one-click installer. The
installer creates an isolated environment, installs CUDA 12.8 PyTorch and the official pinned
Irodori-TTS-Server, prepares numeric files in `audio_reference`, and starts the loopback server.

Requirements:

- Python 3.10 or newer from python.org
- Git for Windows
- NVIDIA GPU with a compatible driver
- System FFmpeg available on `PATH` when a reference needs conversion from M4A, MP3, FLAC, or OGG
- Approximately 9 GB of free disk space for the runtime and model cache

The server binds to `127.0.0.1:8088`, loads `Aratako/Irodori-TTS-v4.1-Small`, and exposes the
standard `/v1/audio/speech` endpoint. ShinyColorsPet starts it lazily on the first local synthesis
request and stops the process it owns when TTS is disabled or the application exits.

## Voice mapping

Numeric character references are converted or copied into the managed server voice directory:

```text
audio_reference/01.m4a -> person_01.wav -> voice: person_01
audio_reference/03.m4a -> person_03.wav -> voice: person_03
```

The current catalog character selects the matching `person_NN` voice. The reference controls
speaker identity; `irodori.caption` is generated only from semantic action/expression directives
and describes emotional delivery without gender, age, pitch, or timbre characteristics.

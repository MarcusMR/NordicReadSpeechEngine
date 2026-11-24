# NordicRead Speech Engine

A standalone English speech generator using Kokoro, Misaki and the eSpeak NG
pronunciation fallback. It provides a local HTTPS API with live PCM audio
streaming and a command to save speech as a WAV file.

- 20 American English voices and 8 British English voices.
- Streamed audio, cancellation and speed changes during generation.
- Cached models for offline use.
- Clients handle playback, buffering, volume and saving.

The engine runs independently of NordicRead and opens no audio device.
The current API accepts connections from this computer only; remote hosting is
not implemented.

## Quick start

Run these commands from the repository root with 64-bit Python 3.12:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py --list-voices
.\.venv\Scripts\python.exe run.py --text "Hello, this is a test." --voice af_heart --output preview.wav
```

The first speech run downloads missing model and voice files. Later runs reuse
the Hugging Face cache. Use `--cache-dir PATH` to select an existing cache root
containing a `hub` directory, or set `HF_HOME`.

For British English, select a British voice such as `bf_emma`. `--speed` accepts
a factor from `0.5` to `2`. See `run.py --help` for all command options.

To use a populated cache without Internet access:

```powershell
.\.venv\Scripts\python.exe run.py --offline --cache-dir PATH --text "This speech is generated offline." --voice bf_emma --output preview.wav
```

The WAV command writes its JSON result to stdout and dependency diagnostics to
stderr. Ctrl+C cancels generation.

## Run the local API

```powershell
.\.venv\Scripts\python.exe run.py --https
```

The engine prints the path to its private `session.json` descriptor on stderr.
Clients use that descriptor to connect to the authenticated HTTPS service.
The model prepares in the background while the health endpoint is available.

See the [API guide](docs/api.md) for connection details, endpoints and the
[independent client example](examples/stream_to_wav.py).

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

Tests use controlled readiness signals and fake runtimes over real TLS. They
exercise streaming, authentication, cancellation, speed changes and shutdown
without downloading models or opening an audio device.

## Documentation

- [API and audio streaming](docs/api.md)
- [Build the Windows executable](docs/building.md)
- [Dependencies, notices and source provenance](docs/third-party.md)

## License

The engine source is [GPL-3.0-or-later](LICENSE). Dependencies retain their own
licenses; see the [dependency notes](docs/third-party.md).

# NordicRead Speech Engine

A standalone, local English speech application. It uses upstream Kokoro 0.9.4,
Misaki English and the eSpeak NG pronunciation fallback, and generates a live PCM audio stream. Playback belongs to the client. It supports 20 American and 8 British English voices.
It imports no NordicRead UI, preference, consent, OCR or update modules.

This repository contains only the speech engine. Its `.venv` and model cache
are independent of any client application. Models use the normal Hugging Face
cache unless `--cache-dir PATH`, `HF_HOME`, or explicit `--assets PATH` is supplied.

This engine's source is licensed under GPL-3.0-or-later; see [LICENSE](LICENSE).
Its dependencies retain their own licenses. [THIRD_PARTY.md](THIRD_PARTY.md)
records important provenance and the release work that remains. This source
separation is an engineering design, not a legal determination that every
distribution of a proprietary client is independent under the GPL.

## Install and run independently

From the repository root, using 64-bit Python 3.12:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py --list-voices
.\.venv\Scripts\python.exe run.py --text "Marcus uses Kubernetes." --voice af_heart --output preview.wav
```

The first speech run prepares missing model and voice files. Repeated runs reuse
the Hugging Face cache. No reader application needs to be running. To reuse an
existing cache, pass `--cache-dir PATH`, where PATH contains the `hub` directory.
`HF_HOME` is also supported. `--offline` blocks Internet sockets and requires
existing files. A complete directory supplied with `--assets PATH` must contain
`config.json`, `kokoro-v1_0.pth`, and voices either directly or under `voices/`.
Frozen releases always require their own bundled assets and never download them.

To generate a WAV without using an audio device:

```powershell
.\.venv\Scripts\python.exe run.py --text "This is a test." --voice bf_emma --speed 1 --output speech-preview.wav
```

The CLI returns a JSON `done` result on stdout and sends dependency diagnostics
to stderr. It does not log input text. `--text` is a one-shot command; Ctrl+C
cancels it. `--output` is a CLI option and is not accepted as a JSON request path.

## Local HTTPS streaming API, version 3

Run `python run.py --https --session-dir PATH`, where PATH is a
new private directory under your user profile. NordicRead creates a fresh Temp
directory for each owned engine. On Windows it inherits the profile ACLs; on
POSIX the directory has mode 0700. Do not put this directory in a shared folder.

The engine binds only `127.0.0.1` on an OS-assigned port. It writes `session.json`
atomically with the port, a random bearer token, and a fresh self-signed TLS
certificate. The private key is removed immediately after loading it into TLS.
Clients must trust only that session certificate, verify its loopback IP address,
and send `Authorization: Bearer TOKEN` on every call. Never disable certificate
verification. Nothing is added to the Windows certificate store. No stdin/stdout
pipes carry API traffic. API credentials and input text are not logged.

The server starts before background model preparation, so health and shutdown
work while dependencies and Kokoro load. `GET /v1/health` returns `protocol: 3`,
`status` (`starting`, `ready`, `failed`, or `closing`), a message, and 28 voice IDs.
A startup failure remains available through health until shutdown.

| Method and endpoint | JSON body / result |
| --- | --- |
| `GET /v1/health` | Readiness, protocol, error and voices. |
| `POST /v1/speech` | `{"text":"Hello, this is a test.","voice":"af_heart"}`; returns HTTP 202 with a job ID and `audio_url`. Optional `id` and numeric `speed`. |
| `GET /v1/jobs/ID/audio` | Single-consumer live PCM stream. Open it within 10 seconds after generation becomes ready. |
| `GET /v1/jobs/ID` | `queued`, `running`, `completed`, `cancelled` or `failed`. Finished results include `code`, `message`, `cancelled` and `chunks`. |
| `POST /v1/jobs/ID/stop` | `{}` cancels one active or queued job. |
| `POST /v1/stop` | `{}` cancels all jobs. |
| `PATCH /v1/jobs/ID` | `{"speed":1.5}` changes upcoming synthesis chunks. |
| `POST /v1/shutdown` | `{}` cancels generation, removes the session descriptor and exits. |

Send mutation bodies as `application/json`. IDs are integers or strings with
1-64 letters, digits, underscores or hyphens; text is limited to 100,000
characters, and speed is a finite factor from 0.5 to 2. Completed input text is
released, and retained job results and queued work are bounded. Speech requests
are processed in order using one loaded model for both accents. Invalid requests
return a 4xx response without killing the engine. A failed synthesis affects
that job; the engine remains reusable.

No CORS access is granted; browser Origin requests are rejected. This is a
private desktop API, not a LAN or public web service. Applications running as
the same Windows user are within the same trust boundary.

NordicRead passes `--parent-pid PID`: if that owner disappears, the engine cancels
and exits. Closing during native model loading or inference also has a bounded
process termination fallback. Standalone API use without a parent continues
until the shutdown endpoint or Ctrl+C. Temporary session directories should be
removed by their creator after the process has exited.

### Audio delivery

The API is implemented with Flask. This local development prototype uses a
threaded Werkzeug WSGI server with TLS, a bounded connection count, no debugger
or reloader, and no browser access. Select and test a production serving setup
before distributing a public service release.

After submitting a speech request, open its returned `audio_url` immediately.
The response is HTTP/1.1 chunked `application/octet-stream` with these headers:

```text
X-Audio-Format: pcm_s16le
X-Sample-Rate: 24000
X-Channels: 1
X-Sample-Width: 2
```

The body is signed 16-bit little-endian mono PCM at 24,000 Hz. There is no WAV
header, JSON, base64 or shared filename in the stream. HTTP chunk boundaries
are not audio sample or utterance boundaries: preserve incomplete 2-byte
samples across transport reads. Each job stream can be opened once.

Audio is yielded as Kokoro produces it; the entire utterance is not buffered
first. Application queues are bounded. A slow or disconnected consumer cannot
cause unlimited PCM accumulation. Disconnecting the stream cancels generation
when the disconnect is observed. Use the Stop endpoint as well for prompt
cancellation during native inference.

Consumers own the audio device, buffering, playback, volume, pause/resume and
saving. A completed generation job does not mean client playback has finished.
Speed changes affect upcoming synthesis chunks; already received samples retain
their original speed. Stopping playback should immediately discard local buffers
and send Stop to the generator. NordicRead implements this ownership locally.

A synthesis error after streaming starts closes the HTTP body without successful
completion. Always check the final JSON job result and reject truncated audio;
never treat EOF alone as proof of success. No audio device is opened by this
program, and API requests cannot choose output paths. `--text --output PATH`
is the separate one-shot WAV-file CLI. `--offline` rejects Internet connections
while leaving local HTTPS available.

An independent standard-library client example, with no NordicRead imports:

```powershell
python examples/stream_to_wav.py --session-dir PATH --text "This standalone application streams audio." --output output.wav
```

## Tests and release limitations

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

The tests use controlled readiness events and fake runtimes over real TLS
connections. They exercise authentication, certificate verification, Stop,
rate changes, shutdown during warmup and request recovery without downloading
models. Client applications should additionally test their own process ownership,
cancellation and termination behavior. Those client tests belong to their repositories.

Actual cached-model synthesis is a separate integration check:

```powershell
.\.venv\Scripts\python.exe run.py --offline --cache-dir PATH --text "This standalone application generates speech." --voice af_heart --output artifacts/smoke.wav
```

Replace `PATH` with a populated Hugging Face cache root. Unit tests never
download models. See [BUILDING.md](BUILDING.md) for the independent Windows
executable build recipe.

Packaging and installed Windows lifecycle checks must also run on the built
independent executable. Passing source tests does not establish that an MSIX
has been rebuilt by a client distributor or that its distribution licensing is ready.

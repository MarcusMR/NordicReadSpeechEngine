# Local HTTPS API

Protocol version: **3**. The service generates audio; the client owns playback.

## Start and connect

From the repository root:

```powershell
.\.venv\Scripts\python.exe run.py --https
```

The engine binds to `127.0.0.1` on an OS-assigned port. It prints the path to a
private `session.json` descriptor on stderr. The descriptor contains the port,
protocol version, random bearer token and a fresh self-signed TLS certificate.

A client must trust that session certificate, verify its loopback IP address,
and send `Authorization: Bearer TOKEN` on every request. Keep certificate
verification enabled. The TLS private key is removed after loading; no
certificate is installed in the operating system's trust store.

Use `--session-dir PATH` to choose a new private session directory. On Windows,
use a location under your user profile so it inherits your profile's ACLs;
POSIX session directories use mode `0700`. Keep the descriptor out of shared
folders. The API does not log request text or session credentials.

## Readiness and endpoints

The HTTPS server starts before model preparation. Poll `GET /v1/health` until
`status` is `ready` before submitting speech. Health includes `protocol: 3`,
the status, a message and 28 voice IDs. Status is one of `starting`, `ready`,
`failed` or `closing`. Startup failures remain available through health until
shutdown.

| Method and endpoint | Request / response |
| --- | --- |
| `GET /v1/health` | Readiness, protocol, message and voices. |
| `POST /v1/speech` | `{"text":"Hello, this is a test.","voice":"af_heart"}`; returns HTTP 202 with a job ID and `audio_url`. Optional `id` and numeric `speed`. |
| `GET /v1/jobs/ID/audio` | Single-consumer live PCM stream. Open promptly after submitting the job. |
| `GET /v1/jobs/ID` | Job status: `queued`, `running`, `completed`, `cancelled` or `failed`. Finished results include `code`, `message`, `cancelled` and `chunks`. |
| `PATCH /v1/jobs/ID` | `{"speed":1.5}` changes upcoming synthesis chunks. |
| `POST /v1/jobs/ID/stop` | `{}` cancels one active or queued job. |
| `POST /v1/stop` | `{}` cancels all jobs. |
| `POST /v1/shutdown` | `{}` cancels generation, removes the descriptor and exits. |

Send mutation bodies as `application/json`. Job IDs are integers or strings
with 1–64 letters, digits, underscores or hyphens. Text is limited to 100,000
characters; speed must be a finite factor from `0.5` to `2`.

Requests are processed in order using one loaded model for both accents.
Queued work and retained results are bounded; completed input text is released.
Invalid requests return a 4xx response. A failed job leaves the service reusable.
API requests cannot choose output paths; `--text --output PATH` is a separate,
one-shot WAV command.

## Receive audio

After submitting a job, open its `audio_url` immediately. A consumer must attach
within 10 seconds after generation becomes ready. Each stream can be opened
once. The response is HTTP/1.1 chunked `application/octet-stream` with:

```text
X-Audio-Format: pcm_s16le
X-Sample-Rate: 24000
X-Channels: 1
X-Sample-Width: 2
```

The body is signed 16-bit little-endian mono PCM at 24,000 Hz. It has no WAV
header, JSON, base64 or shared filename. HTTP chunks can split audio samples;
preserve incomplete 2-byte samples between reads.

Audio is streamed as it is generated, with bounded queues for backpressure.
A slow or disconnected consumer cannot cause unlimited audio accumulation.
Disconnecting cancels generation when observed; also send Stop for prompt
cancellation during native inference.

Clients manage the audio device, buffering, playback, pause/resume, volume and
saving. Generation completing does not mean playback has finished. Speed
changes affect upcoming synthesis chunks; received audio keeps its original
speed. On Stop, discard local playback buffers and cancel the generation job.

Always check the final JSON job result. A synthesis error after streaming
starts closes the body without successful completion; EOF alone does not
prove success. Reject failed results and truncated audio.

## Client example

Keep the service running and wait for health to report `ready`. In another
terminal, use the directory containing its `session.json`:

```powershell
.\.venv\Scripts\python.exe examples/stream_to_wav.py --session-dir PATH --text "This standalone application streams audio." --voice af_heart --output output.wav
```

The [example](../examples/stream_to_wav.py) uses Python's standard library
to receive the PCM stream and save it as a WAV file.

## Lifecycle and deployment scope

Without an owner, the service runs until Ctrl+C or `/v1/shutdown`. An application
can pass `--parent-pid PID` to make the engine exit if its owning process dies.
Owners should use bounded process termination when native model loading or
inference prevents cooperative shutdown. Creators remove explicit session
directories after the process exits; automatically created ones are removed
by the engine.

The current Flask/Werkzeug server is intended for local use. It uses TLS and a
bounded connection count, with no debugger or reloader. Browser Origin requests
are rejected and no CORS access is granted. Applications running as the same
Windows user share the trust boundary. A production serving setup is needed
before exposing a remotely hosted service.

`--offline` requires cached assets and blocks Internet sockets while retaining
the local HTTPS API. A complete `--assets PATH` directory contains `config.json`,
`kokoro-v1_0.pth` and voice `.pt` files, directly or under `voices/`. Frozen
executables require bundled assets and never download them.

[Back to README](../README.md)

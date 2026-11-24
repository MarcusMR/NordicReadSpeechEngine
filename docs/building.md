# Build the Windows executable

The PyInstaller recipe builds a Windows console application with bundled
models and runtime dependencies.

## Prepare the environment

Use 64-bit Windows and Python 3.12. Create `.venv` using the
[quick start](../README.md), then install the build requirements:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe build_speech_engine.py --help
```

## Prepare the inputs

| Input | Required contents |
| --- | --- |
| Model directory | `config.json`, `kokoro-v1_0.pth` and all 28 English voice `.pt` files, directly inside it or under `voices/`. |
| Notices directory | The supplemental [notices](../notices/README.md) and dependency license inventory for the exact environment being frozen. |
| Threading runtime | The Windows runtime DLL supplied through `--threads-runtime`. The tested Windows build uses `vcruntime140_threads.dll` from the Visual C++ runtime. |

Use absolute paths for these inputs. The build does not download models or
prepare a dependency notice inventory for you.

## Build

After preparing the model and notice directories:

```powershell
.\.venv\Scripts\python.exe build_speech_engine.py --assets C:\speech-build\models --notices C:\speech-build\notices --threads-runtime "$env:WINDIR\System32\vcruntime140_threads.dll" --distpath artifacts/dist --workpath artifacts/work --specpath artifacts/spec
```

The PyInstaller recipe creates:

```text
artifacts/dist/NordicReadSpeechEngine/
  NordicReadSpeechEngine.exe
  _internal/
  LICENSE
  source/
  DISTRIBUTION-REVIEW.txt
```

The output includes runtime files, bundled models, notices and this engine's
source and build recipe.

## Verify the build

Run the [unit tests](../README.md), then verify offline synthesis and lifecycle
behavior against the frozen executable and its actual bundled assets. Source
tests do not replace those executable checks.

Keep generated models, DLLs, audio, packages and environment inventories out of
Git. Record the dependency versions, notices and source revisions used by
the build; see [dependency notes](third-party.md).

[Back to README](../README.md)

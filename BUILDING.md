# Build the standalone Windows executable

The source program can run directly using the README commands. A frozen
executable is a separate optional Windows build; this repository does not build,
sign or publish an MSIX, install software, or build a client application.

Use 64-bit Windows and Python 3.12. Create `.venv` as described in the README,
then install the build requirements:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe build_speech_engine.py --help
```

The build requires three inputs prepared by the distributor:

- A complete model directory containing `config.json`, `kokoro-v1_0.pth`, and
  all 28 English voice `.pt` files (directly inside it or under `voices/`).
- A notices directory containing the supplemental `notices/` files and the
  dependency license inventory for the exact environment being frozen.
- The native Windows threading runtime DLL used by the selected dependencies,
  supplied explicitly through `--threads-runtime`.

Pass absolute paths for these inputs. For example, after preparing them:

```powershell
.\.venv\Scripts\python.exe build_speech_engine.py --assets C:\speech-build\models --notices C:\speech-build\notices --threads-runtime C:\speech-build\libwinpthread-1.dll --distpath artifacts/dist --workpath artifacts/work --specpath artifacts/spec
```

This uses the existing PyInstaller build recipe. It creates
`artifacts/dist/NordicReadSpeechEngine/NordicReadSpeechEngine.exe` with its
runtime files and a copy of the engine source. It has no import or build
dependency on the NordicRead reader repository. The executable still needs
offline synthesis and lifecycle checks against the precise bundled assets.

Keep generated models, DLLs, packages, audio and environment inventories out of
Git. Review [THIRD_PARTY.md](THIRD_PARTY.md) before distributing binaries; this
source repository does not contain the complete corresponding source of every
third-party binary.

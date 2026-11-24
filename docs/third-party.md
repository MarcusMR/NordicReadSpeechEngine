# Dependencies and source provenance

The engine source is [GPL-3.0-or-later](../LICENSE). Dependencies keep their
own copyrights, licenses and notice requirements. Versions are pinned in
[requirements.txt](../requirements.txt); supplemental texts are kept under
[notices/](../notices/README.md). Generated inventories belong in build output.

This inventory records the current source and binary provenance. It does not
constitute a complete corresponding-source package for a binary release.

## Recorded dependencies

| Component | Version / license | Primary source |
| --- | --- | --- |
| cryptography | 50.0.2 / Apache-2.0 OR BSD-3-Clause, bundled third-party notices also apply | https://cryptography.io/en/latest/license/ |
| Kokoro inference code | 0.9.4 / Apache-2.0 | https://github.com/hexgrad/kokoro |
| Kokoro-82M model and voices | Snapshot used locally: `f3ff3571791e39611d31c381e3a41a3af07b4987`, declared Apache-2.0 | https://huggingface.co/hexgrad/Kokoro-82M/blob/f3ff3571791e39611d31c381e3a41a3af07b4987/README.md |
| Misaki | 0.9.4 / Apache-2.0 | https://github.com/hexgrad/misaki |
| phonemizer-fork | 3.3.2 / GPL-3.0-or-later | https://pypi.org/project/phonemizer-fork/3.3.2/ |
| espeakng-loader wrapper | 0.2.4 / MIT | https://github.com/thewh1teagle/espeakng-loader |
| eSpeak NG native library and data | Reports 1.52.0 / GPL-3.0-or-later | https://github.com/espeak-ng/espeak-ng/tree/4870adfa25b1a32b4361592f1be8a40337c58d6c |
| num2words | 0.5.14 / LGPL | https://github.com/savoirfairelinux/num2words |
| spaCy English model | 3.8.0 / model MIT, with source notices | https://github.com/explosion/spacy-models |

## Native eSpeak provenance

The MIT license of `espeakng-loader` applies to its loader code; it does not
replace the native eSpeak NG library's GPL license. The loader's 0.2.4 source
revision is `146599e29be31bf17d99f0bcb7dbb2f92aef3d95`. Its upstream workflow builds
eSpeak NG 1.52.0. The wrapper MIT text was added in later revision
`0ddc87adf77e5850d7eeb542ac8a87d421b64daa`. The installed native library does not
embed an exact source revision; mapping it to the eSpeak tag is supported by
its reported runtime version and the loader workflow, not a reproducible-build
proof of the exact binary.

### Source and build references

- Loader workflow: https://github.com/thewh1teagle/espeakng-loader/blob/146599e29be31bf17d99f0bcb7dbb2f92aef3d95/.github/workflows/build.yml
- Loader native build script: https://github.com/thewh1teagle/espeakng-loader/blob/146599e29be31bf17d99f0bcb7dbb2f92aef3d95/build.sh
- eSpeak source archive: https://github.com/espeak-ng/espeak-ng/archive/4870adfa25b1a32b4361592f1be8a40337c58d6c.tar.gz

## Before distributing binaries

Before public distribution, verify exact sources and build scripts for the
distributed binaries, retain all applicable dependency notices, and provide the
required corresponding-source access using an applicable license mechanism.
Include this engine's own source and build instructions, and document any changes.
A set of upstream links alone is not a claim that corresponding-source duties
are satisfied. The precise source of the forked phonemizer distribution and
native build provenance still need confirmation against the final binaries.

The installed dependency metadata contains additional licenses for Python,
PyTorch and its native dependencies, Transformers, spaCy, NumPy and other
packages. The model card contains training-data acknowledgements. Packaging
must preserve the notices relevant to the actual shipped files; this table is
not a replacement for that inventory. The OCR/Tesseract bundle belongs to the
reader application's separate packaging review and is not included in this engine.

## Source origin

Initial source snapshot: the `speech_engine/` component and independent
`build/build_speech_engine.py` recipe at source revision `1af5baa3c7241dbf7970ebd96f46039f7a4502b1`.

This repository starts with fresh history. Reader UI, OCR, website, signing
material, virtual environments, model files and binary build output were not
copied. Existing GPL-3.0-or-later source licensing and supplemental notices
were preserved. Importing the source does not change dependency licenses.

The initial standalone adaptation adjusts documentation and the build recipe
to use this repository root, adds Git exclusions, and aligns the package's
reported version with its existing `0.2.0` project metadata. Synthesis and API
implementation are unchanged.

[Back to README](../README.md)

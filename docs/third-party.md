# Dependencies

The engine source is [GPL-3.0-or-later](../LICENSE). Dependency versions are
pinned in [requirements.txt](../requirements.txt). Their licenses and source
references are listed below; supplemental texts are in [notices/](../notices/README.md).

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

## Native eSpeak source

The loader's 0.2.4 source revision is `146599e29be31bf17d99f0bcb7dbb2f92aef3d95`.
Its upstream workflow builds eSpeak NG 1.52.0. The loader's MIT license text
was added in revision `0ddc87adf77e5850d7eeb542ac8a87d421b64daa`.

The installed native DLL reports version 1.52.0 but does not embed an exact
source revision. The recorded eSpeak tag is based on that version and the
loader workflow; the exact binary-to-source mapping still needs confirmation.

- Loader workflow: https://github.com/thewh1teagle/espeakng-loader/blob/146599e29be31bf17d99f0bcb7dbb2f92aef3d95/.github/workflows/build.yml
- Loader native build script: https://github.com/thewh1teagle/espeakng-loader/blob/146599e29be31bf17d99f0bcb7dbb2f92aef3d95/build.sh
- eSpeak source archive: https://github.com/espeak-ng/espeak-ng/archive/4870adfa25b1a32b4361592f1be8a40337c58d6c.tar.gz

## Binary build records

Record the dependency versions, license texts, source archives and build scripts
used for each binary release. Keep the engine source and build recipe with the
package, and retain the notices from the installed dependency metadata.

Two source records remain to be confirmed against the shipped dependencies:

- The exact source of the `phonemizer-fork` distribution.
- The native eSpeak binary's source revision and build provenance.

The table above covers the main speech components. Python, PyTorch,
Transformers, spaCy, NumPy and their dependencies carry additional notices in
their distribution metadata. Model acknowledgements are in the model card.
Generated inventories and source archives belong in build output.

## Source history

The initial import came from the `speech_engine/` component and
`build/build_speech_engine.py` at revision
`1af5baa3c7241dbf7970ebd96f46039f7a4502b1`.

The import starts fresh Git history. Documentation and build paths were adapted
to this repository root, Git exclusions were added, and the reported version
was aligned with the existing `0.2.0` project metadata. Synthesis and API behavior
were retained.

[Back to README](../README.md)

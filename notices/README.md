# Supplemental speech generator notices

These license texts belong to the independent speech generator:

- `espeak-ng/COPYING`: the GPL version 3 text supplied with the native eSpeak NG runtime.
- `espeakng-loader/LICENSE`: the upstream MIT license for the Python loader code.

Versions, upstream revisions and native binary provenance are documented in
[THIRD_PARTY.md](../THIRD_PARTY.md). The build recipe accepts a `--notices` directory; include these
supplemental files with the speech executable. Preserve the dependency notices
in the Python distribution metadata as well.

Generated dependency inventories belong in each build's output directory.
This source folder contains only maintained supplemental notices; it is not an
inventory of a particular installed environment.

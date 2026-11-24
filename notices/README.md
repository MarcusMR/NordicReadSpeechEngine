# Supplemental dependency notices

| File | Covers |
| --- | --- |
| [espeak-ng/COPYING](espeak-ng/COPYING) | GPL version 3 text supplied with the native eSpeak NG runtime. |
| [espeakng-loader/LICENSE](espeakng-loader/LICENSE) | Upstream MIT license for the Python loader. |

Versions, upstream revisions and native binary provenance are recorded in the
[dependency notes](../docs/third-party.md).

Include these texts in the build's `--notices` directory and preserve relevant
dependency notices from Python distribution metadata. Generated environment
inventories belong in build output, separate from these maintained license
files.

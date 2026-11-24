# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the independent console speech program; never builds an installer."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


PROJECT = Path(__file__).resolve().parent


def source_files(source_root):
    """Keep the helper source distribution separate from the reader project."""
    allowed = {'.py', '.toml', '.txt', '.md'}
    for folder, directories, files in os.walk(source_root, followlinks=False):
        directories[:] = sorted(name for name in directories
                                if not name.startswith('.') and name not in ('vendor', 'artifacts', '__pycache__')
                                and not name.endswith('.egg-info'))
        for name in sorted(files):
            path = Path(folder) / name
            if not name.startswith('.') and (path.suffix.lower() in allowed or name in ('LICENSE', 'COPYING')):
                yield path, path.relative_to(source_root)


def command_for_engine(source_root, assets, distpath, workpath, specpath, notices, threads_runtime):
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onedir', '--console',
               '--name', 'NordicReadSpeechEngine', '--distpath', str(distpath),
               '--workpath', str(workpath), '--specpath', str(specpath),
               '--paths', str(source_root / 'src'), '--noupx',
               '--add-data', f'{assets};assets/kokoro',
               '--add-data', f'{notices};notices',
               '--add-data', f'{source_root / "LICENSE"};.',
               '--recursive-copy-metadata', 'kokoro', '--copy-metadata', 'en_core_web_sm',
               '--collect-data', 'language_tags',
               '--add-binary', f'{threads_runtime};.']
    for package in ('kokoro', 'misaki', 'spacy', 'en_core_web_sm', 'espeakng_loader',
                    'phonemizer', 'num2words', 'transformers'):
        command.extend(('--collect-all', package))
    for package in ('customtkinter', 'tkinter', 'nordicReadApp', 'tensorflow', 'matplotlib',
                    'pandas', 'scipy', 'IPython', 'pytest', 'torchaudio', 'torchvision'):
        command.extend(('--exclude-module', package))
    command.append(str(source_root / 'run.py'))
    return command


def build_engine(*, source_root, assets, distpath, workpath, specpath, notices, threads_runtime):
    source_root, assets = Path(source_root).resolve(), Path(assets).resolve()
    distpath, workpath, specpath = (Path(path).resolve() for path in (distpath, workpath, specpath))
    notices, threads_runtime = Path(notices).resolve(), Path(threads_runtime).resolve()
    for required in (source_root / 'run.py', source_root / 'LICENSE', assets / 'config.json',
                     assets / 'kokoro-v1_0.pth', Path(threads_runtime)):
        if not required.is_file():
            raise RuntimeError(f'Speech engine build input is missing: {required}')
    command = command_for_engine(source_root, assets, distpath, workpath, specpath, notices, threads_runtime)
    subprocess.run(command, cwd=source_root, check=True)
    output = Path(distpath) / 'NordicReadSpeechEngine'
    if not (output / 'NordicReadSpeechEngine.exe').is_file() or not (output / '_internal').is_dir():
        raise RuntimeError('PyInstaller did not produce a complete independent speech engine.')
    source = output / 'source'
    source.mkdir()
    for path, relative in source_files(source_root):
        destination = source / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
    shutil.copy2(Path(__file__), source / 'build_speech_engine.py')
    shutil.copy2(source_root / 'LICENSE', output / 'LICENSE')
    # Include source, license and build-record locations with the executable.
    (output / 'DISTRIBUTION-REVIEW.txt').write_text(
        'Speech engine source and build recipe: source/.\n'
        'Engine license: LICENSE (GPL-3.0-or-later).\n'
        'Dependency notices: _internal/notices/.\n'
        'Source and native build records: source/docs/third-party.md.\n', encoding='utf-8')
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=PROJECT)
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--distpath', type=Path, required=True)
    parser.add_argument('--workpath', type=Path, required=True)
    parser.add_argument('--specpath', type=Path, required=True)
    parser.add_argument('--notices', type=Path, required=True)
    parser.add_argument('--threads-runtime', type=Path, required=True)
    args = parser.parse_args()
    print(build_engine(**vars(args)))


if __name__ == '__main__':
    main()

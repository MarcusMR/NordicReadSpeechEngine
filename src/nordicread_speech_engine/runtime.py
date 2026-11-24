# SPDX-License-Identifier: GPL-3.0-or-later
"""Kokoro and pronunciation generate PCM; the caller owns playback."""

from pathlib import Path
import os
import re
import sys

from .catalog import VOICES


def cached_assets(cache):
    """Reuse a complete model snapshot without a Hugging Face network probe."""
    if cache is None:
        return None
    root = Path(cache) / 'hub' / 'models--hexgrad--Kokoro-82M'
    try:
        revision = (root / 'refs' / 'main').read_text(encoding='utf-8').strip()
        if not re.fullmatch(r'[0-9a-f]{40,64}', revision):
            return None
        snapshot = root / 'snapshots' / revision
        required = ('config.json', 'kokoro-v1_0.pth', 'voices/af_heart.pt')
        if all((snapshot / name).is_file() and (snapshot / name).stat().st_size for name in required):
            return snapshot
    except OSError:
        pass
    return None


def text_parts(text):
    """Start with a small segment, then increase the amount generated ahead."""
    words = re.findall(r'\S+', text)
    index, target = 0, 90
    while index < len(words):
        end, length = index, 0
        while end < len(words) and (end == index or length + len(words[end]) + 1 <= target):
            length += len(words[end]) + 1
            end += 1
            if length >= target // 2 and re.search(r'[.!?;:,]["\')\]]*$', words[end - 1]):
                break
        yield ' '.join(words[index:end])
        index, target = end, min(target * 2, 360)


def bounded_parts(pipeline, text, cancelled):
    """Avoid upstream truncation when a long token expands past 510 phonemes."""
    if cancelled.is_set():
        return
    phonemes, _ = pipeline.g2p(text)
    if len(phonemes or '') <= 510:
        yield text
        return
    if len(text) < 2:
        raise RuntimeError('A character exceeds the pronunciation model limit.')
    middle = len(text) // 2
    boundaries = [match.start() for match in re.finditer(r'\s+', text)
                  if 0 < match.start() < len(text)]
    boundary = min(boundaries, key=lambda index: abs(index - middle)) if boundaries else middle
    for part in (text[:boundary].strip(), text[boundary:].strip()):
        if part:
            yield from bounded_parts(pipeline, part, cancelled)


class Runtime:
    def __init__(self, *, assets=None, cache=None, offline=False):
        cache = Path(cache or os.environ.get('HF_HOME', Path.home() / '.cache' / 'huggingface'))
        if cache:
            os.environ['HF_HOME'] = str(cache)
        if offline:
            os.environ['HF_HUB_OFFLINE'] = '1'
            os.environ['TRANSFORMERS_OFFLINE'] = '1'
            import socket
            original_connect = socket.socket.connect
            def connect(sock, address):
                if sock.family in (socket.AF_INET, socket.AF_INET6):
                    raise RuntimeError('Network access is disabled in offline mode.')
                return original_connect(sock, address)
            socket.socket.connect = connect
        # The CLI redirects dependency diagnostics to stderr, away from API traffic.
        from kokoro import KModel, KPipeline
        import torch
        self.torch = torch
        self.pipeline_type = KPipeline
        self.assets = Path(assets) if assets else cached_assets(cache)
        if self.assets is None:
            if getattr(sys, 'frozen', False):
                raise RuntimeError('The speech engine model directory is missing.')
            from huggingface_hub import snapshot_download
            self.assets = Path(snapshot_download(repo_id='hexgrad/Kokoro-82M',
                allow_patterns=['config.json', 'kokoro-v1_0.pth', 'voices/af_heart.pt'],
                cache_dir=str(cache / 'hub'), local_files_only=offline))
        for name in ('config.json', 'kokoro-v1_0.pth'):
            if not (self.assets / name).is_file():
                raise RuntimeError('The speech engine asset is missing: ' + name)
        self.model = KModel(repo_id='hexgrad/Kokoro-82M', config=str(self.assets / 'config.json'),
                            model=str(self.assets / 'kokoro-v1_0.pth')).to('cpu').eval()
        self.pipelines = {}
        self.pipeline('af_heart')

    def pipeline(self, voice):
        if voice not in VOICES:
            raise ValueError('Unknown English voice: ' + str(voice))
        accent = voice[0]
        pipeline = self.pipelines.get(accent)
        if pipeline is None:
            pipeline = self.pipeline_type(lang_code=accent, repo_id='hexgrad/Kokoro-82M', model=self.model)
            if getattr(pipeline.g2p, 'fallback', None) is None:
                raise RuntimeError('The eSpeak English pronunciation fallback could not initialize.')
            self.pipelines[accent] = pipeline
        if voice not in pipeline.voices:
            local = self.assets / 'voices' / f'{voice}.pt'
            if not local.is_file():
                local = self.assets / f'{voice}.pt'
            if local.is_file():
                pipeline.voices[voice] = self.torch.load(local, weights_only=True)
            elif getattr(sys, 'frozen', False):
                raise RuntimeError('The bundled speech voice is missing: ' + voice)
            else:
                pipeline.load_voice(voice)
        return pipeline

    def synthesize(self, request, cancelled, speed):
        """Yield signed 16-bit little-endian mono PCM at 24 kHz, as produced."""
        import numpy as np
        pipeline = self.pipeline(request['voice'])
        produced = False
        for segment in text_parts(request['text']):
            for part in bounded_parts(pipeline, segment, cancelled):
                if cancelled.is_set():
                    return
                for _, _, audio in pipeline(part, voice=request['voice'], speed=lambda _: speed()):
                    if cancelled.is_set():
                        return
                    if audio is None:
                        continue
                    audio = np.asarray(audio)
                    if not audio.size:
                        continue
                    if audio.ndim != 1 or not np.isfinite(audio).all():
                        raise RuntimeError('The speech model produced invalid audio.')
                    produced = True
                    yield (np.clip(audio, -1, 1) * 32767).astype('<i2').tobytes()
        if not produced and not cancelled.is_set():
            raise RuntimeError('Kokoro produced no audio for this text.')

    def close(self):
        self.pipelines.clear()
        self.model = None

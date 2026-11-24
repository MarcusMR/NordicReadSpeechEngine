"""Standalone protocol regression tests; no models, audio devices or downloads."""

from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE / 'src'))

from nordicread_speech_engine.catalog import VOICES
from nordicread_speech_engine.runtime import Runtime, bounded_parts, cached_assets, text_parts
from nordicread_speech_engine.server import speech_request


class RuntimePreparationTests(unittest.TestCase):
    def fixture_runtime(self, blocks):
        class Pipeline:
            def g2p(self, text): return 'abc', []
            def __call__(self, text, **kwargs):
                for audio in blocks:
                    yield text, 'abc', audio
        runtime = object.__new__(Runtime)
        runtime.pipeline = lambda voice: Pipeline()
        return runtime

    def test_synthesis_yields_pcm16_without_opening_an_audio_device(self):
        import numpy as np
        runtime = self.fixture_runtime([np.array([-1., 0., 1.])])
        with patch('ctypes.WinDLL', create=True) as device:
            frames = list(runtime.synthesize({'voice': 'af_heart', 'text': 'standalone'}, threading.Event(), lambda: 1))
        self.assertEqual(frames, [b'\x01\x80\x00\x00\xff\x7f'])
        device.assert_not_called()

    def test_synthesis_cancellation_and_empty_or_invalid_audio(self):
        import numpy as np
        cancelled = threading.Event()
        runtime = self.fixture_runtime([np.ones(10), np.ones(10)])
        chunks = runtime.synthesize({'voice': 'af_heart', 'text': 'Text'}, cancelled, lambda: 1)
        self.assertEqual(len(next(chunks)), 20)
        cancelled.set()
        self.assertEqual(list(chunks), [])
        for blocks in ([], [np.array([float('nan')])], [np.ones((2, 3))]):
            with self.subTest(blocks=str(blocks)), self.assertRaises(RuntimeError):
                list(self.fixture_runtime(blocks).synthesize({'voice': 'af_heart', 'text': 'Text'}, threading.Event(), lambda: 1))

    def test_runtime_uses_upstream_pipeline_and_requires_its_espeak_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            assets = Path(temporary)
            for name in ('config.json', 'kokoro-v1_0.pth', 'af_heart.pt'):
                (assets / name).write_bytes(b'fixture')
            model = Mock()
            model.to.return_value = model
            model.eval.return_value = model
            upstream = Mock(return_value=SimpleNamespace(
                g2p=SimpleNamespace(fallback=object()), voices={}))
            modules = {'kokoro': SimpleNamespace(KModel=Mock(return_value=model), KPipeline=upstream),
                       'torch': SimpleNamespace(load=Mock(return_value='weights'))}
            with patch.dict(sys.modules, modules):
                runtime = Runtime(assets=assets)
                upstream.assert_called_once_with(lang_code='a', repo_id='hexgrad/Kokoro-82M', model=model)
                self.assertEqual(runtime.pipeline('af_heart').voices['af_heart'], 'weights')
                runtime.close()
                upstream.return_value = SimpleNamespace(g2p=SimpleNamespace(fallback=None), voices={})
                with self.assertRaisesRegex(RuntimeError, 'eSpeak English pronunciation fallback'):
                    Runtime(assets=assets)

    def test_complete_cache_is_reused_and_incomplete_cache_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary)
            model = cache / 'hub' / 'models--hexgrad--Kokoro-82M'
            (model / 'refs').mkdir(parents=True)
            (model / 'refs' / 'main').write_text('a' * 40)
            snapshot = model / 'snapshots' / ('a' * 40)
            for name in ('config.json', 'kokoro-v1_0.pth', 'voices/af_heart.pt'):
                path = snapshot / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'fixture')
            self.assertEqual(cached_assets(cache), snapshot)
            (snapshot / 'config.json').unlink()
            self.assertIsNone(cached_assets(cache))

    def test_long_expanded_tokens_are_split_without_losing_input(self):
        pipeline = Mock(g2p=lambda text: ('p' * len(text) * 8, []))
        text = 'xqzvortle' * 300
        parts = list(bounded_parts(pipeline, text, threading.Event()))
        self.assertEqual(''.join(parts), text)
        self.assertTrue(all(len(pipeline.g2p(part)[0]) <= 510 for part in parts))
        cancelled = threading.Event()
        cancelled.set()
        self.assertEqual(list(bounded_parts(pipeline, text, cancelled)), [])

    def test_text_segments_preserve_words_and_start_small(self):
        text = ' '.join(f'word{index}' for index in range(100))
        parts = list(text_parts(text))
        self.assertEqual(' '.join(parts), text)
        self.assertLessEqual(len(parts[0]), 90)
        self.assertGreater(len(parts[1]), len(parts[0]))

    def test_public_catalog_contains_only_both_english_accents(self):
        self.assertEqual(len(VOICES), 28)
        self.assertEqual({voice[0] for voice in VOICES}, {'a', 'b'})


if __name__ == '__main__':
    unittest.main()

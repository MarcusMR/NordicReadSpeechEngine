"""Real TLS connections with a controlled runtime; no model downloads."""

import http.client
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE / 'src'))
from nordicread_speech_engine.server import serve, tls_context


class FakeRuntime:
    def __init__(self):
        self.started, self.release = threading.Event(), threading.Event()
        self.closed = False
        self.rates = []

    def synthesize(self, request, cancelled, speed):
        self.started.set()
        yield b'\x00\x20' * 2400
        if request['text'] == 'wait':
            if not cancelled.wait(3):
                raise AssertionError('Stop did not reach synthesis')
        if request['text'] == 'speed':
            if not self.release.wait(3):
                raise AssertionError('Speed gate not released')
            self.rates.append(speed())
        if request['text'] == 'fail':
            raise RuntimeError('Synthesis failed')
        if request['text'] == 'many':
            for _ in range(10000):
                if cancelled.is_set():
                    return
                yield b'\x00\x20' * 2400
        yield b'\x00\x10' * 2400

    def close(self):
        self.closed = True


class HTTPSTests(unittest.TestCase):
    def launch(self, *, fail=False, ready=True):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.folder = Path(directory.name)
        self.readers = []
        self.gate, self.warming = threading.Event(), threading.Event()
        self.runtime = FakeRuntime()
        def factory():
            self.warming.set()
            if not self.gate.wait(4):
                raise AssertionError('Controlled readiness was not released')
            if fail:
                raise RuntimeError('Model missing')
            return self.runtime
        self.thread = threading.Thread(target=serve, args=(self.folder, factory), daemon=True)
        self.thread.start()
        self.wait_for(lambda: (self.folder / 'session.json').is_file())
        self.session = json.loads((self.folder / 'session.json').read_text())
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.context.load_verify_locations(cadata=self.session['certificate'])
        self.addCleanup(self.finish)
        self.assertTrue(self.warming.wait(3))
        if ready:
            self.gate.set()
            self.wait_for(lambda: self.call('GET', '/v1/health')[1]['status'] != 'starting')

    def wait_for(self, condition):
        deadline = time.monotonic() + 4
        while not condition():
            if time.monotonic() > deadline:
                self.fail('Controlled HTTPS signal did not arrive')
            threading.Event().wait(.01)

    def call(self, method, path, body=None, *, token=None, context=None, headers=None, raw=None, consume=True):
        connection = http.client.HTTPSConnection('127.0.0.1', self.session['port'],
                                                context=context or self.context, timeout=3)
        try:
            values = {'Authorization': 'Bearer ' + (self.session['token'] if token is None else token),
                      'Content-Type': 'application/json'}
            values.update(headers or {})
            data = raw if raw is not None else json.dumps(body) if body is not None else None
            connection.request(method, path, data, values)
            response = connection.getresponse()
            result = json.loads(response.read())
            if path == '/v1/speech' and response.status == 202 and consume:
                self.consume(result['id'])
            return response.status, result
        finally:
            connection.close()

    def consume(self, identifier):
        def read():
            connection = http.client.HTTPSConnection('127.0.0.1', self.session['port'], context=self.context, timeout=4)
            try:
                connection.request('GET', f'/v1/jobs/{identifier}/audio', headers={'Authorization': 'Bearer ' + self.session['token']})
                response = connection.getresponse()
                response.read()
            except (OSError, http.client.HTTPException):
                pass  # Synthesis-error streams deliberately terminate early.
            finally:
                connection.close()
        thread = threading.Thread(target=read, daemon=True)
        self.readers.append(thread)
        thread.start()

    def finish(self):
        self.gate.set()
        self.runtime.release.set()
        if self.thread.is_alive():
            try:
                self.call('POST', '/v1/shutdown', {})
            except (OSError, http.client.HTTPException):
                pass
            self.thread.join(4)
        self.assertFalse(self.thread.is_alive())
        for reader in self.readers: reader.join(4)

    def done(self, identifier):
        self.wait_for(lambda: self.call('GET', '/v1/jobs/' + str(identifier))[1]['status']
                      in ('completed', 'cancelled', 'failed'))
        return self.call('GET', '/v1/jobs/' + str(identifier))[1]

    def test_health_during_controlled_readiness_and_same_service_after_ready(self):
        self.launch(ready=False)
        status, health = self.call('GET', '/v1/health')
        self.assertEqual((status, health['status'], health['protocol']), (200, 'starting', 3))
        self.assertEqual(len(health['voices']), 28)
        self.gate.set()
        self.wait_for(lambda: self.call('GET', '/v1/health')[1]['status'] == 'ready')
        status, job = self.call('POST', '/v1/speech', {'text': 'Hello', 'voice': 'bf_emma'})
        self.assertEqual(status, 202)
        self.assertEqual(self.done(job['id'])['code'], 0)

    def test_authentication_browser_rejection_and_certificate_verification(self):
        self.launch()
        self.assertEqual(self.session['host'], '127.0.0.1')
        self.assertEqual(self.call('GET', '/v1/health', token='wrong')[0], 401)
        self.assertEqual(self.call('POST', '/v1/shutdown', {}, headers={'Origin': 'https://example.com'})[0], 403)
        with self.assertRaises(ssl.SSLCertVerificationError):
            self.call('GET', '/v1/health', context=ssl.create_default_context())
        with tempfile.TemporaryDirectory() as other:
            _, pem = tls_context(Path(other))
            wrong = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            wrong.load_verify_locations(cadata=pem)
            with self.assertRaises(ssl.SSLCertVerificationError):
                self.call('GET', '/v1/health', context=wrong)
        self.assertFalse((self.folder / 'server.key').exists())
        self.assertFalse((self.folder / 'server.pem').exists())
        self.assertNotIn(self.session['token'], self.session['certificate'])

    def test_idle_plaintext_socket_does_not_block_authenticated_health_or_stop(self):
        self.launch()
        with socket.create_connection(('127.0.0.1', self.session['port']), timeout=2):
            self.assertEqual(self.call('GET', '/v1/health')[0], 200)
            self.assertEqual(self.call('POST', '/v1/stop', {})[0], 200)

    def test_invalid_json_routes_voice_size_and_speed_do_not_break_next_request(self):
        self.launch()
        for message in ([], {'text': 'Hi', 'voice': 'if_sara'}, {'text': 'Hi', 'voice': []},
                        {'text': 'Hi', 'voice': {}}, {'text': 'Hi', 'voice': None},
                        {'text': 'Hi', 'speed': True},
                        {'text': 'Hi', 'speed': float('nan')}, {'text': 'Hi', 'id': '../private'},
                        {'text': 'x' * 100001}):
            self.assertEqual(self.call('POST', '/v1/speech', message)[0], 400)
        self.assertEqual(self.call('POST', '/v1/speech', raw='broken')[0], 400)
        self.assertEqual(self.call('POST', '/v1/speech', {}, headers={'Content-Length': '1000001'})[0], 413)
        self.assertEqual(self.call('GET', '/unknown')[0], 404)
        self.assertEqual(self.call('GET', '/v1/jobs/missing')[0], 404)
        self.call('POST', '/v1/speech', {'text': 'Next', 'id': 'valid'})
        self.assertEqual(self.done('valid')['code'], 0)

    def test_stop_and_live_speed_and_failed_request_preserve_model(self):
        self.launch()
        self.call('POST', '/v1/speech', {'text': 'wait', 'id': 1})
        self.assertTrue(self.runtime.started.wait(2))
        self.call('POST', '/v1/jobs/1/stop', {})
        self.assertTrue(self.done(1)['cancelled'])
        self.runtime.started.clear()
        self.call('POST', '/v1/speech', {'text': 'speed', 'id': 2})
        self.assertTrue(self.runtime.started.wait(2))
        self.call('PATCH', '/v1/jobs/2', {'speed': 1.7})
        self.runtime.release.set()
        self.assertEqual(self.done(2)['code'], 0)
        self.assertEqual(self.runtime.rates, [1.7])
        self.call('POST', '/v1/speech', {'text': 'fail', 'id': 3})
        self.assertEqual(self.done(3)['message'], 'Synthesis failed')
        self.call('POST', '/v1/speech', {'text': 'Next', 'id': 4})
        self.assertEqual(self.done(4)['code'], 0)

    def test_shutdown_during_warmup_cancels_and_removes_descriptor(self):
        self.launch(ready=False)
        self.assertEqual(self.call('POST', '/v1/shutdown', {})[1]['status'], 'closing')
        self.gate.set()
        self.thread.join(3)
        self.assertFalse(self.thread.is_alive())
        self.assertTrue(self.runtime.closed)
        self.assertFalse((self.folder / 'session.json').exists())

    def test_model_startup_error_is_available_through_health(self):
        self.launch(fail=True)
        self.assertEqual(self.call('GET', '/v1/health')[1]['message'], 'Model missing')

    def stream(self, identifier):
        connection = http.client.HTTPSConnection('127.0.0.1', self.session['port'], context=self.context, timeout=3)
        self.addCleanup(connection.close)
        connection.request('GET', f'/v1/jobs/{identifier}/audio', headers={'Authorization': 'Bearer ' + self.session['token']})
        response = connection.getresponse()
        self.addCleanup(response.close)
        return connection, response

    def test_first_audio_is_delivered_before_generation_finishes(self):
        self.launch()
        self.call('POST', '/v1/speech', {'text': 'speed', 'id': 'stream'}, consume=False)
        _, response = self.stream('stream')
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader('Transfer-Encoding'), 'chunked')
        self.assertEqual(response.getheader('X-Audio-Format'), 'pcm_s16le')
        first = response.read1(4800)
        self.assertTrue(first, 'The server buffered the entire utterance instead of streaming')
        self.assertEqual(self.call('GET', '/v1/jobs/stream')[1]['status'], 'running')
        self.assertFalse(self.runtime.release.is_set())
        self.assertEqual(self.call('GET', '/v1/jobs/stream/audio', token='wrong')[0], 401)
        self.assertEqual(self.call('GET', '/v1/jobs/stream/audio')[0], 400)
        self.runtime.release.set()
        audio = first + response.read()
        self.assertEqual(audio, b'\x00\x20' * 2400 + b'\x00\x10' * 2400)
        self.assertEqual(self.done('stream')['code'], 0)

    def test_synthesis_error_truncates_stream_and_reports_failed_job(self):
        self.launch()
        self.call('POST', '/v1/speech', {'text': 'fail', 'id': 'broken'}, consume=False)
        _, response = self.stream('broken')
        self.assertEqual(response.status, 200)
        with self.assertRaises(http.client.IncompleteRead):
            response.read()
        self.assertEqual(self.done('broken')['code'], 1)

    def test_disconnected_consumer_cancels_generation_and_next_job_works(self):
        self.launch()
        self.call('POST', '/v1/speech', {'text': 'many', 'id': 'disconnect'}, consume=False)
        connection, response = self.stream('disconnect')
        self.assertTrue(response.read1(4800))
        response.close()
        connection.close()
        self.assertTrue(self.done('disconnect')['cancelled'])
        self.call('POST', '/v1/speech', {'text': 'Next', 'id': 'next'})
        self.assertEqual(self.done('next')['code'], 0)

    def test_bounded_audio_queue_releases_a_blocked_producer_on_stop(self):
        from nordicread_speech_engine.server import SpeechState
        state = SpeechState(lambda: self.runtime)
        self.runtime = FakeRuntime()
        state.worker.start()
        self.addCleanup(state.worker.join, 2)
        self.addCleanup(state.close)
        state.submit({'text': 'many', 'id': 'bounded'})
        job = state.claim_audio('bounded')
        self.wait_for(job['audio'].full)
        self.assertEqual(job['audio'].qsize(), 8)
        state.stop('bounded')
        self.assertTrue(job['finished'].wait(1))
        self.assertTrue(state.result('bounded')['cancelled'])

    def test_help_and_voice_listing_need_no_server_or_model(self):
        with tempfile.TemporaryDirectory() as directory:
            for arguments in (['--help'], ['--list-voices']):
                result = subprocess.run([sys.executable, str(ENGINE / 'run.py'), *arguments],
                                        cwd=directory, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                if arguments == ['--list-voices']:
                    self.assertEqual(len(json.loads(result.stdout)['voices']), 28)

    def test_independent_example_saves_stream_without_reader_imports(self):
        import wave
        self.launch()
        target = self.folder / 'example.wav'
        result = subprocess.run([sys.executable, str(ENGINE / 'examples/stream_to_wav.py'),
            '--session-dir', str(self.folder), '--text', 'Independent client', '--output', str(target)],
            cwd=self.folder, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        with wave.open(str(target), 'rb') as audio:
            self.assertEqual((audio.getnchannels(), audio.getsampwidth(), audio.getframerate()), (1, 2, 24000))
            self.assertEqual(audio.getnframes(), 4800)


if __name__ == '__main__':
    unittest.main()

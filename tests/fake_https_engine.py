"""Controlled child-process fixture. No models, downloads or audio devices."""

import argparse
import json
import os
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from nordicread_speech_engine import server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--session-dir', type=Path, required=True)
    parser.add_argument('--parent-pid', type=int)
    args = parser.parse_args()
    folder = Path(os.environ['FAKE_ENGINE_FOLDER'])
    mode = os.environ.get('FAKE_ENGINE_MODE', '')
    (folder / 'pid').write_text(str(os.getpid()))

    def log(message):
        with (folder / 'commands.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(message) + '\n')

    class Runtime:
        def __init__(self):
            while not (folder / 'ready-gate').exists():
                threading.Event().wait(.005)
            if mode == 'fatal':
                raise RuntimeError('Model unavailable')

        def synthesize(self, request, cancelled, speed):
            assert not any(name in sys.modules for name in ('nordicReadApp', 'torch', 'kokoro'))
            identifier, text = request['id'], request['text']
            if text == 'CRASH':
                os._exit(7)
            if text in ('ERROR', ''):
                raise RuntimeError('Synthesis failed')
            yield b'\x00\x20' * 2400
            if text in ('WAIT', 'SLOW'):
                (folder / ('started-' + str(identifier))).write_text('started')
                while not cancelled.is_set() and not (folder / 'release').exists():
                    cancelled.wait(.005)
            if not cancelled.is_set():
                yield b'\x00\x10' * 2400

        def close(self):
            (folder / 'runtime-closed').touch()

    original = server.SpeechState
    class State(original):
        def health(self):
            result = super().health()
            if result['status'] == 'ready' and mode == 'version':
                result['protocol'] = 999
            return result

        def submit(self, message):
            result = super().submit(message)
            log(dict(message, type='speak'))
            return result

        def speed(self, identifier, value):
            super().speed(identifier, value)
            (folder / ('speed-' + str(identifier))).write_text(str(value))
            log({'type': 'speed', 'id': identifier, 'speed': value})

        def result(self, identifier):
            result = super().result(identifier)
            if result['status'] == 'completed' and result['id'] == bad_id[0]:
                result['code'] = 'invalid'
            return result

    bad_id = [None]
    submit = State.submit
    def track_bad(self, message):
        if message['text'] == 'BAD_CODE':
            bad_id[0] = message['id']
        return submit(self, message)
    State.submit = track_bad
    server.SpeechState = State
    from nordicread_speech_engine import http_api
    from flask import request
    create = http_api.create_app
    def create_app(state, token):
        app = create(state, token)
        @app.after_request
        def malformed(response):
            if mode == 'malformed' and request.path == '/v1/health' and state.status == 'ready':
                response.set_data(b'Not JSON')
            return response
        return app
    http_api.create_app = create_app
    return server.serve(args.session_dir, Runtime, parent_pid=args.parent_pid)


if __name__ == '__main__':
    raise SystemExit(main())

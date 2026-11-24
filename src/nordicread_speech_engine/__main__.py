# SPDX-License-Identifier: GPL-3.0-or-later
"""Standalone speech application entry point."""

import argparse
from contextlib import redirect_stdout
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import wave


def main(argv=None):
    parser = argparse.ArgumentParser(description='Independent English Kokoro speech engine; authenticated local HTTPS API.')
    parser.add_argument('--https', action='store_true', help='Run the loopback HTTPS API (default)')
    parser.add_argument('--session-dir', type=Path, help='Private directory for the HTTPS session descriptor')
    parser.add_argument('--parent-pid', type=int, help='Exit if this owning process disappears')
    parser.add_argument('--assets', type=Path, help='Directory containing config, model and voice files')
    parser.add_argument('--cache-dir', type=Path, help='Hugging Face cache root for source use')
    parser.add_argument('--offline', action='store_true', help='Reject Internet connections and use cached assets only')
    parser.add_argument('--text', help='Generate a WAV file once and exit')
    parser.add_argument('--voice', default='af_heart', help='Voice for --text (default af_heart)')
    parser.add_argument('--speed', type=float, default=1, help='Speech rate for --text, from 0.5 to 2')
    parser.add_argument('--output', type=Path, help='Save the one-shot --text result as a PCM WAV')
    parser.add_argument('--list-voices', action='store_true', help='Print voice IDs without loading the model')
    args = parser.parse_args(argv)
    from .catalog import VOICES
    if args.list_voices:
        print(json.dumps({'type': 'voices', 'voices': list(VOICES)}))
        return 0
    if (args.output is None) != (args.text is None):
        parser.error('Use --text and --output together to generate a WAV file')
    if args.https and args.text is not None:
        parser.error('Choose --https or --text')
    from .server import serve, speech_request
    if args.text is not None:
        try:
            request = speech_request({'id': 'preview', 'text': args.text,
                                      'voice': args.voice, 'speed': args.speed}, 1)
        except ValueError as error:
            parser.error(str(error))
    assets = args.assets
    if assets is None and getattr(sys, 'frozen', False):
        assets = Path(sys._MEIPASS) / 'assets' / 'kokoro'
    # API traffic never uses stdin/stdout. The one-shot CLI prints its result.
    protocol_stdout = sys.stdout
    from .runtime import Runtime
    with redirect_stdout(sys.stderr):
        if args.text is None:
            if args.cache_dir:
                os.environ['HF_HOME'] = str(args.cache_dir)
            if args.offline:
                os.environ['HF_HUB_OFFLINE'] = '1'
                os.environ['TRANSFORMERS_OFFLINE'] = '1'
            session = args.session_dir or Path(tempfile.mkdtemp(prefix='nordicread-speech-'))
            if args.session_dir is None:
                print('HTTPS session descriptor: ' + str(session / 'session.json'), file=sys.stderr)
            try:
                return serve(session, lambda: Runtime(assets=assets, cache=args.cache_dir,
                    offline=args.offline),
                    parent_pid=args.parent_pid)
            finally:
                if args.session_dir is None:
                    session.rmdir()
        cancelled = threading.Event()
        runtime = None
        try:
            runtime = Runtime(assets=assets, cache=args.cache_dir, offline=args.offline)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            chunks = 0
            with wave.open(str(args.output), 'wb') as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(24000)
                for pcm in runtime.synthesize(request, cancelled, lambda: request['speed']):
                    output.writeframesraw(pcm)
                    chunks += 1
            result = {'type': 'done', 'id': 'preview', 'code': 0, 'message': '',
                      'cancelled': False, 'chunks': chunks}
            code = 0
        except KeyboardInterrupt:
            cancelled.set()
            result = {'type': 'done', 'id': 'preview', 'code': 0, 'message': '', 'cancelled': True}
            code = 130
        except Exception as error:
            result = {'type': 'error', 'fatal': True, 'message': str(error) or type(error).__name__}
            code = 1
        finally:
            if runtime is not None:
                runtime.close()
        protocol_stdout.write(json.dumps(result) + '\n')
        protocol_stdout.flush()
        return code


if __name__ == '__main__':
    raise SystemExit(main())

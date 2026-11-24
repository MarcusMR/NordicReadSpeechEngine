# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent example: consume local HTTPS PCM and save it to a WAV file."""

import argparse
import http.client
import json
from pathlib import Path
import ssl
import wave


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session-dir', type=Path, required=True)
    parser.add_argument('--text', required=True)
    parser.add_argument('--voice', default='af_heart')
    parser.add_argument('--speed', type=float, default=1)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    session = json.loads((args.session_dir / 'session.json').read_text(encoding='utf-8'))
    if session.get('protocol') != 3 or session.get('host') != '127.0.0.1':
        raise ValueError('Expected a local protocol 3 audio generator.')
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations(cadata=session['certificate'])
    headers = {'Authorization': 'Bearer ' + session['token'], 'Content-Type': 'application/json'}

    def request(method, path, body=None):
        connection = http.client.HTTPSConnection('127.0.0.1', session['port'], context=context, timeout=120)
        try:
            connection.request(method, path, None if body is None else json.dumps(body), headers)
            response = connection.getresponse()
            result = json.loads(response.read(1_000_000))
            if response.status not in (200, 202):
                raise RuntimeError(result.get('message', 'Speech request failed.'))
            return result
        finally:
            connection.close()

    health = request('GET', '/v1/health')
    if health['status'] != 'ready':
        raise RuntimeError('Wait for the generator to become ready before submitting audio.')
    job = request('POST', '/v1/speech', {'text': args.text, 'voice': args.voice, 'speed': args.speed})
    connection = http.client.HTTPSConnection('127.0.0.1', session['port'], context=context, timeout=120)
    try:
        connection.request('GET', f'/v1/jobs/{job["id"]}/audio', headers=headers)
        response = connection.getresponse()
        if response.status != 200 or response.getheader('X-Audio-Format') != 'pcm_s16le':
            raise RuntimeError('Expected a PCM16 audio stream.')
        if (response.getheader('X-Sample-Rate'), response.getheader('X-Channels'),
                response.getheader('X-Sample-Width')) != ('24000', '1', '2'):
            raise RuntimeError('Unsupported audio format.')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with wave.open(str(args.output), 'wb') as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(24000)
            pending = b''
            while block := response.read1(4800):
                pending += block
                length = len(pending) // 2 * 2
                output.writeframesraw(pending[:length])
                count += length
                pending = pending[length:]
            if pending or not count:
                raise RuntimeError('Incomplete or empty PCM audio stream.')
        result = request('GET', f'/v1/jobs/{job["id"]}')
        if result.get('code') != 0 or result.get('cancelled'):
            raise RuntimeError(result.get('message') or 'Audio generation did not complete.')
        print(f'Saved {count // 2} PCM samples to {args.output}')
    except BaseException:
        try:
            request('POST', f'/v1/jobs/{job["id"]}/stop', {})
        except Exception:
            pass  # Keep the original stream error if the generator has exited.
        raise
    finally:
        connection.close()


if __name__ == '__main__':
    main()

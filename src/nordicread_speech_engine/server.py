# SPDX-License-Identifier: GPL-3.0-or-later
"""Authenticated loopback HTTPS API; no UI modules or speech dependencies."""

from collections import OrderedDict
from datetime import datetime, timedelta, timezone
import ipaddress
import json
import math
import os
from pathlib import Path
from queue import Empty, Full, Queue
import re
import secrets
import ssl
import time
import threading

from .catalog import VOICES

PROTOCOL = 3
PCM_BLOCK = 4800


def speech_request(message, next_id):
    identifier = message.get('id', next_id)
    if type(identifier) not in (str, int) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', str(identifier)):
        raise ValueError('id must contain 1-64 letters, digits, underscores or hyphens.')
    text = message.get('text')
    if not isinstance(text, str) or len(text) > 100_000:
        raise ValueError('text must be a string of at most 100000 characters.')
    voice = message.get('voice', 'af_heart')
    if not isinstance(voice, str) or voice not in VOICES:
        raise ValueError('Unknown English voice.')
    return {'id': identifier, 'text': text, 'voice': voice, 'speed': speed_value(message.get('speed', 1))}


def speed_value(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0.5 <= value <= 2:
        raise ValueError('speed must be a finite number from 0.5 to 2.')
    return float(value)


class SpeechState:
    """One reusable generator; bounded PCM queues and independent controls."""
    def __init__(self, runtime_factory):
        self.runtime_factory = runtime_factory
        self.closing = threading.Event()
        self.lock = threading.RLock()
        self.requests = Queue(maxsize=64)
        self.jobs = OrderedDict()
        self.status, self.error = 'starting', ''
        self.worker = threading.Thread(target=self._work, name='speech-model', daemon=True)

    def health(self):
        with self.lock:
            return {'protocol': PROTOCOL, 'status': self.status, 'message': self.error,
                    'engine': 'nordicread-speech-engine', 'voices': list(VOICES),
                    'audio': {'format': 'pcm_s16le', 'sample_rate': 24000, 'channels': 1}}

    def submit(self, message):
        with self.lock:
            if self.status in ('failed', 'closing'):
                raise ValueError(self.error or 'Speech engine is closing.')
            request = speech_request(message, secrets.token_hex(12))
            key = str(request['id'])
            if key in self.jobs:
                raise ValueError('Request id is already in use.')
            # Bound completed results too; never retain completed input text.
            if len(self.jobs) >= 256:
                for old, job in list(self.jobs.items()):
                    if job['result']['status'] in ('completed', 'cancelled', 'failed'):
                        self.jobs.pop(old)
                        break
                else:
                    raise ValueError('Speech queue is full.')
            job = {'request': request, 'cancelled': threading.Event(),
                   'attached': threading.Event(), 'finished': threading.Event(),
                   'audio': Queue(maxsize=8), 'claimed': False,
                   'result': {'id': request['id'], 'status': 'queued'}}
            self.jobs[key] = job
            try:
                self.requests.put_nowait(job)
            except Full:
                self.jobs.pop(key)
                raise ValueError('Speech queue is full.') from None
            return dict(job['result'], audio_url=f'/v1/jobs/{key}/audio')

    def claim_audio(self, identifier):
        with self.lock:
            job = self.jobs[identifier]
            if job['claimed']:
                raise ValueError('This audio stream has already been opened.')
            job['claimed'] = True
            job['attached'].set()
            return job

    def audio_chunks(self, job):
        try:
            while not self.closing.is_set() and not job['cancelled'].is_set():
                try:
                    yield job['audio'].get(timeout=.05)
                except Empty:
                    if job['finished'].is_set():
                        if job['result']['code']:
                            # Do not terminate a failed stream as if it were a
                            # successful complete HTTP body. The client checks
                            # both transport completion and the JSON job result.
                            raise RuntimeError('Audio generation failed.')
                        return
        finally:
            job['cancelled'].set()

    def _publish(self, job, pcm):
        if not isinstance(pcm, bytes) or len(pcm) % 2:
            raise ValueError('The generator returned invalid PCM samples.')
        for start in range(0, len(pcm), PCM_BLOCK):
            while not job['cancelled'].is_set() and not self.closing.is_set():
                try:
                    job['audio'].put(pcm[start:start + PCM_BLOCK], timeout=.05)
                    break
                except Full:
                    continue
            else:
                return

    def result(self, identifier):
        with self.lock:
            return dict(self.jobs[identifier]['result'])

    def stop(self, identifier=None):
        with self.lock:
            jobs = [self.jobs[identifier]] if identifier is not None else list(self.jobs.values())
            for job in jobs:
                job['cancelled'].set()

    def speed(self, identifier, value):
        rate = speed_value(value)
        with self.lock:
            request = self.jobs[identifier]['request']
            if request is not None:
                request['speed'] = rate

    def close(self):
        with self.lock:
            self.closing.set()
            self.status = 'closing'
            self.stop()

    def _work(self):
        runtime = None
        try:
            runtime = self.runtime_factory()
            with self.lock:
                if self.closing.is_set():
                    return
                self.status = 'ready'
            while not self.closing.is_set():
                try:
                    job = self.requests.get(timeout=.1)
                except Empty:
                    continue
                request, cancelled = job['request'], job['cancelled']
                code, message, chunks = 0, '', 0
                with self.lock:
                    job['result']['status'] = 'running'
                try:
                    deadline = time.monotonic() + 10
                    while not job['attached'].wait(.05):
                        if cancelled.is_set() or self.closing.is_set():
                            break
                        if time.monotonic() > deadline:
                            raise RuntimeError('The audio stream was not opened within 10 seconds.')
                    if not cancelled.is_set():
                        for pcm in runtime.synthesize(request, cancelled, lambda: request['speed']):
                            if cancelled.is_set() or self.closing.is_set():
                                break
                            self._publish(job, pcm)
                            chunks += 1
                except Exception as error:
                    code, message = 1, str(error) or type(error).__name__
                with self.lock:
                    job['request'] = None
                    job['result'] = {'id': request['id'], 'code': code, 'message': message,
                        'cancelled': cancelled.is_set(), 'chunks': chunks,
                        'status': 'failed' if code else 'cancelled' if cancelled.is_set() else 'completed'}
                    job['finished'].set()
        except Exception as error:
            with self.lock:
                if not self.closing.is_set():
                    self.status, self.error = 'failed', str(error) or type(error).__name__
        finally:
            if runtime is not None:
                runtime.close()


def tls_context(folder):
    """Fresh identity per launch, trusted only by the owning API client."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
    key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.now(timezone.utc)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'NordicRead local speech')])
    certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=30))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]), False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False)
        .sign(key, hashes.SHA256()))
    pem = certificate.public_bytes(serialization.Encoding.PEM)
    cert_path, key_path = folder / 'server.pem', folder / 'server.key'
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        for path, data in ((cert_path, pem), (key_path, key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))):
            with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
                stream.write(data)
        context.load_cert_chain(cert_path, key_path)
    finally:
        cert_path.unlink(missing_ok=True)
        key_path.unlink(missing_ok=True)
    return context, pem.decode('ascii')


def serve(session_dir, runtime_factory, *, parent_pid=None):
    """Publish an atomic private descriptor, then prepare the model off-thread."""
    folder = Path(session_dir).resolve()
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    context, pem = tls_context(folder)
    token = secrets.token_urlsafe(32)
    state = SpeechState(runtime_factory)
    from .http_api import create_app, LocalHTTPSServer
    server = LocalHTTPSServer(create_app(state, token), context)
    temporary, descriptor = folder / 'session.tmp', folder / 'session.json'
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .05}, daemon=True)
    try:
        with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', encoding='utf-8') as stream:
            json.dump({'protocol': PROTOCOL, 'host': '127.0.0.1', 'port': server.server_port,
                       'token': token, 'certificate': pem, 'pid': os.getpid()}, stream)
        os.replace(temporary, descriptor)
        thread.start()
        if parent_pid is not None:
            from .lifecycle import watch_parent
            watch_parent(parent_pid, state)
        state.worker.start()
        state.closing.wait()
        return 0
    except KeyboardInterrupt:
        return 130
    finally:
        state.close()
        if thread.is_alive():
            server.shutdown()
            thread.join(2)
        server.server_close()
        if state.worker.ident is not None:
            state.worker.join(1)
        descriptor.unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)

# SPDX-License-Identifier: GPL-3.0-or-later
"""Flask API for the local audio generator. No playback or reader imports."""

import hmac
import socket
import threading

from flask import Flask, Response, jsonify, request
from werkzeug.exceptions import HTTPException
from werkzeug.serving import ThreadedWSGIServer, WSGIRequestHandler


def create_app(state, token):
    app = Flask(__name__, static_folder=None)
    app.config['MAX_CONTENT_LENGTH'] = 1_000_000

    @app.before_request
    def authenticate():
        supplied = request.headers.get('Authorization', '').encode('utf-8')
        if not hmac.compare_digest(supplied, ('Bearer ' + token).encode('ascii')):
            return jsonify(message='Authentication required.'), 401
        if request.headers.get('Origin'):
            return jsonify(message='Browser requests are not accepted.'), 403

    @app.after_request
    def private_response(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    def body():
        if request.headers.get('Transfer-Encoding') or request.content_length is None:
            raise ValueError('Supply a bounded Content-Length.')
        data = request.get_json()
        if not isinstance(data, dict):
            raise ValueError('Each request must be a JSON object.')
        return data

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(message=error.description), error.code

    @app.errorhandler(ValueError)
    def invalid(error):
        return jsonify(message=str(error)), 400

    @app.errorhandler(KeyError)
    def missing(error):
        return jsonify(message='Unknown speech request.'), 404

    @app.get('/v1/health')
    def health():
        return jsonify(state.health())

    @app.post('/v1/speech')
    def speech():
        return jsonify(state.submit(body())), 202

    @app.get('/v1/jobs/<identifier>')
    def result(identifier):
        return jsonify(state.result(identifier))

    @app.get('/v1/jobs/<identifier>/audio')
    def audio(identifier):
        stream = state.claim_audio(identifier)
        response = Response(state.audio_chunks(stream), content_type='application/octet-stream',
                            direct_passthrough=True)
        response.headers.update({'X-Audio-Format': 'pcm_s16le', 'X-Sample-Rate': '24000',
                                 'X-Channels': '1', 'X-Sample-Width': '2'})
        # A disconnected consumer must release a producer blocked on its queue.
        response.call_on_close(stream['cancelled'].set)
        return response

    @app.patch('/v1/jobs/<identifier>')
    def speed(identifier):
        state.speed(identifier, body().get('speed'))
        return jsonify(status='updated')

    @app.post('/v1/jobs/<identifier>/stop')
    def stop_job(identifier):
        body()
        state.stop(identifier)
        return jsonify(status='stopping')

    @app.post('/v1/stop')
    def stop_all():
        body()
        state.stop()
        return jsonify(status='stopping')

    @app.post('/v1/shutdown')
    def shutdown():
        body()
        state.close()
        return jsonify(status='closing')

    return app


class TLSRequestHandler(WSGIRequestHandler):
    def setup(self):
        self.request.settimeout(3)
        self.request.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 16384)
        # TLS negotiation happens on a request thread, not on the accept loop.
        # An idle plaintext connection must not block health, Stop or shutdown.
        self.request = self.server.ssl_context.wrap_socket(self.request, server_side=True)
        super().setup()

    def finish(self):
        try:
            super().finish()
        finally:
            self.connection.close()

    def log(self, *args, **kwargs):
        pass


class LocalHTTPSServer(ThreadedWSGIServer):
    def __init__(self, app, context):
        self.slots = threading.BoundedSemaphore(16)
        super().__init__('127.0.0.1', 0, app, handler=TLSRequestHandler)
        self.ssl_context = context

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()

    def handle_error(self, request, address):
        pass

    def log(self, *args, **kwargs):
        pass

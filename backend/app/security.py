"""Bounded request bodies and non-cacheable API responses; no proxy-IP trust."""
import time
from collections import deque
from starlette.responses import JSONResponse


class RequestSafety:
    def __init__(self, app, max_upload_bytes, production=False):
        self.app, self.max_upload_bytes, self.production = app, max_upload_bytes, production
        self.reads = deque(maxlen=600)

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        path, method = scope['path'], scope['method']
        headers = dict(scope['headers'])
        async def reject(status, text):
            await JSONResponse({'detail': text}, status_code=status,
                headers={'Cache-Control':'private, no-store', 'Retry-After':'60'})(scope, receive, send)
        if len(headers.get(b'authorization', b'')) > 8192:
            return await reject(400, 'Invalid authorization header')
        if self.production and path != '/api/health':
            now = time.monotonic()
            while self.reads and self.reads[0] < now - 60:
                self.reads.popleft()
            if len(self.reads) >= 600:
                return await reject(429, 'Server request limit reached. Please retry shortly.')
            self.reads.append(now)
        if method in ('POST', 'PATCH', 'PUT'):
            maximum = self.max_upload_bytes + 1024 * 1024 if path == '/api/uploads' else self.max_upload_bytes if path.endswith('/complete') else 65536
            body = bytearray()
            while True:
                message = await receive()
                if message['type'] == 'http.disconnect':
                    return
                body.extend(message.get('body', b''))
                if len(body) > maximum:
                    return await reject(413, 'Request body exceeds the configured limit')
                if not message.get('more_body', False):
                    break
            delivered = False
            original_receive = receive
            async def buffered_receive():
                nonlocal delivered
                if delivered:
                    return await original_receive()
                delivered = True
                return {'type':'http.request', 'body':bytes(body), 'more_body':False}
            receive = buffered_receive
        started = False
        async def safe_send(message):
            nonlocal started
            if message['type'] == 'http.response.start':
                started = True
            if message['type'] == 'http.response.start' and path.startswith('/api/'):
                message['headers'] = [(k,v) for k,v in message['headers'] if k.lower() not in (b'cache-control', b'x-content-type-options')]
                message['headers'] += [(b'cache-control', b'private, no-store'), (b'x-content-type-options', b'nosniff')]
            await send(message)
        try:
            await self.app(scope, receive, safe_send)
        except Exception:
            # Consume route exceptions here: Starlette's outer error middleware
            # otherwise reraises handled errors for the server to log, including
            # SDK exception chains. Never forward those chains to access logs.
            import logging
            logging.getLogger('storyverse.api').error('Unhandled request failure (details redacted)')
            if not started:
                await JSONResponse({'detail':'Something went wrong. Please try again.'},status_code=500,
                    headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})(scope, receive, send)

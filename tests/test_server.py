"""Check the real HTTP middleware used to deliver browser assets."""
import gzip
import unittest

try:
    from streamlit.web.server.starlette.starlette_gzip_middleware import SelectiveGZipMiddleware
except ImportError:
    SelectiveGZipMiddleware = None


@unittest.skipIf(SelectiveGZipMiddleware is None, 'HTTP checks require requirements.txt')
class ServerMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def response_messages(self, headers, body):
        async def app(scope, receive, send):
            await send({'type':'http.response.start', 'status':200, 'headers':headers})
            await send({'type':'http.response.body', 'body':body})

        messages = []

        async def receive():
            return {'type':'http.request', 'body':b'', 'more_body':False}

        async def send(message):
            messages.append(message)

        scope = {'type':'http', 'path':'/component-assets/example', 'root_path':'',
                 'headers':[(b'accept-encoding', b'gzip')], 'method':'GET'}
        await SelectiveGZipMiddleware(app)(scope, receive, send)
        return messages

    async def test_image_response_sends_headers_before_body(self):
        body = b'\x89PNG\r\n\x1a\n' + b'image-content' * 100
        messages = await self.response_messages([(b'content-type', b'image/png')], body)
        self.assertEqual([m['type'] for m in messages],
                         ['http.response.start', 'http.response.body'])
        self.assertEqual(messages[0]['status'], 200)
        self.assertEqual(messages[1]['body'], body)

    async def test_precompressed_response_sends_headers_before_body(self):
        body = gzip.compress(b'console.log("asset");' * 100)
        messages = await self.response_messages([(b'content-type', b'application/javascript'),
                                                 (b'content-encoding', b'gzip')], body)
        self.assertEqual([m['type'] for m in messages],
                         ['http.response.start', 'http.response.body'])
        self.assertIn((b'content-encoding', b'gzip'), messages[0]['headers'])
        self.assertEqual(messages[1]['body'], body)

"""Read-only WSGI dashboard. Serve behind HTTPS; bind the app to loopback."""
import base64
import hmac
import json
import os
from pathlib import Path
from storage import Store


def application(env, start_response):
    headers = [('Content-Type', 'application/json; charset=utf-8'), ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff'), ('X-Frame-Options', 'DENY'), ('Referrer-Policy', 'no-referrer'), ('Strict-Transport-Security', 'max-age=31536000'), ('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")]
    def reply(status, data, mime=None):
        if mime:
            headers[0] = ('Content-Type', mime)
        start_response(status, headers)
        return [data if isinstance(data, bytes) else json.dumps(data).encode()]
    if env.get('wsgi.url_scheme') != 'https' and os.environ.get('DASHBOARD_ALLOW_HTTP') != 'true':
        return reply('403 Forbidden', {'error': 'HTTPS required'})
    user, password = os.environ.get('DASHBOARD_USER', ''), os.environ.get('DASHBOARD_PASSWORD', '')
    if not user or len(password) < 20:
        return reply('503 Service Unavailable', {'error': 'Dashboard not configured'})
    expected = 'Basic ' + base64.b64encode(f'{user}:{password}'.encode()).decode()
    if not hmac.compare_digest(env.get('HTTP_AUTHORIZATION', '').encode(), expected.encode()):
        headers.append(('WWW-Authenticate', 'Basic realm="Sottocosto Oggi", charset="UTF-8"'))
        return reply('401 Unauthorized', {'error': 'Authentication required'})
    if env.get('REQUEST_METHOD') != 'GET':
        headers.append(('Allow', 'GET'))
        return reply('405 Method Not Allowed', {'error': 'Read only'})
    path = env.get('PATH_INFO', '/')
    try:
        if path in ('/api/status', '/healthz'):
            status = Store(initialize=False).status()
            return reply('200 OK' if path == '/api/status' or status['healthy'] else '503 Service Unavailable', status if path == '/api/status' else {'healthy': status['healthy']})
        files = {'/': ('index.html', 'text/html; charset=utf-8'), '/dashboard.js': ('dashboard.js', 'text/javascript; charset=utf-8'), '/dashboard.css': ('dashboard.css', 'text/css; charset=utf-8')}
        if path not in files:
            return reply('404 Not Found', {'error': 'Not found'})
        filename, mime = files[path]
        return reply('200 OK', (Path(os.environ['DASHBOARD_DIR']) / filename).read_bytes(), mime)
    except Exception:
        # Never emit database errors or filesystem paths into HTTP responses.
        return reply('503 Service Unavailable', {'error': 'Service unavailable'})

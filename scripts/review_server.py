"""Loopback-only review UI with revision-checked writes and no model credentials."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import secrets
from urllib.parse import parse_qs, urlsplit

from core import safe_path
import review

WEB = Path(__file__).resolve().parents[1] / 'assets' / 'review'


def make_server(root, port=0, token=None):
    root = Path(root).resolve()
    review.load_project(root)
    token = token or secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Resource URLs contain the local access token.

        def send_bytes(self, payload, mime, status=200, extra=None):
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; media-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            for key, value in (extra or {}).items(): self.send_header(key, value)
            self.end_headers()
            self.wfile.write(payload)

        def json_response(self, value, status=200):
            self.send_bytes(json.dumps(value, ensure_ascii=False, allow_nan=False).encode(), 'application/json; charset=utf-8', status)

        def authorize(self, allow_query=False):
            host = f'127.0.0.1:{self.server.server_port}'
            if self.headers.get('Host') != host:
                raise PermissionError('Invalid host')
            origin = self.headers.get('Origin')
            if origin and origin != f'http://{host}':
                raise PermissionError('Invalid origin')
            supplied = self.headers.get('X-Review-Token', '')
            if allow_query:
                supplied = parse_qs(urlsplit(self.path).query).get('token', [supplied])[0]
            if not secrets.compare_digest(supplied, token):
                raise PermissionError('请用启动时提供的本地审核链接打开页面')

        def do_GET(self):
            path = urlsplit(self.path).path
            try:
                if path in ('/', '/app.js', '/style.css'):
                    name, mime = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/style.css': ('style.css', 'text/css; charset=utf-8')}[path]
                    self.send_bytes((WEB / name).read_bytes(), mime)
                elif path == '/api/state':
                    self.authorize(); self.json_response(review.view(root))
                elif path == '/api/file':
                    self.authorize(allow_query=True)
                    relative = parse_qs(urlsplit(self.path).query).get('path', [''])[0]
                    allowed = {r['path'] for r in review.view(root)['resources']}
                    if relative not in allowed:
                        raise PermissionError('Only registered project resources are available')
                    file = safe_path(root, relative)
                    extension = file.suffix.lower()
                    mime = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.mp4': 'video/mp4', '.webm': 'video/webm', '.mov': 'video/quicktime', '.zip': 'application/zip', '.blend': 'application/octet-stream'}.get(extension, 'text/plain; charset=utf-8')
                    # These are project-owned media/text only; never execute uploaded HTML/SVG.
                    extra = {'Content-Disposition': 'attachment'} if extension in ('.gltf', '.zip', '.blend') else None
                    payload = file.read_bytes()
                    if extension in ('.mp4', '.webm', '.mov'):
                        extra = {'Accept-Ranges': 'bytes'}
                        requested = self.headers.get('Range')
                        if requested:
                            try:
                                if not requested.startswith('bytes=') or ',' in requested: raise ValueError()
                                first, last = requested[6:].split('-', 1)
                                if first:
                                    start = int(first); end = int(last) if last else len(payload)-1
                                else:
                                    count = int(last)
                                    if count <= 0: raise ValueError()
                                    start = max(0, len(payload)-count); end = len(payload)-1
                                if start < 0 or start >= len(payload) or end < start: raise ValueError()
                                end = min(end, len(payload)-1)
                            except (ValueError, TypeError):
                                self.send_bytes(b'', mime, 416, {'Content-Range': f'bytes */{len(payload)}', 'Accept-Ranges':'bytes'})
                                return
                            extra['Content-Range'] = f'bytes {start}-{end}/{len(payload)}'
                            self.send_bytes(payload[start:end+1], mime, 206, extra)
                            return
                    self.send_bytes(payload, mime, extra=extra)
                else:
                    self.json_response({'error': 'Not found'}, 404)
            except PermissionError as exc:
                self.json_response({'error': str(exc)}, 403)
            except (ValueError, KeyError, OSError) as exc:
                self.json_response({'error': str(exc)}, 409)

        def do_POST(self):
            try:
                self.authorize()
                if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    raise ValueError('JSON required')
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 1024 * 1024:
                    raise ValueError('Request too large or empty')
                data = json.loads(self.rfile.read(length), parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Non-finite number')))
                path = urlsplit(self.path).path
                if path == '/api/edit':
                    if set(data) != {'id', 'zh', 'revision'}: raise ValueError('Unexpected edit fields')
                    review.edit_shot(root, data['id'], data['zh'], data['revision'])
                elif path == '/api/confirm-shot':
                    if set(data) != {'id', 'revision'}: raise ValueError('Unexpected confirmation fields')
                    review.confirm_shot(root, data['id'], data['revision'], '用户在本地审核页面点击“确认当前镜头”')
                elif path == '/api/confirm-stage':
                    if set(data) != {'stage', 'revision'}: raise ValueError('Unexpected confirmation fields')
                    review.confirm_stage(root, data['stage'], data['revision'], '用户在本地审核页面确认阶段：' + data['stage'])
                elif path == '/api/groups-plan':
                    import groups
                    groups.apply(root,data)
                elif path == '/api/groups-confirm':
                    if set(data) != {'revision','project_revision'}: raise ValueError('Unexpected group confirmation fields')
                    import groups
                    groups.confirm(root,data['revision'],data['project_revision'],'用户在审核页点击确认分组方案与中英文本')
                elif path == '/api/previs-choice':
                    if set(data) != {'choice', 'revision'}: raise ValueError('Unexpected choice fields')
                    from previs import choose
                    choose(root, data['choice'], data['revision'], '用户在本地审核页面选择：' + ('跳过预演，继续资产流程；未验证动态空间' if data['choice']=='skip' else '生成预演'))
                else:
                    self.json_response({'error': 'Not found'}, 404); return
                self.json_response(review.view(root))
            except PermissionError as exc:
                self.json_response({'error': str(exc)}, 403)
            except (ValueError, KeyError, OSError, TypeError) as exc:
                self.json_response({'error': str(exc)}, 409)

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    server.review_token = token
    return server


def serve(root, port=0):
    server = make_server(root, port)
    print(json.dumps({'url': f'http://127.0.0.1:{server.server_port}/#token={server.review_token}', 'project': str(Path(root).resolve()), 'mode': 'manual_codex_sync'}, ensure_ascii=False), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

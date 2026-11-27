import argparse
import json
import sqlite3
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener
import http.client


class Problem(Exception):
    def __init__(self, code, message, status=409):
        super().__init__(message)
        self.code = code
        self.status = status


class Unavailable(Exception):
    pass


def text(value, field):
    if not isinstance(value, str) or not value or value.strip() != value:
        raise Problem('invalid_input', f'{field} must be a nonempty identifier', 400)
    return value


def positive(value, field):
    if type(value) is not int or not 1 <= value <= 2**63 - 1:
        raise Problem('invalid_input', f'{field} must be a positive integer', 400)
    return value


def array(value, field):
    if not isinstance(value, list):
        raise Problem('invalid_input', f'{field} must be an array', 400)
    return value


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


@contextmanager
def transaction(path, *, write=False):
    db = sqlite3.connect(path, timeout=5, isolation_level=None)
    db.row_factory = sqlite3.Row
    try:
        db.execute('PRAGMA foreign_keys = ON')
        db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
    finally:
        db.close()


def install_schema(db, statements):
    for statement in statements:
        db.execute(statement)
    db.execute('CREATE TABLE IF NOT EXISTS sample_imports (name TEXT PRIMARY KEY)')


def install_sample(db, name, load):
    if db.execute('SELECT 1 FROM sample_imports WHERE name = ?', (name,)).fetchone():
        return
    load(db)
    db.execute('INSERT INTO sample_imports (name) VALUES (?)', (name,))


def invoke(url, route, data):
    req = Request(f'{url}/{route}', data=encode(data).encode(),
                  headers={'Content-Type': 'application/json'}, method='POST')
    opener = build_opener(ProxyHandler({}))
    try:
        try:
            with opener.open(req, timeout=5) as response:
                return json.load(response)['result']
        except HTTPError as error:
            with error:
                if error.code >= 500:
                    raise Unavailable(f'{route}: HTTP {error.code}') from error
                payload = json.load(error)['error']
                raise Problem(payload['code'], payload['message'], error.code) from error
    except (URLError, OSError, http.client.HTTPException, ValueError, KeyError) as error:
        raise Unavailable(f'{route}: {error}') from error


class LocalServer(ThreadingHTTPServer):
    daemon_threads = False


def make_server(dispatch, port=0):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_POST(self):
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if size <= 0:
                    raise ValueError('empty request')
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError('request must be an object')
            except (ValueError, UnicodeError):
                self.reply(400, {'error': {'code': 'invalid_json', 'message': 'Expected a JSON object'}})
                return
            try:
                result = dispatch(self.path.removeprefix('/'), data)
            except Problem as error:
                self.reply(error.status, {'error': {'code': error.code, 'message': str(error)}})
            except Unavailable as error:
                self.reply(503, {'error': {'code': 'peer_unavailable', 'message': str(error)}})
            else:
                self.reply(200, {'result': result})

        def reply(self, status, payload):
            body = encode(payload).encode()
            try:
                self.send_response(status)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                return

    return LocalServer(('127.0.0.1', port), Handler)


def local_url(port):
    return f'http://127.0.0.1:{port}'


@contextmanager
def running(server):
    with server:
        thread = Thread(target=server.serve_forever, kwargs={'poll_interval': 0.02})
        thread.start()
        try:
            yield local_url(server.server_port)
        finally:
            server.shutdown()
            thread.join()


def service_arguments(name, port, peer_port):
    parser = argparse.ArgumentParser(description=name)
    parser.add_argument('--db', required=True)
    parser.add_argument('--port', type=int, default=port)
    parser.add_argument('--peer-port', type=int, default=peer_port)
    parser.add_argument('--sample', action='store_true')
    return parser.parse_args()


def serve(dispatch, port):
    with make_server(dispatch, port) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            return

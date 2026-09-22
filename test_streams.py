"""通信が途絶えても先読みを残さず、進行中の対局は最新局面から再開する。

2026-09-22の障害では、サーバー上で終局した後も先読みが残った。
無応答の検出、終局後の解放、再接続時の局面更新と重複起動の防止を検証する。
"""

import copy
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Queue
from unittest.mock import Mock

import pytest
import requests

import lishogi
from test_correspondence import bot, config, game_full, session


@pytest.fixture
def stalled_server():
    release = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            self.wfile.write(b'10\r\n{"type":"ping"}\n\r\n')
            self.wfile.flush()
            release.wait(5)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        worker.join()


@pytest.mark.timeout(2)
@pytest.mark.parametrize("kind", ["event", "game"])
def test_silent_stream_times_out(stalled_server, monkeypatch, kind):
    # Shorten the operational deadline, while retaining real HTTP/socket reads.
    monkeypatch.setattr(lishogi, "STREAM_TIMEOUT", (0.1, 0.05), raising=False)
    api = lishogi.Lishogi("offline", stalled_server, "test", logging.CRITICAL)
    response = api.get_event_stream() if kind == "event" else api.get_game_stream("offline")
    try:
        lines = response.iter_lines()
        assert next(lines) == b'{"type":"ping"}'
        with pytest.raises((requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError)):
            next(lines)
    finally:
        response.close()


def response_with(*updates, error=None):
    response = Mock()

    def lines():
        for update in updates:
            yield json.dumps(update).encode()
        if error:
            raise error

    response.iter_lines.side_effect = lines
    return response


@pytest.mark.parametrize("failure", [None, requests.exceptions.ConnectionError("read timed out")])
def test_reconnect_uses_latest_position_and_releases_engine(config, session, failure):
    wire, _ = session
    config["engine"]["ponder"] = False
    waiting = game_full("7i7h", realtime=True)
    resumed = game_full("7i7h 6d6e", realtime=True)
    finished = copy.deepcopy(resumed["state"])
    finished.update(status="resign", winner="sente")
    first = response_with(waiting, error=failure)
    second = response_with(resumed, finished)
    api = Mock(baseUrl="https://lishogi.invalid/")
    api.get_game_stream.side_effect = [first, second]
    api.get_ongoing_games.return_value = [{"gameId": "offline"}]
    control = Queue()
    bot.play_game.__wrapped__(api, "offline", control, {"username": "bot"}, config,
                              [], Queue(), Queue(), lambda *_: None, logging.CRITICAL)
    api.make_move.assert_called_once_with("offline", "7h7g")
    assert "position startpos moves 7i7h 6d6e" in wire.lines
    assert wire.killed
    assert control.qsize() == 1
    first.close.assert_called_once()
    second.close.assert_called_once()


def test_disconnect_after_game_ended_stops_ponder(config, session, monkeypatch):
    wire, _ = session
    released = threading.Event()
    started = threading.Event()
    original_send = wire.send

    def send(line):
        original_send(line)
        if line == "stop":
            released.set()

    def recv():
        if any(line.startswith("go ponder") for line in wire.lines):
            started.set()
            assert released.wait(2), "ponder was not stopped after disconnection"
        return "bestmove", "7h7g ponder 6e6f"

    monkeypatch.setattr(wire, "send", send)
    monkeypatch.setattr(wire, "recv_usi", recv)
    response = Mock()

    def lines():
        yield json.dumps(game_full("", realtime=True)).encode()
        assert started.wait(2)
        raise requests.exceptions.ConnectionError("read timed out")

    response.iter_lines.side_effect = lines
    api = Mock(baseUrl="https://lishogi.invalid/")
    api.get_game_stream.return_value = response
    api.get_ongoing_games.return_value = []
    control = Queue()
    bot.play_game.__wrapped__(api, "offline", control, {"username": "bot"}, config,
                              [], Queue(), Queue(), lambda *_: None, logging.CRITICAL)
    assert started.is_set()
    assert released.is_set()
    assert wire.killed
    assert control.qsize() == 1
    assert api.get_game_stream.call_count == 1


def test_failed_recovery_still_releases_engine(config, session):
    wire, _ = session
    response = response_with(game_full("7i7h", realtime=True),
                             error=requests.exceptions.ConnectionError("read timed out"))
    api = Mock(baseUrl="https://lishogi.invalid/")
    api.get_game_stream.return_value = response
    denied = requests.Response()
    denied.status_code = 403
    api.get_ongoing_games.side_effect = requests.exceptions.HTTPError(response=denied)
    with pytest.raises(requests.exceptions.HTTPError):
        bot.play_game.__wrapped__(api, "offline", Queue(), {"username": "bot"}, config,
                                  [], Queue(), Queue(), lambda *_: None, logging.CRITICAL)
    assert wire.killed
    assert wire.lines[-2:] == ["stop", "quit"]
    response.close.assert_called_once()


def test_event_stream_reconnects_and_delivers_events(monkeypatch, caplog):
    api = Mock()
    first = response_with({"type": "ping"}, error=requests.exceptions.ConnectionError("read timed out"))
    second = response_with({"type": "challenge", "challenge": {"id": "offline"}})
    for response in [first, second]:
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
    api.get_event_stream.side_effect = [first, second]
    received = []

    def receive(event):
        received.append(event)
        if event["type"] == "challenge":
            monkeypatch.setattr(bot, "terminated", True)

    queue = Mock()
    queue.put_nowait.side_effect = receive
    monkeypatch.setattr(bot, "terminated", False)
    monkeypatch.setattr(bot.time, "sleep", lambda _: None)
    with caplog.at_level(logging.WARNING):
        bot.watch_control_stream(queue, api)
    assert [event["type"] for event in received] == ["ping", "challenge"]
    assert "read timed out" in caplog.text
    assert "Reconnecting event stream" in caplog.text


@pytest.mark.parametrize("kind", ["event", "game"])
def test_http_errors_close_stream_and_propagate(monkeypatch, kind):
    response = Mock()
    response.status_code = 401
    response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=response)
    monkeypatch.setattr(lishogi.requests, "get", Mock(return_value=response))
    api = lishogi.Lishogi("offline", "https://lishogi.invalid/", "test", logging.CRITICAL)
    with pytest.raises(requests.exceptions.HTTPError):
        if kind == "event":
            api.get_event_stream()
        else:
            api.get_game_stream("offline")
    response.close.assert_called_once()


def test_expired_game_releases_slot_without_starting_engine(config, session):
    wire, _ = session
    missing = requests.Response()
    missing.status_code = 404
    api = Mock()
    api.get_game_stream.side_effect = requests.exceptions.HTTPError(response=missing)
    control = Queue()
    bot.play_game.__wrapped__(api, "offline", control, {"username": "bot"}, config,
                              [], Queue(), Queue(), lambda *_: None, logging.CRITICAL)
    assert control.get_nowait() == {"type": "free_process", "gameId": "offline"}
    assert wire.lines == []
    api.get_ongoing_games.assert_not_called()


def test_failed_worker_releases_its_slot():
    control = Queue()
    bot.game_error_handler(RuntimeError("recovery failed"), control, "offline")
    assert control.get_nowait() == {"type": "free_process", "gameId": "offline"}


def test_repeated_game_start_does_not_launch_second_engine(config, monkeypatch):
    control = Queue()
    for event in [
        {"type": "gameStart", "game": {"id": "offline"}},
        {"type": "gameStart", "game": {"id": "offline"}},
        {"type": "terminated"},
    ]:
        control.put(event)
    manager = Mock()
    manager.list.return_value = []
    manager.Queue.side_effect = [control, Queue(), Queue()]
    monkeypatch.setattr(bot.multiprocessing, "Manager", lambda: manager)
    monkeypatch.setattr(bot.multiprocessing, "Process", Mock())
    pool = Mock()
    pool.__enter__ = Mock(return_value=pool)
    pool.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(bot.multiprocessing.pool, "Pool", lambda _: pool)
    monkeypatch.setattr(bot, "terminated", False)
    bot.start(Mock(), {"username": "bot"}, config, logging.CRITICAL, None)
    assert pool.apply_async.call_count == 1

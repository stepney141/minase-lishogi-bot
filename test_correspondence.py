"""通信対局の契約を、配備イメージ内でネットワークを使わず検証する。

入力形式はlishogiのchallenge/JsonView、bot/BotJsonView、game/JsonViewに基づく。
中将棋のperfは通信対局でも中将棋を示す。時間制御で受諾と対局処理を選ぶ。
config.ymlの運用方針は1手60秒、150秒で切断、600秒ごとに確認、先読みなし。
"""

import copy
import importlib
import json
import logging
import multiprocessing.pool
from pathlib import Path
from queue import Queue
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml

import engine_wrapper
from engine_ctrl import usi
import model

bot = importlib.import_module("lishogi-bot")


@pytest.fixture
def config():
    return yaml.safe_load(Path("config.yml").read_text())


def challenge(time_control, rated=False):
    return model.Challenge({
        "id": "offline", "rated": rated,
        "variant": {"key": "chushogi"}, "perf": {"name": "chushogi"},
        "challenger": {"name": "opponent", "rating": 1500},
        "timeControl": time_control,
    })


@pytest.mark.parametrize("days", [1, 2, 3, 5, 7, 10, 14])
@pytest.mark.parametrize("rated", [False, True])
def test_accepts_correspondence_chushogi(config, days, rated):
    incoming = challenge({"type": "correspondence", "daysPerTurn": days}, rated)
    assert incoming.is_supported(config["challenge"])


@pytest.mark.parametrize("limit, accepted", [(60, False), (300, True), (10800, True), (10860, False)])
def test_realtime_limits_still_apply(config, limit, accepted):
    incoming = challenge({"type": "clock", "limit": limit, "increment": 0,
                          "byoyomi": 10, "periods": 1})
    assert incoming.is_supported(config["challenge"]) is accepted


def test_unlimited_requires_its_own_acceptance(config):
    assert not challenge({"type": "unlimited"}).is_supported(config["challenge"])


def game_full(moves, username="bot", remaining=86400000, realtime=False):
    return {
        "type": "gameFull", "id": "offline", "rated": False,
        "variant": {"key": "chushogi", "name": "Chushogi"},
        "perf": {"name": "Chu shogi"},
        "clock": {"initial": 300000, "increment": 0, "byoyomi": 10000, "periods": 1} if realtime else None,
        "sente": {"name": username}, "gote": {"name": "opponent"},
        "initialSfen": "startpos",
        "state": {"type": "gameState", "moves": moves, "status": "started",
                  "btime": remaining, "wtime": remaining, "binc": 0, "winc": 0, "byo": 0},
    }


class WireEngine(usi.Engine):
    """実際のUSIコマンド生成を使い、外部プロセスとの送受信だけを記録する。"""

    def __init__(self):
        self.lines = []
        self.info = {}
        self.killed = False

    def set_variant_options(self, variant):
        pass

    def send(self, line):
        self.lines.append(line)

    def recv_usi(self):
        return "bestmove", "7h7g ponder 6e6f"

    def kill_process(self):
        self.killed = True


@pytest.fixture
def session(monkeypatch):
    engine = object.__new__(engine_wrapper.USIEngine)
    engine.go_commands = {}
    engine.engine = WireEngine()
    monkeypatch.setattr(engine_wrapper, "create_engine", lambda _: engine)
    now = SimpleNamespace(value=0)
    monkeypatch.setattr(bot.time, "time", lambda: now.value)
    monkeypatch.setattr(bot.time, "perf_counter_ns", lambda: 0)
    monkeypatch.setattr(bot.time, "sleep", lambda _: None)
    monkeypatch.setattr(bot, "terminated", False)
    return engine.engine, now


def play(config, session, full, updates=(), username="bot"):
    wire, now = session
    api = Mock(baseUrl="https://lishogi.invalid/")

    def lines():
        yield json.dumps(full).encode()
        for elapsed, update in updates:
            now.value += elapsed
            yield json.dumps(update).encode() if update else b""

    api.get_game_stream.return_value.iter_lines.side_effect = lines
    control, correspondence = Queue(), Queue()
    # Retry delays are irrelevant with a deterministic stream; propagate failures directly.
    bot.play_game.__wrapped__(api, "offline", control, {"username": username}, config,
                              [], correspondence, Queue(), lambda *_: None, logging.CRITICAL)
    assert control.get_nowait() == {"type": "free_process"}
    assert wire.lines[-2:] == ["stop", "quit"]
    assert wire.killed
    return api, correspondence


@pytest.mark.parametrize("moves, username", [("", "bot"), ("7i7h", "opponent"), ("7i7h 6d6e", "bot")])
def test_every_correspondence_turn_uses_60_seconds_without_ponder(config, session, moves, username):
    full = game_full(moves)
    api, pending = play(config, session, full, username=username)
    assert [line for line in session[0].lines if line.startswith("go ")] == ["go movetime 60000"]
    api.make_move.assert_called_once_with("offline", "7h7g")
    api.abort.assert_not_called()
    assert pending.get_nowait() == "offline"


@pytest.mark.parametrize("remaining, budget", [(5000, 3100), (1900, 1), (0, 1)])
def test_search_respects_near_deadline(config, session, remaining, budget):
    play(config, session, game_full("7i7h 6d6e", remaining=remaining))
    assert [line for line in session[0].lines if line.startswith("go ")] == [f"go movetime {budget}"]


@pytest.mark.parametrize("moves, username", [("", "opponent"), ("7i7h", "bot")])
def test_opening_wait_disconnects_without_aborting(config, session, moves, username):
    full = game_full(moves)
    api, pending = play(config, session, full, [(35, None), (116, None)], username=username)
    api.abort.assert_not_called()
    api.make_move.assert_not_called()
    assert pending.get_nowait() == "offline"


def test_reconnect_plays_the_new_position(config, session):
    full = game_full("7i7h 6d6e")
    acknowledged = copy.deepcopy(full["state"])
    acknowledged["moves"] += " 7h7g"
    api, pending = play(config, session, full, [(0, acknowledged), (151, None)])
    api.get_game_stream.return_value.close.assert_called_once()
    assert pending.get_nowait() == "offline"
    full["state"]["moves"] = acknowledged["moves"] + " 6e6f"
    api, pending = play(config, session, full)
    assert "position startpos moves 7i7h 6d6e 7h7g 6e6f" in session[0].lines
    api.make_move.assert_called_once()


def test_after_first_move_waits_150_seconds_without_aborting(config, session):
    full = game_full("")
    acknowledged = copy.deepcopy(full["state"])
    acknowledged["moves"] = "7h7g"
    api, pending = play(config, session, full, [(0, acknowledged), (35, None), (116, None)])
    assert session[1].value == 151
    api.abort.assert_not_called()
    assert pending.get_nowait() == "offline"


def test_finished_game_is_not_requeued(config, session):
    full = game_full("7i7h 6d6e")
    full["state"].update(status="resign", winner="sente")
    api, pending = play(config, session, full)
    assert pending.empty()
    api.make_move.assert_not_called()


def test_realtime_opening_keeps_short_search(config, session):
    config["engine"]["ponder"] = False
    play(config, session, game_full("", realtime=True))
    assert "go movetime 1000" in session[0].lines


@pytest.mark.parametrize("game_count", [1, 3])
def test_startup_resumes_chushogi_on_opponents_turn(config, monkeypatch, game_count):
    """再起動時の一覧には時間制御がないので、対局ストリームで判定する。"""
    control = Queue()
    game_ids = [f"offline{index}" for index in range(game_count)]
    for game_id in game_ids:
        control.put({"type": "gameStart", "game": {"id": game_id}})
    if game_count > 2:
        control.put({"type": "free_process"})
        control.put({"type": "correspondence_ping"})
    control.put({"type": "terminated"})
    manager = Mock()
    manager.list.return_value = []
    manager.Queue.side_effect = [control, Queue(), Queue()]
    monkeypatch.setattr(bot.multiprocessing, "Manager", lambda: manager)
    processes = Mock()
    monkeypatch.setattr(bot.multiprocessing, "Process", processes)
    pool = Mock()
    pool.__enter__ = Mock(return_value=pool)
    pool.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(bot.multiprocessing.pool, "Pool", lambda _: pool)
    monkeypatch.setattr(bot, "terminated", False)
    api = Mock()
    api.get_ongoing_games.return_value = [
        {"gameId": game_id, "perf": "chushogi", "isMyTurn": False} for game_id in game_ids
    ]
    bot.start(api, {"username": "bot"}, config, logging.CRITICAL, None)
    assert [call.args[1][1] for call in pool.apply_async.call_args_list] == game_ids
    pingers = [call for call in processes.call_args_list if call.kwargs["target"] is bot.do_correspondence_ping]
    assert pingers[0].kwargs["args"][1] == 600

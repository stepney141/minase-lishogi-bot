"""通信対局の対局ループとminaseを、ネットワークを使わず接続して確かめる。"""

import importlib
import json
import logging
import time
from pathlib import Path
from queue import Queue
from unittest.mock import Mock

import yaml

import engine_wrapper

bot = importlib.import_module("lishogi-bot")
config = yaml.safe_load(Path("config.yml").read_text())
assert config["correspondence"]["move_time"] == 60
assert config["correspondence"]["ponder"] is False

commands = []


class Capture(logging.Handler):
    def emit(self, record):
        message = record.getMessage()
        if message.startswith("<< "):
            commands.append(message[3:])
            print(message, flush=True)
        elif message.startswith(">> bestmove"):
            print(message, flush=True)


logging.getLogger().setLevel(logging.DEBUG)
logging.getLogger().addHandler(Capture())
state = {
    "type": "gameState", "moves": "", "status": "started",
    "btime": 86400000, "wtime": 86400000, "binc": 0, "winc": 0, "byo": 0,
}
full = {
    "type": "gameFull", "id": "offline", "variant": {"name": "Chushogi"},
    "perf": {"name": "Chu shogi"}, "clock": None, "initialSfen": "startpos",
    "sente": {"name": "bot"}, "gote": {"name": "opponent"}, "state": state,
}
api = Mock(baseUrl="https://lishogi.invalid/")
api.get_game_stream.return_value.iter_lines.return_value = iter([json.dumps(full).encode()])
control, pending = Queue(), Queue()
started = time.monotonic()
bot.play_game.__wrapped__(api, "offline", control, {"username": "bot"}, config,
                          [], pending, Queue(), lambda *_: None, logging.DEBUG)
elapsed = time.monotonic() - started
assert [line for line in commands if line.startswith("go ")] == ["go movetime 60000"]
api.make_move.assert_called_once()
game_id, move = api.make_move.call_args.args
api.abort.assert_not_called()
api.get_game_stream.return_value.close.assert_called_once()
assert game_id == "offline"
assert pending.get_nowait() == "offline"
assert control.get_nowait() == {"type": "free_process"}
assert "stop" in commands and "quit" in commands

# minase自身の合法手一覧と照合する。探索時間だけで合否を決めない。
helper = engine_wrapper.create_engine(config)
try:
    helper.engine.position("startpos", [])
    helper.engine.send("moves")
    while True:
        line = helper.engine.recv()
        if line.startswith("moves "):
            assert move in line.split()[1:], f"illegal move: {move}"
            break
finally:
    helper.quit()
    helper.engine.proccess.wait(10)
print(f"ALL CHECKS PASSED: legal move {move}, 60 s budget, elapsed {elapsed:.3f} s")

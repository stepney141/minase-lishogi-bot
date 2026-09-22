"""配備イメージの中で、Lishogi-Botの関数を実際に呼んで先読みの通信を確かめる。

lishogiへは接続しない。config.ymlどおりにエンジンを起動し、play_midgame_move、
start_pondering、get_pondering_result、および終局時の停止を、対局ループと同じ順に呼ぶ。
"""
import importlib, logging, sys, threading, time, types

import shogi
import yaml

import engine_wrapper

lb = importlib.import_module("lishogi-bot")

LINES = []


class Capture(logging.Handler):
    def emit(self, record):
        message = record.getMessage()
        if message.startswith(("<< ", ">> ")):
            LINES.append((time.perf_counter(), message))
            if not message.startswith(">> info ") or " string " in message:
                print(f"{time.perf_counter():10.3f} {message[:200]}", flush=True)


logging.getLogger().setLevel(logging.DEBUG)
logging.getLogger().addHandler(Capture())

config = yaml.safe_load(open("config.yml"))
assert config["engine"]["ponder"] is True
OVERHEAD = config["move_overhead"]


def sent_since(mark):
    return [m[3:] for _, m in LINES[mark:] if m.startswith("<< ")]


def received_since(mark):
    return [m[3:] for _, m in LINES[mark:] if m.startswith(">> ")]


def make_game(moves, btime, wtime, binc, winc, byo):
    state = {"moves": " ".join(moves), "btime": btime, "wtime": wtime, "binc": binc, "winc": winc, "byo": byo}
    return types.SimpleNamespace(id="check", variant_name="Chushogi", initial_sfen="startpos", state=state)


def make_board(moves):
    board = shogi.Board()
    for _ in moves:
        board.push(shogi.Move.null())
    return board


def legal_moves(helper, moves):
    helper.engine.position("startpos", moves)
    helper.engine.send("moves")
    while True:
        line = helper.engine.recv()
        if line.split(" ", 1)[0] == "moves":
            return line.split()[1:]


def go_clock(line):
    tokens = line.split()
    return {name: int(tokens[tokens.index(name) + 1]) for name in ("btime", "wtime", "byoyomi", "binc", "winc") if name in tokens}


def turn(engine, moves, clock, reply_kind, helper):
    """自分の1手、先読みの開始、相手の応手、先読みの回収までを対局ループと同じ順に行う。"""
    btime, wtime, binc, winc, byo = clock
    game, board = make_game(moves, *clock), make_board(moves)
    start = time.perf_counter_ns()
    best, ponder = lb.play_midgame_move(engine, board, btime, wtime, OVERHEAD, start, lb.logger, game)
    assert best is not None
    for _ in range(3):
        if ponder is not None:
            break
        # 予想手のない着手では対局ループも先読みを始めないので、局面を進めてやり直す。
        print(f"no ponder move with {best}; advancing the position", flush=True)
        moves = moves + [best]
        moves.append(legal_moves(helper, moves)[0])
        game, board = make_game(moves, *clock), make_board(moves)
        start = time.perf_counter_ns()
        best, ponder = lb.play_midgame_move(engine, board, btime, wtime, OVERHEAD, start, lb.logger, game)
    assert ponder is not None, "no ponder move in 4 consecutive searches"
    mark = len(LINES)
    thread, ponder_usi = lb.start_pondering(engine, board, best, ponder, btime, wtime, game, lb.logger, OVERHEAD, start, True)
    time.sleep(1.0)
    sent = sent_since(mark)
    assert sent[0] == "position startpos moves " + " ".join(moves + [best, ponder]), sent
    assert sent[1].startswith("go ponder "), sent
    assert not any(line.startswith("bestmove") for line in received_since(mark)), "bestmove before ponderhit/stop"
    ponder_clock = go_clock(sent[1])

    replies = legal_moves(helper, moves + [best])
    assert ponder in replies, "ponder move is not legal"
    reply = ponder if reply_kind == "hit" else next(m for m in replies if m != ponder)
    played = moves + [best, reply]
    game.state = make_game(played, *clock).state
    mark = len(LINES)
    began = time.perf_counter()
    best2, ponder2 = lb.get_pondering_result(engine, game, make_board(played), thread, ponder_usi)
    waited = time.perf_counter() - began
    sent = sent_since(mark)
    if reply_kind == "hit":
        assert sent == ["ponderhit"], sent
        assert best2 is not None
        assert best2 in legal_moves(helper, played), "move after ponderhit is not legal"
    else:
        assert sent == ["stop"], sent
        assert (best2, ponder2) == (None, None)
        assert sum(line.startswith("bestmove") for line in received_since(mark)) == 1
    return played, best2, ponder_clock, waited


engine = engine_wrapper.create_engine(config)
helper = engine_wrapper.create_engine(config)
opening = ["7i7h", "6d6e"]
opening = [m for m in opening]
first = legal_moves(helper, [])
moves = [first[0]]
moves.append(legal_moves(helper, moves)[0])

print("== 1. main time, hit ==")
clock = (300000, 300000, 0, 0, 10000)
moves, best, ponder_clock, waited = turn(engine, moves, clock, "hit", helper)
assert ponder_clock["btime"] <= 300000 - OVERHEAD - 10000, ponder_clock
print(f"ok: go ponder clock {ponder_clock}, ponderhit answered in {waited:.3f} s with {best}")
moves.append(best)
moves.append(legal_moves(helper, moves)[0])

print("== 2. main time, miss, then a normal search ==")
moves, best, ponder_clock, waited = turn(engine, moves, clock, "miss", helper)
print(f"ok: go ponder clock {ponder_clock}, stop answered in {waited:.3f} s")
game, board = make_game(moves, *clock), make_board(moves)
mark = len(LINES)
best, _ = lb.play_midgame_move(engine, board, clock[0], clock[1], OVERHEAD, time.perf_counter_ns(), lb.logger, game)
sent = sent_since(mark)
assert sent[0] == "position startpos moves " + " ".join(moves) and sent[1].startswith("go btime "), sent
assert best in legal_moves(helper, moves)
print(f"ok: normal search after the miss returned {best}")
moves.append(best)
moves.append(legal_moves(helper, moves)[0])

print("== 3. byoyomi being consumed (clock reloaded to the byoyomi), hit ==")
byo_clock = (10000, 10000, 0, 0, 10000)
moves, best, ponder_clock, waited = turn(engine, moves, byo_clock, "hit", helper)
assert ponder_clock["btime"] == 0 and ponder_clock["byoyomi"] == 10000, ponder_clock
assert waited < 10.0 - OVERHEAD / 1000, f"thought {waited:.3f} s after ponderhit in a 10 s byoyomi"
print(f"ok: go ponder clock {ponder_clock}, ponderhit answered in {waited:.3f} s with {best}")
moves.append(best)
moves.append(legal_moves(helper, moves)[0])

print("== 4. game ends while pondering ==")
game, board = make_game(moves, *clock), make_board(moves)
# 予想手の出力は任意なので、停止の検証には合法な2手を入力として与える。
best = legal_moves(helper, moves)[0]
ponder = legal_moves(helper, moves + [best])[0]
start = time.perf_counter_ns()
thread, _ = lb.start_pondering(engine, board, best, ponder, clock[0], clock[1], game, lb.logger, OVERHEAD, start, True)
time.sleep(0.5)
final = moves + [best, legal_moves(helper, moves + [best])[0]]
mark = len(LINES)
engine.report_game_result(game, final)
engine.stop()
engine.quit()
thread.join(10)
assert not thread.is_alive(), "ponder thread did not finish at game end"
engine.engine.proccess.wait(10)
sent = sent_since(mark)
assert sent[0].startswith("position startpos moves ") and sent[1:] == ["stop", "quit"], sent
assert sum(line.startswith("bestmove") for line in received_since(mark)) == 1
print(f"ok: engine exited with code {engine.engine.proccess.returncode} after position, stop, quit")
helper.quit()
print("ALL CHECKS PASSED")

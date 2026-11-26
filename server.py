import asyncio
import json
import logging
import os
import socket
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import config as cfg
from game_engine import Game, GameError
from word_bank import load_words

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("hidden_word")
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

game: Game = None
conns: dict = {}
lock = asyncio.Lock()


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


@asynccontextmanager
async def lifespan(app):
    global game
    from embeddings import SimilarityScorer
    words = load_words()                      # raises a clear error if missing/empty
    game = Game(words, SimilarityScorer(words))
    log.info("\n  Hidden Word is ready — %d words loaded.\n  Join on your Wi-Fi: "
             "http://%s:%d\n", len(words), lan_ip(), cfg.PORT)
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


app.mount("/static", StaticFiles(directory=STATIC), name="static")


async def send(ws, payload):
    try:
        await ws.send_text(json.dumps(payload))
    except Exception:  # noqa: BLE001
        pass


async def broadcast():
    for pid, ws in list(conns.items()):
        if game.has_player(pid):
            await send(ws, {"type": "state", "state": game.view(pid)})


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    pid = None
    try:
        while True:
            msg = json.loads(await ws.receive_text())
            async with lock:
                try:
                    pid = await handle(ws, pid, msg)
                except GameError as e:
                    await send(ws, {"type": "error", "message": str(e)})
                    if pid and game.has_player(pid):      # resync a possibly stale client
                        await send(ws, {"type": "state", "state": game.view(pid)})
                except (KeyError, TypeError, ValueError):
                    await send(ws, {"type": "error", "message": "Bad request."})
    except WebSocketDisconnect:
        pass
    finally:
        async with lock:
            if pid and conns.get(pid) is ws:
                del conns[pid]
                if game.has_player(pid):
                    if game.phase == "lobby":
                        game.remove_player(pid)
                    else:
                        await asyncio.to_thread(game.set_connected, pid, False)
                    await broadcast()


async def handle(ws, pid, msg):
    t = msg.get("type")
    if t == "ping":
        await send(ws, {"type": "pong"})
        return pid
    if t == "join":
        sess = msg.get("session")
        if sess and game.has_player(sess):
            pid = sess
            game.set_connected(pid, True)
            old = conns.get(pid)
            if old is not None and old is not ws:
                await old.close(code=4000)
        else:
            pid = game.add_player(msg.get("name", "")).pid
        conns[pid] = ws
        await send(ws, {"type": "joined", "pid": pid})
        await broadcast()
        return pid
    if not pid or not game.has_player(pid):
        raise GameError("Join the game first.")
    result = None
    if t == "start":
        game.start(pid)
    elif t == "select":
        game.select_word(pid, msg["word"])
    elif t == "hint":
        result = await asyncio.to_thread(game.submit_hint, pid, msg["word"],
                                         bool(msg.get("confirmed")))
    elif t == "guess":
        result = await asyncio.to_thread(game.submit_guess, pid, list(msg["words"]),
                                         bool(msg.get("use_token")),
                                         bool(msg.get("confirmed")))
    elif t == "next":
        game.next_turn(pid)
    elif t == "play_again":
        game.play_again(pid)
    else:
        raise GameError("Unknown action.")
    if result and not result["ok"]:
        await send(ws, {"type": "suggest", **result})
    else:
        await broadcast()
    return pid


if __name__ == "__main__":
    uvicorn.run(app, host=cfg.HOST, port=cfg.PORT, log_level="warning")

# actions/spotify_control.py
# Wrapper per spotify_api.py — integra la riproduzione Spotify Desktop
# nel sistema di tool-calling di MARK XXXIX-OR.
#
# TUTTO il playback passa esclusivamente da spotify_api.py (search_and_play,
# pause, resume, next_track, previous_track). Non esistono altri "player"
# Spotify nel progetto: questo wrapper e' solo un adattatore.

import sys
import platform
from pathlib import Path

# spotify_api.py vive nella root del repo
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    import spotify_api  # noqa: E402
    _SPOTIFY_OK = True
    _SPOTIFY_ERR = None
except Exception as e:
    spotify_api = None
    _SPOTIFY_OK = False
    _SPOTIFY_ERR = str(e)


def _log(player, msg: str):
    if player:
        try:
            player.write_log(f"[spotify] {msg}")
        except Exception:
            pass
    print(f"[spotify] {msg}")


def _unpack(ret):
    """search_and_play/pause/resume/next/previous di spotify_api ritornano
    una tupla (ok, msg, ...) — normalizziamola in (bool, str)."""
    if isinstance(ret, tuple):
        ok = bool(ret[0]) if len(ret) >= 1 else False
        msg = str(ret[1]) if len(ret) >= 2 else ""
        return ok, msg
    if isinstance(ret, bool):
        return ret, ""
    return bool(ret), ""


def spotify_control(parameters=None, response=None, player=None, session_memory=None) -> str:
    """
    parameters:
    action: play | pause | resume | next | previous | replay | current |
            loop_song | loop_album | loop_off
        song:   (solo per play) titolo/artista
    """
    params = parameters or {}
    action = (params.get("action") or "play").lower().strip()
    song = (params.get("song") or "").strip()

    if not _SPOTIFY_OK:
        msg = f"Sir, the Spotify module is not available: {_SPOTIFY_ERR}"
        _log(player, msg)
        return msg

    system = platform.system()
    if system != "Windows" and action in {"play", "pause", "resume", "next", "previous", "replay"}:
        _log(player, f"non-Windows ({system}): degrado a fallback nativo")

    try:
        if action == "play":
            if not song:
                return "Sir, please specify the song or artist to play."
            _log(player, f"play '{song}'")

            # Risolvi la traccia PRIMA di suonarla, cosi' abbiamo nome+artista
            # per la risposta parlata (get_current_track() ritorna None su FREE).
            track = spotify_api.search_track(song)
            if not track:
                return f"Sir, I couldn't find '{song}' on Spotify."

            ok, msg = _unpack(spotify_api.search_and_play(song, track=track))
            if ok:
                name = (track.get("name") or "").strip()
                artist = (track.get("artist") or "").strip()
                label = f"{name} - {artist}".strip(" -") or song
                return f"Now playing {label} on Spotify, sir."
            return f"Sir, I couldn't start '{song}' on Spotify. {msg}".strip()

        if action == "pause":
            _log(player, "pause")
            ok, _ = _unpack(spotify_api.pause())
            return "Music paused, sir." if ok else "Sir, Spotify is not running."

        if action == "resume":
            _log(player, "resume")
            ok, _ = _unpack(spotify_api.resume())
            return "Resuming playback, sir." if ok else "Sir, Spotify is not running."

        if action in ("next", "skip"):
            _log(player, "next")
            ok, _ = _unpack(spotify_api.next_track())
            return "Skipping to the next track, sir." if ok else "Sir, Spotify is not running."

        if action in ("previous", "prev", "back"):
            _log(player, "previous")
            ok, _ = _unpack(spotify_api.previous_track())
            return "Going back to the previous track, sir." if ok else "Sir, Spotify is not running."

        if action in ("replay", "restart", "again", "repeat_current", "same"):
            _log(player, "replay")
            ok, _ = _unpack(spotify_api.replay_track())
            return "Replaying the current track from the beginning, sir." if ok else "Sir, Spotify is not running."

        if action == "current":
            track = spotify_api.get_current_track() if hasattr(spotify_api, "get_current_track") else None
            if track and isinstance(track, dict) and track.get("name"):
                return f"Currently playing {track.get('name')} - {track.get('artist','')}".strip(" -")
            return "Sir, I cannot identify the current track."

        if action in ("loop_song", "loop_track", "repeat_song", "repeat_track"):
            _log(player, "loop song")
            ok, _ = _unpack(spotify_api.set_repeat_mode("track"))
            return "Looping this song, sir." if ok else "Sir, Spotify is not running."

        if action in ("loop_album", "loop_context", "repeat_album", "repeat_context", "loop_playlist", "repeat_playlist"):
            _log(player, "loop album")
            ok, _ = _unpack(spotify_api.set_repeat_mode("context"))
            return "Repeating the album, sir." if ok else "Sir, Spotify is not running."

        if action in ("loop_off", "repeat_off", "no_loop", "no_repeat",
                      "loop_disable", "disable_loop", "disattiva_loop",
                      "stop_loop", "loop_stop", "off"):
            _log(player, "loop off")
            ok, _ = _unpack(spotify_api.set_repeat_mode("off"))
            return "Loop disabled, sir." if ok else "Sir, Spotify is not running."

        return f"Unknown spotify action: {action}"

    except Exception as e:
        msg = f"Sir, the Spotify command failed: {e}"
        _log(player, msg)
        return msg

# actions/voice_io.py
# Riproduzione e registrazione di messaggi vocali.
#
# Riproduzione:  ffplay (ffmpeg) se installato, altrimenti playsound.
# Registrazione: sounddevice -> WAV temporaneo -> conversione OGG/Opus
#                via ffmpeg (richiesto da WhatsApp per i messaggi vocali).
#
# Comandi pubblici (per il tool dispatcher di main.py):
#   play_last_voice(parameters)            -> "Jarvis riproduci il vocale"
#   record_whatsapp_voice(parameters)      -> "Jarvis registra un vocale per X"

from __future__ import annotations
import os
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from typing import Optional

from actions.message_state import get_last_record, get_last_record_for_platform


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffplay") is not None


def _download(url: str, suffix: str = ".ogg") -> Optional[str]:
    try:
        fd, path = tempfile.mkstemp(suffix=suffix, prefix="jarvis_voice_")
        os.close(fd)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r, open(path, "wb") as f:
            f.write(r.read())
        return path
    except Exception:
        return None


def _play_file(path: str) -> tuple[bool, str]:
    if not path or not Path(path).is_file():
        return False, "File audio non trovato."
    # 1) ffplay
    if _has_ffmpeg():
        try:
            subprocess.run(
                ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path],
                check=False,
            )
            return True, "Riproduzione completata."
        except Exception:
            pass
    # 2) playsound fallback
    try:
        from playsound import playsound  # type: ignore
        playsound(path, block=True)
        return True, "Riproduzione completata (playsound)."
    except Exception as e:
        # 3) ultima spiaggia Windows: apri col player di default
        try:
            os.startfile(path)  # type: ignore[attr-defined]
            return True, "Aperto con il player di sistema."
        except Exception:
            return False, f"Impossibile riprodurre l'audio: {e}"


def play_last_voice(parameters: dict | None = None, response=None,
                    player=None, session_memory=None) -> str:
    """Riproduce l'ultimo vocale ricevuto (qualunque piattaforma)."""
    params = parameters or {}
    plat = (params.get("platform") or "").strip().lower()
    rec = (get_last_record_for_platform(plat) if plat else get_last_record())
    if not rec or rec.get("kind") != "voice":
        return "Non ho un messaggio vocale recente da riprodurre, signore."
    path = rec.get("audio_path") or ""
    url  = rec.get("audio_url")  or ""
    if not path and url:
        path = _download(url, suffix=".ogg") or ""
    if not path:
        return "Non riesco a recuperare il file vocale, signore."
    ok, msg = _play_file(path)
    if player and hasattr(player, "write_log"):
        try: player.write_log(f"[voice] play -> {msg}")
        except Exception: pass
    return msg if ok else msg


# ---------------------------------------------------------------------------
# Registrazione (solo WhatsApp)
# ---------------------------------------------------------------------------

# Stato della registrazione in corso (per il bottone della dashboard).
_rec_state: dict[str, object] = {
    "thread":  None,
    "stop":    None,   # threading.Event
    "buffer":  None,   # numpy array
    "samplerate": 44100,
}
_rec_lock = threading.Lock()


def start_recording(samplerate: int = 44100) -> tuple[bool, str]:
    """Avvia la registrazione audio dal microfono. Restituisce subito."""
    try:
        import sounddevice as sd
        import numpy as np
    except Exception as e:
        return False, f"sounddevice/numpy non disponibili: {e}"
    with _rec_lock:
        if _rec_state["thread"] is not None:
            return False, "Registrazione gia' in corso."
        stop_evt = threading.Event()
        chunks: list = []

        def _run():
            try:
                with sd.InputStream(samplerate=samplerate, channels=1,
                                    dtype="int16") as stream:
                    while not stop_evt.is_set():
                        data, _ = stream.read(1024)
                        chunks.append(data.copy())
            except Exception:
                pass

        t = threading.Thread(target=_run, daemon=True)
        _rec_state["thread"] = t
        _rec_state["stop"]   = stop_evt
        _rec_state["buffer"] = chunks
        _rec_state["samplerate"] = samplerate
        t.start()
    return True, "Registrazione avviata."


def stop_recording_and_save_wav() -> Optional[str]:
    """Ferma la registrazione, salva WAV temporaneo, ritorna il path."""
    import numpy as np
    import wave
    with _rec_lock:
        t = _rec_state.get("thread")
        stop_evt = _rec_state.get("stop")
        chunks = _rec_state.get("buffer") or []
        sr = int(_rec_state.get("samplerate") or 44100)
        _rec_state["thread"] = None
        _rec_state["stop"]   = None
        _rec_state["buffer"] = None
    if not t or not stop_evt:
        return None
    stop_evt.set()
    t.join(timeout=2)
    if not chunks:
        return None
    audio = np.concatenate(chunks, axis=0)
    fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="jarvis_rec_")
    os.close(fd)
    with wave.open(wav_path, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr)
        wf.writeframes(audio.tobytes())
    return wav_path


def _wav_to_ogg_opus(wav_path: str) -> Optional[str]:
    if not _has_ffmpeg():
        return None
    out = wav_path.replace(".wav", ".ogg")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", wav_path, "-c:a", "libopus",
             "-b:a", "32k", "-vbr", "on", "-application", "voip",
             "-loglevel", "quiet", out],
            check=True,
        )
        return out
    except Exception:
        return None


def send_recorded_voice_whatsapp(recipient: str, wav_path: str) -> tuple[bool, str]:
    """Invia il file registrato come vocale WhatsApp tramite il bridge."""
    import requests
    base = os.environ.get("WHATSAPP_BRIDGE_URL", "http://127.0.0.1:8765")
    if not Path(wav_path).is_file():
        return False, "File audio non trovato."
    ogg = _wav_to_ogg_opus(wav_path)
    upload_path = ogg or wav_path
    try:
        with open(upload_path, "rb") as f:
            files = {"file": (Path(upload_path).name, f,
                              "audio/ogg" if ogg else "audio/wav")}
            data  = {"to": recipient}
            r = requests.post(f"{base}/sendVoice", files=files, data=data, timeout=60)
        ok = r.ok and (r.json().get("ok") is True)
        return ok, r.text
    except Exception as e:
        return False, f"ERR send voice: {e}"


def record_whatsapp_voice(parameters: dict | None = None, response=None,
                          player=None, session_memory=None) -> str:
    """Comando 'Jarvis registra un vocale per X'.
    Registra per `seconds` secondi (default 8), poi invia su WhatsApp."""
    params = parameters or {}
    recipient = (params.get("receiver") or params.get("to") or "").strip()
    if not recipient:
        return "Per chi devo registrare il vocale, signore?"
    try:
        seconds = float(params.get("seconds") or 8.0)
    except Exception:
        seconds = 8.0
    seconds = max(1.0, min(seconds, 60.0))
    ok, msg = start_recording()
    if not ok:
        return msg
    if player and hasattr(player, "write_log"):
        try: player.write_log(f"[voice] rec start ({seconds}s) -> {recipient}")
        except Exception: pass
    time.sleep(seconds)
    wav = stop_recording_and_save_wav()
    if not wav:
        return "Registrazione fallita, signore."
    ok2, info = send_recorded_voice_whatsapp(recipient, wav)
    try: os.remove(wav)
    except Exception: pass
    return (f"Vocale inviato a {recipient} su WhatsApp."
            if ok2 else f"Invio vocale fallito: {info}")

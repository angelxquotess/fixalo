# actions/ai_reply.py
# - "Jarvis suggeriscimi una risposta"  ->  genera 3 risposte AI e le legge.
# - "Jarvis rispondi cosi'" (subito dopo) ->  usa l'ULTIMA risposta letta
#   come testo del messaggio e invia via send_message all'ultimo mittente.
# - "Jarvis rispondi con la prima/seconda/terza" -> sceglie la N-esima.
#
# Usa l'OpenRouter client gia' presente nel progetto (or_client.py) per
# generare le risposte.

from __future__ import annotations
import re
from typing import Optional

from actions.message_state import (
    get_last_record,
    set_ai_suggestions,
    get_ai_suggestions,
    pick_ai_suggestion,
)
from actions.send_dashboard import send_to_targets


_NUM_RE = re.compile(r"^\s*\d+[\.\)]\s*", re.M)


def _parse_suggestions(text: str) -> list[str]:
    """Estrae 2-3 risposte da una risposta LLM in formato "1) ..." / "- ..." / righe."""
    if not text:
        return []
    lines = [l.strip(" -*•\t") for l in text.splitlines() if l.strip()]
    parsed = []
    for l in lines:
        l = _NUM_RE.sub("", l).strip(" \"'")
        if 3 <= len(l) <= 240:
            parsed.append(l)
    # dedup mantenendo ordine
    seen = set(); out = []
    for s in parsed:
        k = s.lower()
        if k not in seen:
            seen.add(k); out.append(s)
        if len(out) >= 3:
            break
    return out


def suggest_reply(parameters: dict | None = None, response=None,
                  player=None, session_memory=None) -> str:
    """Genera 3 risposte all'ultimo messaggio in arrivo e le legge."""
    rec = get_last_record()
    if not rec:
        return "Non ho un messaggio recente a cui rispondere, signore."
    sender = rec.get("sender") or "qualcuno"
    body   = rec.get("body")   or ""
    plat   = (rec.get("platform") or "").capitalize()
    if not body and rec.get("kind") == "voice":
        body = "(messaggio vocale)"
    try:
        from or_client import OpenRouterClient
    except Exception as e:
        return f"Modulo OpenRouter non disponibile: {e}"
    sys_prompt = (
        "Sei l'assistente personale che suggerisce 3 risposte BREVI (max 20 "
        "parole ciascuna) in italiano, in tono naturale e amichevole, a un "
        "messaggio appena ricevuto. Rispondi SOLO con 3 righe numerate "
        "1) ... 2) ... 3) ... niente altro."
    )
    user = (f"Piattaforma: {plat}\nMittente: {sender}\nMessaggio:\n"
            f"\"\"\"\n{body}\n\"\"\"\n\nGenera 3 risposte:")
    try:
        client = OpenRouterClient()
        raw = client.chat(prompt=user, system=sys_prompt,
                          max_tokens=400, temperature=0.7)
    except Exception as e:
        return f"Errore generazione risposte: {e}"
    suggestions = _parse_suggestions(raw)
    if not suggestions:
        return "Non sono riuscito a generare risposte utili, signore."
    set_ai_suggestions(suggestions)
    spoken = "Ecco tre proposte, signore. "
    for i, s in enumerate(suggestions, 1):
        spoken += f"Opzione {i}: {s}. "
    spoken += ("Dica \"rispondi cosi'\" per la prima, oppure "
               "\"rispondi con la seconda\" o \"con la terza\".")
    if player and hasattr(player, "write_log"):
        try: player.write_log("[ai-reply] " + " | ".join(suggestions))
        except Exception: pass
    return spoken


_ORDINAL = {
    "prima": 0, "primo": 0, "uno": 0, "1": 0,
    "seconda": 1, "secondo": 1, "due": 1, "2": 1,
    "terza": 2, "terzo": 2, "tre": 2, "3": 2,
}


def reply_with_picked(parameters: dict | None = None, response=None,
                      player=None, session_memory=None) -> str:
    """Comando 'rispondi cosi' / 'rispondi con la seconda' / etc.
    Invia all'ultimo mittente l'opzione AI scelta."""
    params = parameters or {}
    suggestions = get_ai_suggestions()
    if not suggestions:
        return "Non ho proposte di risposta in memoria, signore."
    # Determina indice
    idx = 0
    raw_pick = (params.get("pick") or params.get("which") or "").strip().lower()
    if raw_pick:
        for k, v in _ORDINAL.items():
            if k in raw_pick:
                idx = v; break
    text = pick_ai_suggestion(idx) or suggestions[0]
    rec = get_last_record()
    if not rec:
        return "Non so a chi inviare la risposta, signore."
    plat   = rec.get("platform") or ""
    sender = rec.get("sender")   or ""
    if not plat or not sender:
        return "Manca destinatario o piattaforma, signore."
    results = send_to_targets([(plat, sender)], text)
    msg = results[0] if results else "Nessun risultato."
    if player and hasattr(player, "write_log"):
        try: player.write_log("[ai-reply send] " + msg + " :: " + text)
        except Exception: pass
    return f"Inviato a {sender} su {plat.capitalize()}: \"{text}\""

"""addons/voice_bridge.py — collega gli addon ai comandi vocali di JARVIS.

Genera le dichiarazioni tool per Gemini Live e smista l'esecuzione.
Tutto ADDITIVO: main.py importa build_tool_declarations() e execute_addon().
"""
from __future__ import annotations

from . import REGISTRY
from .ocr_tool import ocr_screenshot, ocr_region

# (tool_name, descrizione per il modello, {param: (tipo, descrizione)}, [required])
_SPECS: list[tuple[str, str, dict, list]] = [
    # produttivita'
    ("addon_note_add", "Salva una nota vocale dell'utente. Usa quando dice 'prendi nota', 'segnati', 'ricordati che'.",
     {"text": ("STRING", "Testo della nota")}, ["text"]),
    ("addon_note_list", "Leggi le ultime note salvate.",
     {"n": ("INTEGER", "Quante note (default 10)")}, []),
    ("addon_note_search", "Cerca tra le note salvate.",
     {"query": ("STRING", "Parola da cercare")}, ["query"]),
    ("addon_pomodoro_start", "Avvia un timer Pomodoro lavoro/pausa.",
     {"work_min": ("INTEGER", "Minuti di lavoro (default 25)"),
      "break_min": ("INTEGER", "Minuti di pausa (default 5)")}, []),
    ("addon_pomodoro_stop", "Ferma il Pomodoro attivo.", {}, []),
    ("addon_habit_mark", "Segna un'abitudine come completata oggi.",
     {"name": ("STRING", "Nome dell'abitudine (es. palestra)")}, ["name"]),
    ("addon_habit_stats", "Mostra le statistiche delle abitudini.", {}, []),
    ("addon_expense_add", "Registra una spesa. Usa quando l'utente dice 'ho speso X per Y'.",
     {"amount": ("NUMBER", "Importo in euro"),
      "category": ("STRING", "Categoria (cibo, trasporti, ...)"),
      "note": ("STRING", "Nota opzionale")}, ["amount"]),
    ("addon_expense_summary", "Riepilogo delle spese per categoria.", {}, []),
    ("addon_set_timer", "Imposta un timer con notifica. 'Timer di 5 minuti'.",
     {"seconds": ("INTEGER", "Durata in secondi"),
      "message": ("STRING", "Messaggio alla scadenza")}, ["seconds"]),
    ("addon_set_alarm", "Imposta una sveglia a un orario preciso.",
     {"hh": ("INTEGER", "Ora 0-23"), "mm": ("INTEGER", "Minuti 0-59"),
      "message": ("STRING", "Messaggio sveglia")}, ["hh", "mm"]),
    ("addon_stopwatch_start", "Avvia il cronometro.", {}, []),
    ("addon_stopwatch_read", "Leggi il tempo del cronometro.", {}, []),
    ("addon_remind_in", "Promemoria tra N minuti. 'Ricordami tra 10 minuti di...'.",
     {"minutes": ("INTEGER", "Tra quanti minuti"),
      "text": ("STRING", "Cosa ricordare")}, ["minutes", "text"]),
    ("addon_meeting_log", "Annota una frase della riunione con timestamp.",
     {"text": ("STRING", "Frase da annotare")}, ["text"]),
    ("addon_meeting_export", "Esporta tutte le note della riunione.", {}, []),
    # sistema
    ("addon_system_report", "Report del sistema: CPU, RAM, disco, OS.",
     {}, []),
    ("addon_top_processes", "Elenca i processi che usano piu' memoria.",
     {"n": ("INTEGER", "Quanti processi (default 10)")}, []),
    ("addon_kill_process", "Termina i processi con un certo nome.",
     {"name": ("STRING", "Nome processo (es. chrome)")}, ["name"]),
    ("addon_biggest_items", "Trova i file piu' grandi in una cartella.",
     {"path": ("STRING", "Cartella da analizzare"),
      "n": ("INTEGER", "Quanti risultati (default 10)")}, ["path"]),
    ("addon_find_duplicates", "Trova file duplicati in una cartella.",
     {"path": ("STRING", "Cartella da analizzare")}, ["path"]),
    ("addon_organize_folder", "Organizza i file di una cartella in sottocartelle per estensione.",
     {"path": ("STRING", "Cartella da organizzare")}, ["path"]),
    ("addon_clean_temp", "Pulisci i file temporanei del sistema.", {}, []),
    ("addon_backup_folder", "Crea un backup zip di una cartella.",
     {"src": ("STRING", "Cartella da salvare"),
      "dest_dir": ("STRING", "Dove salvare lo zip")}, ["src", "dest_dir"]),
    ("addon_power", "Spegni, riavvia, sospendi o blocca il PC, anche con ritardo.",
     {"action": ("STRING", "shutdown | restart | sleep | lock"),
      "delay_min": ("INTEGER", "Ritardo in minuti (default 0)")}, ["action"]),
    ("addon_find_files", "Cerca file per nome/pattern in una cartella.",
     {"pattern": ("STRING", "Pattern, es. *.pdf o *fattura*"),
      "root": ("STRING", "Cartella radice")}, ["pattern", "root"]),
    # rete
    ("addon_public_ip", "Mostra l'IP pubblico.", {}, []),
    ("addon_speed_test", "Testa la velocita' di download della connessione.",
     {}, []),
    ("addon_ping", "Pinga un host per verificare la connessione.",
     {"host": ("STRING", "Host o IP (default 8.8.8.8)")}, []),
    ("addon_scan_ports", "Scansiona le porte comuni aperte su un host.",
     {"host": ("STRING", "Host o IP da scansionare")}, ["host"]),
    ("addon_rss_headlines", "Leggi i titoli di un feed RSS di notizie.",
     {"feed_url": ("STRING", "URL del feed RSS"),
      "n": ("INTEGER", "Quanti titoli (default 5)")}, ["feed_url"]),
    ("addon_flush_dns", "Svuota la cache DNS.", {}, []),
    # utility
    ("addon_gen_password", "Genera una password sicura casuale.",
     {"length": ("INTEGER", "Lunghezza (default 16)")}, []),
    ("addon_calc", "Calcolatrice. Usa SEMPRE per calcoli matematici.",
     {"expr": ("STRING", "Espressione, es. (12*4)+7")}, ["expr"]),
    ("addon_convert", "Converti unita' di misura (km/mi, kg/lb, C/F, ...).",
     {"value": ("NUMBER", "Valore"),
      "from_unit": ("STRING", "Unita' origine (es. km)"),
      "to_unit": ("STRING", "Unita' destinazione (es. mi)")},
     ["value", "from_unit", "to_unit"]),
    ("addon_world_clock", "Che ore sono nel mondo.", {}, []),
    ("addon_weather_now", "Meteo attuale dettagliato di una citta' (senza API key).",
     {"city": ("STRING", "Citta' (default Roma)")}, []),
    ("addon_air_quality", "Qualita' dell'aria di una citta'.",
     {"city": ("STRING", "Citta' (default Roma)")}, []),
    ("addon_quote", "Dici una citazione tech.", {}, []),
    ("addon_joke", "Racconta una barzelletta.", {}, []),
    ("addon_trivia", "Fai una domanda trivia.", {}, []),
    ("addon_roll_dice", "Lancia dei dadi.",
     {"sides": ("INTEGER", "Facce (default 6)"),
      "count": ("INTEGER", "Quanti dadi (default 1)")}, []),
    ("addon_coin_flip", "Lancia una moneta, testa o croce.", {}, []),
    # media + OCR
    ("addon_screenshot", "Fai uno screenshot istantaneo dello schermo.",
     {}, []),
    ("addon_ocr_screenshot", "Leggi il TESTO dallo schermo (OCR). Usa quando l'utente chiede "
     "'leggi cosa c'e' scritto', 'che dice sullo schermo', 'trascrivi il testo'.",
     {"lang": ("STRING", "Lingue tesseract (default ita+eng)")}, []),
    ("addon_pixel_color", "Dimmi il colore di un pixel dello schermo.",
     {"x": ("INTEGER", "Coordinata X"), "y": ("INTEGER", "Coordinata Y")},
     ["x", "y"]),
    ("addon_record_audio", "Registra audio dal microfono per N secondi.",
     {"seconds": ("INTEGER", "Durata (default 10)")}, []),
    ("addon_clipboard_get", "Leggi il contenuto degli appunti.", {}, []),
    ("addon_clipboard_set", "Copia un testo negli appunti.",
     {"text": ("STRING", "Testo da copiare")}, ["text"]),
    # benessere
    ("addon_eye_rest_start", "Attiva il promemoria occhi 20-20-20.",
     {"minutes": ("INTEGER", "Intervallo in minuti (default 20)")}, []),
    ("addon_water_reminder_start", "Attiva il promemoria per bere acqua.",
     {"minutes": ("INTEGER", "Intervallo in minuti (default 45)")}, []),
    ("addon_stretch_reminder_start", "Attiva il promemoria stretching.",
     {"minutes": ("INTEGER", "Intervallo in minuti (default 60)")}, []),
    ("addon_posture_check", "Dai un consiglio sulla postura.", {}, []),
    ("addon_wellness_stop_all", "Ferma tutti i promemoria benessere.", {}, []),
    # QR code
    ("addon_qr_create", "Genera un QR code e mostralo a schermo. Usa quando l'utente "
     "dice 'crea un QR per questo link/testo/numero'.",
     {"data": ("STRING", "Testo o link da codificare nel QR"),
      "show": ("STRING", "'si' per aprirlo subito (default si)")}, ["data"]),
    ("addon_qr_read_screen", "Leggi/decodifica un QR code visibile sullo schermo. "
     "Usa quando l'utente dice 'leggi questo QR', 'che c'e' in questo codice'.",
     {}, []),
    ("addon_qr_read_file", "Decodifica un QR code da un file immagine.",
     {"path": ("STRING", "Percorso del file immagine")}, ["path"]),
    # scorciatoie vocali (macro)
    ("addon_macro_create", "Crea una scorciatoia vocale: una frase trigger ESATTA che "
     "lancia una sequenza di addon. steps_json = lista JSON di "
     "{\"addon\": nome_addon, \"params\": {...}}. Usa '{input}' nei params per la frase detta.",
     {"trigger": ("STRING", "Frase trigger esatta, es. 'modalita lavoro'"),
      "steps_json": ("STRING", "JSON con la lista degli step")}, ["trigger", "steps_json"]),
    ("addon_macro_run", "Esegui una scorciatoia vocale salvata, dal suo trigger.",
     {"trigger": ("STRING", "Frase trigger della scorciatoia")}, ["trigger"]),
    ("addon_macro_list", "Elenca tutte le scorciatoie vocali definite.", {}, []),
    ("addon_macro_delete", "Elimina una scorciatoia vocale.",
     {"trigger": ("STRING", "Frase trigger da eliminare")}, ["trigger"]),
    ("addon_macro_panel", "Apri il pannello grafico delle scorciatoie vocali "
     "nella finestra JARVIS. Usa quando l'utente dice 'mostrami le mie scorciatoie', "
     "'apri le macro'.",
     {}, []),
]

# fallback generico: qualsiasi altro addon del REGISTRY via nome + json
_EXTRA = {"ocr_screenshot": ocr_screenshot, "ocr_region": ocr_region,
          "macro_panel": lambda: "Apri il pannello dal tasto VOICE MACROS nella finestra."}


def _get_fn(base: str):
    if base in _EXTRA:
        return _EXTRA[base]
    try:
        from . import qr_tool, voice_macros
        dyn = {
            "qr_create": qr_tool.qr_create,
            "qr_read_screen": qr_tool.qr_read_screen,
            "qr_read_file": qr_tool.qr_read_file,
            "macro_create": voice_macros.macro_create,
            "macro_run": voice_macros.macro_run,
            "macro_list": voice_macros.macro_list,
            "macro_delete": voice_macros.macro_delete,
        }
        if base in dyn:
            return dyn[base]
    except Exception:
        pass
    entry = REGISTRY.get(base)
    return entry[1] if entry else None


def build_tool_declarations() -> list[dict]:
    decls = []
    for name, desc, props, required in _SPECS:
        decls.append({
            "name": name,
            "description": desc,
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    p: {"type": t, "description": d}
                    for p, (t, d) in props.items()
                },
                "required": required,
            },
        })
    decls.append({
        "name": "addon_run",
        "description": (
            "Esegue QUALSIASI altro addon JARVIS non presente nella lista. "
            "Passa il nome dell'addon e i parametri come stringa JSON. "
            "Addon disponibili: " + ", ".join(sorted(REGISTRY.keys()))
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "name": {"type": "STRING",
                         "description": "Nome addon dal registro"},
                "params_json": {"type": "STRING",
                                "description": "Parametri come oggetto JSON, es. {\"n\": 5}"},
            },
            "required": ["name"],
        },
    })
    return decls


def _coerce(value, spec_type: str):
    if value is None:
        return None
    try:
        if spec_type == "INTEGER":
            return int(float(value))
        if spec_type == "NUMBER":
            return float(value)
    except (TypeError, ValueError):
        return value
    return value


def execute_addon(tool_name: str, args: dict | None) -> str:
    args = dict(args or {})
    import json

    if tool_name == "addon_run":
        name = args.get("name", "")
        try:
            kwargs = json.loads(args.get("params_json") or "{}")
        except Exception:
            kwargs = {}
        fn = _EXTRA.get(name) or _get_fn(name)
        if not fn:
            return f"Addon '{name}' sconosciuto."
        try:
            return str(fn(**kwargs)) if kwargs else str(fn())
        except TypeError:
            try:
                return str(fn(*kwargs.values()))
            except Exception as e:
                return f"Addon '{name}' errore: {e}"
        except Exception as e:
            return f"Addon '{name}' errore: {e}"

    spec = next((s for s in _SPECS if s[0] == tool_name), None)
    if not spec:
        return f"Tool addon sconosciuto: {tool_name}"

    _, _, props, _ = spec
    base = tool_name[len("addon_"):]
    fn = _EXTRA.get(base) or _get_fn(base)
    if not fn:
        return f"Addon '{base}' non trovato nel registro."

    kwargs = {p: _coerce(args[p], t) for p, (t, _d) in props.items()
              if p in args and args[p] is not None}
    try:
        result = fn(**kwargs)
        if isinstance(result, (list, dict)):
            return json.dumps(result, ensure_ascii=False, default=str)[:3000]
        return str(result)[:3000]
    except Exception as e:
        return f"Addon '{base}' errore: {e}"

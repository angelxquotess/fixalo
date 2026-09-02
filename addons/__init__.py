"""addons — pacchetto ADDITIVO di nuove funzionalita' JARVIS.

Non modifica il codice esistente. Ogni funzione e' indipendente e
sicura da chiamare singolarmente. `REGISTRY` elenca tutte le funzioni
disponibili con nome, descrizione e callable, cosi' un tool dispatcher
puo' esporle al modello in futuro.
"""
from __future__ import annotations

from . import productivity, system_tools, network_tools, fun_tools, media_tools, health_tools
from . import ocr_tool, qr_tool, voice_macros

REGISTRY: dict[str, tuple[str, object]] = {
    # produttivita'
    "note_add":            ("Aggiungi una nota veloce", productivity.note_add),
    "note_list":           ("Ultime N note", productivity.note_list),
    "note_search":         ("Cerca nelle note", productivity.note_search),
    "note_clear":          ("Cancella tutte le note", productivity.note_clear),
    "pomodoro_start":      ("Avvia timer Pomodoro", productivity.pomodoro_start),
    "pomodoro_stop":       ("Ferma Pomodoro", productivity.pomodoro_stop),
    "habit_mark":          ("Segna abitudine completata oggi", productivity.habit_mark),
    "habit_stats":         ("Statistiche abitudini", productivity.habit_stats),
    "expense_add":         ("Registra una spesa", productivity.expense_add),
    "expense_summary":     ("Riepilogo spese per categoria", productivity.expense_summary),
    "set_timer":           ("Timer con notifica", productivity.set_timer),
    "set_alarm":           ("Sveglia a orario", productivity.set_alarm),
    "stopwatch_start":     ("Avvia cronometro", productivity.stopwatch_start),
    "stopwatch_read":      ("Leggi cronometro", productivity.stopwatch_read),
    "remind_in":           ("Promemoria tra N minuti", productivity.remind_in),
    "meeting_log":         ("Annotazione meeting con timestamp", productivity.meeting_log),
    "meeting_export":      ("Esporta note meeting", productivity.meeting_export),
    "focus_list_add":      ("Aggiungi sito alla lista distrazioni", productivity.focus_list_add),
    # sistema
    "system_report":       ("Report completo del sistema", system_tools.system_report),
    "top_processes":       ("Top processi per memoria", system_tools.top_processes),
    "kill_process":        ("Termina processi per nome", system_tools.kill_process),
    "biggest_items":       ("File piu' grandi in una cartella", system_tools.biggest_items),
    "find_duplicates":     ("Trova file duplicati", system_tools.find_duplicates),
    "organize_folder":     ("Organizza cartella per estensione", system_tools.organize_folder),
    "clean_temp":          ("Pulisci file temporanei", system_tools.clean_temp),
    "backup_folder":       ("Backup zip di una cartella", system_tools.backup_folder),
    "power":               ("Spegni/riavvia/sospendi/blocca", system_tools.power),
    "find_files":          ("Cerca file per pattern", system_tools.find_files),
    # rete
    "public_ip":           ("IP pubblico", network_tools.public_ip),
    "local_ip":            ("IP locale", network_tools.local_ip),
    "ip_details":          ("Dettagli IP (geo, ISP)", network_tools.ip_details),
    "speed_test":          ("Test velocita' download", network_tools.speed_test),
    "ping":                ("Ping a un host", network_tools.ping),
    "scan_ports":          ("Scansione porte comuni", network_tools.scan_ports),
    "rss_headlines":       ("Titoli da feed RSS", network_tools.rss_headlines),
    "flush_dns":           ("Svuota cache DNS", network_tools.flush_dns),
    "dns_lookup":          ("Risolvi un hostname", network_tools.dns_lookup),
    # utility varie
    "gen_password":        ("Password sicura casuale", fun_tools.gen_password),
    "gen_passphrase":      ("Passphrase leggibile", fun_tools.gen_passphrase),
    "calc":                ("Calcolatrice sicura", fun_tools.calc),
    "convert":             ("Convertitore unita'", fun_tools.convert),
    "world_clock":         ("Ora nel mondo", fun_tools.world_clock),
    "weather_now":         ("Meteo attuale (no API key)", fun_tools.weather_now),
    "air_quality":         ("Qualita' dell'aria (no API key)", fun_tools.air_quality),
    "quote":               ("Citazione del giorno", fun_tools.quote),
    "joke":                ("Barzelletta tech", fun_tools.joke),
    "trivia":              ("Domanda trivia", fun_tools.trivia),
    "text_stats":          ("Statistiche testo", fun_tools.text_stats),
    "text_transform":      ("Trasforma testo (upper/lower/...)", fun_tools.text_transform),
    "roll_dice":           ("Lancia dadi", fun_tools.roll_dice),
    "coin_flip":           ("Testa o croce", fun_tools.coin_flip),
    # media
    "screenshot":          ("Screenshot istantaneo", media_tools.screenshot),
    "pixel_color":         ("Colore del pixel sotto coordinate", media_tools.pixel_color),
    "record_audio":        ("Registra audio dal microfono", media_tools.record_audio),
    "clipboard_get":       ("Leggi clipboard", media_tools.clipboard_get),
    "clipboard_set":       ("Scrivi clipboard", media_tools.clipboard_set),
    "clipboard_history_push": ("Salva clipboard nello storico", media_tools.clipboard_history_push),
    "clipboard_history":   ("Storico clipboard", media_tools.clipboard_history),
    "type_text":           ("Digita testo automaticamente", media_tools.type_text),
    "mouse_position":      ("Posizione del mouse", media_tools.mouse_position),
    # benessere
    "eye_rest_start":      ("Promemoria 20-20-20 occhi", health_tools.eye_rest_start),
    "eye_rest_stop":       ("Ferma promemoria occhi", health_tools.eye_rest_stop),
    "water_reminder_start": ("Promemoria acqua", health_tools.water_reminder_start),
    "water_reminder_stop": ("Ferma promemoria acqua", health_tools.water_reminder_stop),
    "stretch_reminder_start": ("Promemoria stretching", health_tools.stretch_reminder_start),
    "stretch_reminder_stop": ("Ferma promemoria stretching", health_tools.stretch_reminder_stop),
    "posture_check":       ("Consiglio postura", health_tools.posture_check),
    "wellness_stop_all":   ("Ferma tutti i promemoria benessere", health_tools.stop_all),
    # OCR
    "ocr_screenshot":      ("OCR: leggi il testo dallo schermo", ocr_tool.ocr_screenshot),
    "ocr_region":          ("OCR di una regione dello schermo", ocr_tool.ocr_region),
    # QR code
    "qr_create":           ("Genera un QR code e mostralo", qr_tool.qr_create),
    "qr_read_screen":      ("Leggi un QR code dallo schermo", qr_tool.qr_read_screen),
    "qr_read_file":        ("Leggi un QR code da file immagine", qr_tool.qr_read_file),
    # scorciatoie vocali
    "macro_create":        ("Crea scorciatoia vocale (frase -> sequenza)", voice_macros.macro_create),
    "macro_run":           ("Esegui scorciatoia vocale", voice_macros.macro_run),
    "macro_list":          ("Elenca scorciatoie vocali", voice_macros.macro_list),
    "macro_delete":        ("Elimina scorciatoia vocale", voice_macros.macro_delete),
}


def run(name: str, *args, **kwargs):
    """Esegue un addon dal registro: addons.run('calc', '2+2')."""
    if name not in REGISTRY:
        return f"Addon '{name}' sconosciuto. Disponibili: {len(REGISTRY)}"
    try:
        return REGISTRY[name][1](*args, **kwargs)
    except Exception as e:
        return f"Addon '{name}' errore: {e}"


def list_addons() -> list[str]:
    return sorted(f"{k} — {v[0]}" for k, v in REGISTRY.items())

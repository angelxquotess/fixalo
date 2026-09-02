# Fix: chiedi conferma "salvare?" prima di chiudere un'app

## Richiesta
> Quando gli dico "apri blocco note, scrivi, poi chiudi", voglio che mi chieda
> se salvare o no.

## Cosa è stato cambiato

### `actions/computer_settings.py`
- Nuove helper:
  - `close_app_save()` → `Ctrl+S` → `Alt+F4` → conferma "Salva" nel dialog di sistema (Alt+S / ⌘+S)
  - `close_app_no_save()` → `Alt+F4` → conferma "Non salvare" nel dialog di sistema (Alt+N / ⌘+D)
  - `close_window_save()` / `close_window_no_save()` (analoghi per Ctrl+W / ⌘+W)
- Il dispatcher intercetta `close_app` e `close_window`:
  - Se `save_choice` non è presente → ritorna
    `"ASK_USER_SAVE_BEFORE_CLOSE: Before I close, do you want me to save the file? ..."`
    Questo segnale dice al modello di chiedere all'utente prima di richiamare il tool.
  - `save_choice='yes' | 'sì' | 'si' | 'salva'` → salva prima di chiudere
  - `save_choice='no' | 'non_salvare' | 'discard'` → chiude scartando le modifiche

### Tool schema in `main.py` (Gemini function-calling)
Aggiunto il parametro `save_choice` e la nota:
> When the user asks to close, ASK first "Do you want me to save before closing?"
> Do NOT include save_choice on the first call. Call again with save_choice='yes'|'no'.

### Prompt di sistema (`core/prompt.txt`, `core/prompt_daidai.txt`)
Aggiunta la regola esplicita per close_app / close_window:
- prima chiedi nella lingua dell'utente
- poi richiama il tool con `save_choice`

## Flusso finale atteso

```
Utente: "apri il blocco note, scrivi una lettera d'amore"
JARVIS: open_app("Notepad") → computer_settings(action="type_text", text="…")

Utente: "chiudi"
JARVIS: computer_settings(action="close_app")
        → risposta: "ASK_USER_SAVE_BEFORE_CLOSE: ..."
JARVIS (voce): "Vuoi che salvi prima di chiudere?"
Utente: "sì"
JARVIS: computer_settings(action="close_app", save_choice="yes")
        → Ctrl+S, Alt+F4, conferma "Salva" nel dialog → file salvato + app chiusa.

Oppure:
Utente: "no"
JARVIS: computer_settings(action="close_app", save_choice="no")
        → Alt+F4, conferma "Non salvare" → app chiusa senza salvare.
```

## Test
```
1) close_app senza scelta         → ASK_USER_SAVE_BEFORE_CLOSE: ...
2) close_app save_choice=yes      → SAVED_AND_CLOSED: saved then closed
3) close_app save_choice=no       → CLOSED_WITHOUT_SAVE
4) close_app save_choice=sì       → SAVED_AND_CLOSED (accetta l'italiano)
5) close_window senza scelta      → ASK_USER_SAVE_BEFORE_CLOSE: ...
6) close_window save_choice=no    → CLOSED_WITHOUT_SAVE (window)
7) volume_up                      → invariato, azioni non-close non toccate
```

Retro-compatibile con tutto il resto (restart/shutdown, volume, brightness, ecc.).

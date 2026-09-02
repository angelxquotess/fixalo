# MERGE NOTES

## Sorgenti
- daidai (feature set): https://github.com/angelxquotess/daidai

## Criterio applicato
1. **UI**: sempre Mark-L (`ui.py`).
2. **File in comune**: mantenuta la versione **Mark-L** quando i due file
   differivano principalmente per date o rifiniture; la versione daidai è
   conservata a lato con suffisso `_legacy` o `_daidai`.
3. **File esclusivi**: portati integralmente dalla repo che li possedeva.
4. **requirements.txt**: unione dei due file, con `sys_platform` guard per i
   pacchetti Windows-only.
5. **`__pycache__` / `*.pyc`**: rimossi dallo zip finale.

## File conservati "a lato" (non attivi ma disponibili)
- `main_legacy.py` — main.py originale di daidai
- `ui_legacy.py` — ui.py originale di daidai
- `core/prompt_daidai.txt` — prompt di daidai
- `requirements_add.txt` — additivi originali di daidai

## Azioni uniche importate da daidai
`ai_reply`, `calls`, `check_messages`, `jarvis_map`, `message_state`,
`qr_from_screen`, `send_dashboard`, `shortcut_creator`, `spotify_control`,
`voice_io`, `whatsapp_bridge`.

## Directory intere importate da daidai
`addons/`, `agent/`, `scorciatoie/`, `wa-bridge/`, `tests/`.

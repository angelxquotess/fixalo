# FIX APPLICATI (31 Agosto 2026)

## 1. Loop — Disambiguazione "metti in loop"

**Problema**: dicendo genericamente "metti in loop" senza specificare
canzone o album, l'LLM sceglieva a caso (spesso sbagliando).

**Fix**:
- Nuova action `loop_ask` in `actions/spotify_control.py` che risponde
  chiedendo esplicitamente all'utente: "Sir, would you like to loop
  the current song, or the whole album? Please say 'loop canzone' or
  'loop album'."
- Aggiornato il prompt del tool `spotify_control` in `main.py` così
  l'LLM ora invoca `loop_ask` solo per il generico "metti in loop" /
  "attiva il loop", mentre `loop_song` e `loop_album` vengono usate
  solo con qualificatore esplicito.

Flusso ora:
- "metti in loop"            → `loop_ask` (chiede quale)
- "metti in loop canzone"    → `loop_song`
- "metti in loop album"      → `loop_album`
- "disattiva loop" / "togli il loop" / "loop off" → `loop_off`

## 2. Loop OFF — precisione click

**Problema**: dicendo "disattiva loop" mentre era attivo il loop canzone
(`track`), il codice a volte cliccava due volte, atterrando su
`context` (album) invece di `off`, per drift dello state tracker.

**Fix in `spotify_api.py::set_repeat_mode`**:
- Se target = `off`, il numero di pressioni Ctrl+R è forzato in modo
  esplicito in base allo stato corrente:
    * `track`   → **1 click** (Spotify: track → off)
    * `context` → **2 click** (Spotify: context → track → off)
    * `off`     → **0 click**
- Aggiornati alias per accettare anche `disable_loop` / `loop_disable`.

## 3. Tray — left-click mute (Jarvis minimizzato)

**Problema**: con Jarvis minimizzato, il click sinistro sull'icona
nella tray non silenziava il microfono (né cambiava colore in rosso).

**Fix in `tray_manager.py::_install_single_click_hook`**:
- Riscrittura completa con **tre strategie di install** applicate
  tutte insieme, per resistere alle differenze fra versioni di
  pystray:
    * **A**: swap dell'entry `WM_NOTIFY` in `icon._message_handlers`.
    * **B**: monkey-patch di `icon._on_notify` (metodo bound).
    * **C**: monkey-patch class-level di `_on_notify` (con flag
      `_jarvis_patched` per idempotenza).
- Debounce da 350 ms per evitare doppio fire su `WM_LBUTTONUP` +
  `WM_LBUTTONDBLCLK` consecutivi (fast double-click).
- Print di debug all'installazione: `[Tray] single-click mute hook
  installed (multi-strategy)`.

Comportamento risultante:
- **click sinistro** sull'icona tray → toggle mute (icona diventa
  rossa quando muted, ciano quando attiva).
- **click destro** → menu Mostra / Esci / label mute.
- Sincronizzato con lo stato mute globale (`F4`, bottone HUD ecc.).

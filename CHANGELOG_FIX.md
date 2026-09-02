# JARVIS — Changelog Fix & Boost

## Bug trovati e risolti

### 1. CPU ~100% — probe GPU/temperatura in loop (`ui.py`, `_SysMetrics`)
Ogni 1.5 secondi il thread metriche provava **tutti** i tool GPU in sequenza
(`nvidia-smi`, `rocm-smi`, `intel_gpu_top`, `powermetrics`) e poi i probe
temperatura (`psutil`, `osx-cpu-temp`, PowerShell WMI). Su una macchina con
GPU NVIDIA veniva lanciato un processo `nvidia-smi` ogni 1.5s; sulle macchine
senza gli altri tool, fino a 4-5 tentativi di subprocess a ciclo.
**Fix**: il probe che funziona viene memorizzato e riusato; quelli falliti non
vengono ritentati per 5 minuti; intervallo ciclo 1.5s → 2.5s.

### 2. `asyncio.QueueFull` nel callback microfono (`main.py`, `_listen_audio`)
La coda `out_queue` ha `maxsize=10`. Quando la rete verso Gemini era lenta,
`put_nowait` dal callback audio sollevava `QueueFull` **dentro l'event loop**:
traceback a ripetizione (uno per chunk audio, ~30/sec) e frame persi.
**Fix**: enqueue sicura che scarta il frame più vecchio invece di esplodere.

### 3. Spin-loop in `_receive_audio` (`main.py`)
Se `session.receive()` terminava senza yield né eccezione, il `while True`
rientrava immediatamente nel generatore → tight-loop a CPU 100%.
**Fix**: guardia `got_any` con `await asyncio.sleep(0.05)`.

### 4. `asyncio.get_event_loop()` deprecato (`main.py`)
Dentro coroutine in esecuzione va usato `get_running_loop()`; su Python 3.12+
`get_event_loop()` genera DeprecationWarning e comportamenti ambigui.
**Fix**: sostituito in `_listen_audio` e `_play_audio`.

## Patch performance ADDITIVA (`jarvis_perf.py` + `start_jarvis_boosted.py`)

Nessun file esistente modificato: importare `jarvis_perf.apply()` prima di
`main` (oppure usare il nuovo launcher `start_jarvis_boosted.py`).

- **Cache API key / system prompt**: `api_keys.json` e `prompt.txt` venivano
  riletti da disco a ogni controllo memoria e a ogni riconnessione. Ora con
  `lru_cache` (anche per `or_client`).
- **FPS adattivi HUD**: l'animazione 30fps e la drop-zone si fermano quando la
  finestra è minimizzata/nascosta (repaint invisibili = CPU sprecata).
- **Intervallo minimo QTimer 15ms** globale: nessun timer può andare sotto.
- **GC tuning**: soglie alzate + `gc.freeze()` → meno pause.
- **Flag QtWebEngine**: disattiva compositing GPU e throttling del Chromium
  embedded (overlay WhatsApp).
- **Priorità processo BelowNormal** (ridondante con start_jarvis, ma sicura).

## Nuovi addon (cartella `addons/`, 100% additiva)

~70 funzioni registrate in `addons.REGISTRY`: note, pomodoro, abitudini,
spese, timer, sveglie, meeting notes, system report, gestione processi,
duplicati, organizzazione file, backup, pulizia temp, power, IP/speedtest/
ping/portscan/RSS/DNS, password, calcolatrice, conversioni, world clock,
meteo + qualità aria senza API key, citazioni, barzellette, trivia, testo,
dadi, screenshot, color picker, registrazione audio, clipboard + storico,
typing macro, promemoria benessere (occhi/acqua/stretching/postura).

## Test

`python tests/smoke_test.py` — verifica offline dei fix e degli addon.

## Update 2 — Addon vocali + OCR

- `addons/voice_bridge.py`: 55 tool Gemini Live dedicati (note, timer,
  sveglie, pomodoro, spese, sistema, rete, meteo, OCR, benessere...) +
  runner generico `addon_run` per tutti i 72 addon del registro.
- `main.py`: carica le dichiarazioni all'avvio e smista `addon_*` in
  `_execute_tool`. Fallback graceful se gli addon mancano.
- `addons/ocr_tool.py`: OCR schermo con pytesseract (offline) e fallback
  vision OpenRouter. Richiede Tesseract su Windows
  (https://github.com/UB-Mannheim/tesseract/wiki) + `pip install pytesseract`
  (aggiunto a requirements_add.txt).
- Comandi vocali esempio: "prendi nota che...", "timer di 5 minuti",
  "ricordami tra 10 minuti di...", "leggi cosa c'è scritto sullo schermo",
  "quanto ho speso questo mese", "fai uno screenshot", "testa la velocità
  internet", "genera una password da 20 caratteri".

## Update 3 — QR code + scorciatoie vocali

- `addons/qr_tool.py`: generazione QR (pacchetto `qrcode`, aggiunto a
  requirements_add.txt) con apertura immediata a schermo; lettura QR da
  schermo o da file con OpenCV QRCodeDetector (opencv e' GIA' nei
  requirements, nessuna dipendenza nativa extra).
  Comandi: "crea un QR per https://...", "leggi questo QR code".
- `addons/voice_macros.py`: scorciatoie vocali parola-per-parola. Crea una
  frase trigger esatta che lancia una SEQUENZA di addon:
  "Jarvis, crea la scorciatoia 'modalità lavoro' che avvia il pomodoro e
  il promemoria occhi". Da quel momento, dicendo esattamente "modalità
  lavoro" la sequenza parte SUBITO (fast-path in main._receive_audio,
  senza attendere il modello; match insensibile a maiuscole, accenti e
  punteggiatura; dedup 10s anti doppia esecuzione).
  Placeholder "{input}" nei parametri = la frase pronunciata.
  Tool vocali: addon_macro_create / run / list / delete.

## Update 4 — Pannello macro nella finestra

- Nuovo tasto "⚡ VOICE MACROS" nel pannello destro della finestra JARVIS:
  apre un overlay con l'elenco delle scorciatoie vocali. Per ogni macro:
  trigger + sequenza step, tasto MODIFICA (dialog con JSON degli step,
  validazione e salvataggio), tasto ✕ per eliminare. In basso: creazione
  nuova macro (trigger + steps JSON) e tasto REFRESH.
- Comando vocale: "Jarvis, mostrami le mie scorciatoie" apre il pannello
  (tool addon_macro_panel, instradato al segnale Qt della finestra).
- Implementazione in `addons/macro_panel.py` (stile HUD identico:
  Courier New, ciano su scuro); wiring in ui.py puramente additivo
  (segnale `_macro_sig`, tasto, metodo `_toggle_macro_overlay`).

## Update 5 — UI futuristica completa (MARK XLII)

- **Nuova palette neon**: nero spaziale + ciano elettrico con accenti
  magenta/viola (NEON / NEON2).
- **HUD ridisegnata**: sfondo statico cacheato (griglia + anello esagonale
  + angoli decorativi, renderizzato UNA volta per dimensione → meno CPU),
  anello esterno tratteggiato in contro-rotazione, anello interno magenta
  a segmenti, scanline orizzontale, flussi di dati esadecimali ai lati
  del nucleo, esagono con nodi attorno al viso.
- **Barre metriche segmentate** a blocchi (stile HUD) invece di barre piene.
- **Header**: gradiente orizzontale, titolo "J · A · R · V · I · S" con
  bordi neon laterali, badge "⬡ MARK XLII", data in magenta.
- **Pannelli laterali** con gradiente verticale, **tasto invio** con
  gradiente ciano e pressione viola, footer aggiornato.
- **Tasti rapidi (QUICK ACTIONS)**: 6 bottoni nel pannello destro —
  📸 screenshot, ⏱ timer (con dialog minuti), 📝 nota rapida, 🔳 lettura
  QR da schermo, 🌤 meteo, 🚀 speed test. Esecuzione in background,
  risultato nel log. 
- **ADDONS BROWSER** (tasto 🧠 o F3): overlay con tutte le ~75 funzioni,
  filtro di ricerca, tasto ESEGUI per quelle senza parametri.
- **Scorciatoie tastiera**: F2 = pannello macro, F3 = addons browser.
- **Bugfix**: il timer delle statistiche (2s) ora si ferma quando il
  pannello e' nascosto (prima girava sempre).

## Update 6 — Boot sequence + mini player Spotify

- `addons/boot_sequence.py`: animazione di avvio stile Iron Man a tutta
  finestra — righe di diagnostica con typewriter ("Neural core ... OK",
  "Tool matrix: 63 addons ... OK", "Welcome back, sir."), barra di
  progresso con gradiente ciano→viola, "◈ ACCESS GRANTED ◈" finale.
  Click o ESC per saltare. Parte solo se la configurazione esiste.
- `addons/spotify_widget.py`: mini player nel pannello sinistro —
  titolo/artista in riproduzione (letti dalla window title di Spotify su
  Windows), copertina via oEmbed con cache su disco, controlli ⏮ ⏯ ⏭
  via i WM_APPCOMMAND esistenti. Polling ogni 5s SOLO quando visibile.
- Bugfix: riferimento alla boot overlay ripulito dopo deleteLater
  (resizeEvent poteva toccare un oggetto distrutto).

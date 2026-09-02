# Fix applicati (JARVIS)

## 1. Impostazioni PC / Volume
`actions/computer_settings.py` → `volume_set()`
- Ora usa `SetMasterVolumeLevelScalar(value/100)` (scala lineare 0–100%
  identica a quella di Windows). Prima usava una conversione in dB che
  faceva finire "volume 80%" molto piu' basso del previsto.
- Toglie automaticamente il mute prima di impostare il volume.
- Fallback tastiera piu' affidabile (azzera e risale alla percentuale).

## 2. Browser predefinito di sistema
`actions/browser_control.py` → `_find_browser_executable()`
- Ora rispetta SEMPRE il browser predefinito del sistema (Firefox, Chrome,
  Edge, Opera, Brave, Vivaldi) rilevato dal registro/OS, mappandolo al
  motore Playwright corretto con canale/eseguibile giusto.
- Prima forzava Firefox/Chrome ignorando il predefinito.

## 3. Comprensione schermo in tempo reale
`actions/screen_processor.py` → `SYSTEM_PROMPT`
- JARVIS ora capisce il contesto di QUALSIASI app (chat, editor, browser,
  terminale...). Se dici "crea un QR di questo sito"/"questo link"/"questo
  messaggio", trova l'elemento reale a schermo (URL, messaggio, titolo) e
  agisce su quello, senza presumere di essere su una pagina web.
- Risponde nella lingua dell'utente (italiano se parli italiano).

## 4. GUI più futuristica (restyling PyQt6)
`ui.py` → palette e header aggiornati con look HUD arc-reactor più marcato.

## 5. CPU
Confermate/mantenute le ottimizzazioni esistenti (probe GPU/temp con cache,
animazioni a 30fps, metriche ogni 5s) per non sovraccaricare la CPU.

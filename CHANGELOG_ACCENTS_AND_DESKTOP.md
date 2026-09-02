# Update: Fix accenti + scorciatoie fisiche sul desktop

## 1) Fix caratteri accentati non digitati
**Problema:** JARVIS diceva nei log `Typed: à`, `Typed: ò`, ecc. ma nel campo di
testo comparivano stringhe monche ("ci far caso" invece di "ci farà caso").
La causa era `pyautogui.typewrite()` che scarta silenziosamente ogni
carattere non ASCII (àèìòù, €, ecc.).

**Soluzione (`actions/computer_control.py`):**
- `_type()` ora rileva automaticamente i caratteri unicode e usa la
  clipboard (`pyperclip` + `Ctrl+V`/`Cmd+V`) per incollarli, così le
  accentate vengono scritte davvero.
- Se la clipboard non è disponibile, viene applicata una fallback per
  singolo carattere che non lascia mai cadere una lettera.
- Il valore precedente della clipboard viene ripristinato per non
  "sporcare" quello dell'utente.
- Stessa logica anche in `_smart_type()`.

## 2) Scorciatoie FISICHE sul desktop
**Novità (`actions/shortcut_creator.py`):** JARVIS può ora creare veri
collegamenti sul Desktop dell'utente, non solo file `.py` interni.

- Windows -> `.lnk` (via `pywin32` o PowerShell come fallback)
- Linux   -> `.desktop` (`chmod +x` incluso)
- macOS   -> `.command`

Nuovi tool esposti al modello:
- `create_desktop_shortcut(name, action?, icon?)`
- `remove_desktop_shortcut(name)`

Esempi di uso vocale:
- "jarvis metti la scorciatoia 'apri chatgpt' sul desktop"
- "crea un collegamento sul desktop per lanciare il gioco"
- "togli la scorciatoia dal desktop"

Se la scorciatoia logica non esiste ancora, viene creata automaticamente
usando il parametro `action` come descrizione (es. "cerca pizza", "apri
chatgpt", path a un `.exe`, ecc.).

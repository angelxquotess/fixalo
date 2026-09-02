# Fix: computer_control action aliases (type_text, select_all, …)

## Problema
Il modulo `actions/computer_control.py` accettava solo i nomi di action "canonici"
(`type`, `press`, `hotkey`, `click`, …). Quando il modello LLM produceva alias
naturali come `type_text` o `select_all`, il dispatch rispondeva con
`Unknown action: 'type_text'`, pur essendo quella l'intenzione ovvia.

Log originale:
```
[JARVIS] 🔧 computer_control  {'action': 'type_text', 'text': '...'}
[JARVIS] 📤 computer_control → Unknown action: 'type_text'
[JARVIS] 🔧 computer_control  {'action': 'select_all'}
[JARVIS] 📤 computer_control → Unknown action: 'select_all'
```

## Causa
In `computer_control(...)` il dispatch confrontava `action` con stringhe
esatte. Non c'era normalizzazione né tabella di sinonimi.

## Fix
Aggiunta una mappa di alias `_ACTION_ALIASES` che normalizza l'action ricevuta
verso il nome canonico prima del dispatch, più due handler dedicati:

- `select_all` / `selectall` / `select`  → `hotkey ctrl+a` (o `command+a` su macOS)
- `scroll_up`, `scroll_down`, `scroll_left`, `scroll_right` → `_scroll(direction, amount)`

### Alias supportati (estratto)
| Alias in ingresso | Action canonica |
|---|---|
| `type_text`, `typewrite`, `write`, `write_text`, `text_input`, `input_text`, `enter_text`, `keyboard_type` | `type` |
| `smart_typing`, `smart_write`, `type_smart` | `smart_type` |
| `key_press`, `keypress`, `press_key`, `hit_key`, `tap_key` | `press` |
| `hot_key`, `keyboard_shortcut`, `shortcut`, `combo`, `key_combo` | `hotkey` |
| `mouse_click`, `left_click`, `mouse_left_click` | `click` |
| `mouse_right_click` | `right_click` |
| `mouse_double_click`, `dbl_click` | `double_click` |
| `mouse_move`, `move_mouse` | `move` |
| `mouse_drag`, `drag_mouse` | `drag` |
| `screen_capture`, `capture_screen`, `take_screenshot` | `screenshot` |
| `sleep`, `delay`, `pause` | `wait` |
| `clipboard_copy`, `clipboard_get` | `copy` |
| `clipboard_paste`, `paste_text` | `paste` |
| `clear`, `clear_input`, `erase_field` | `clear_field` |
| `focus`, `activate_window`, `bring_to_front` | `focus_window` |
| `find_element` | `screen_find` |
| `click_element`, `ai_click` | `screen_click` |
| `fake_data`, `generate_data` | `random_data` |
| `profile_data`, `memory_data` | `user_data` |
| `select_all`, `selectall`, `select` | `hotkey(ctrl+a)` |

## Verifica
Eseguito test sintetico:
```
type_text     → Typed: Ciao mondo
select_all    → Hotkey: ctrl+a
write         → Typed: test
keypress      → Pressed: enter
sleep         → Waited 0.01s
hotkey        → Hotkey: ctrl+a   (retro-compatibile)
type          → Typed: still works (retro-compatibile)
unknown_thing → Unknown action: 'unknown_thing' (fallback intatto)
```

Nessuna regressione sulle action canoniche.

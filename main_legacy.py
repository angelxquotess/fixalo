import asyncio
import threading
import time
import json
import sys
import traceback
from pathlib import Path

import sounddevice as sd
from google import genai
from google.genai import types
from ui import JarvisUI
from memory.memory_manager import (
    load_memory, update_memory, format_memory_for_prompt,
    should_extract_memory, extract_memory
)

from actions.file_processor import file_processor
from actions.flight_finder     import flight_finder
from actions.open_app          import open_app
from actions.weather_report    import weather_action
from actions.send_message      import send_message
from actions.check_messages    import (
    check_messages, start_notification_pollers, read_last_notifications,
)
from actions.voice_io          import play_last_voice, record_whatsapp_voice
from actions.ai_reply          import suggest_reply, reply_with_picked
from actions.calls             import start_call
from actions.reminder          import reminder
from actions.computer_settings import computer_settings
from actions.screen_processor  import screen_process
from actions.youtube_video     import youtube_video
from actions.desktop           import desktop_control
from actions.browser_control   import browser_control
from actions.file_controller   import file_controller
from actions.code_helper       import code_helper
from actions.dev_agent         import dev_agent
from actions.web_search        import web_search as web_search_action
from actions.computer_control  import computer_control
from actions.game_updater      import game_updater
from actions.spotify_control   import spotify_control
from actions.jarvis_map        import jarvis_map
from actions.qr_from_screen    import qr_from_screen
from actions.shortcut_creator  import (
    create_shortcut as shortcut_create,
    run_shortcut    as shortcut_run,
    list_shortcuts  as shortcut_list,
    create_desktop_shortcut  as shortcut_desktop_create,
    remove_desktop_shortcut  as shortcut_desktop_remove,
)


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"
LIVE_MODEL          = "models/gemini-2.5-flash-native-audio-preview-12-2025"
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024


def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            "You are JARVIS, Tony Stark's AI assistant. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool."
        )
    
_last_memory_input = ""

def _update_memory_async(user_text: str, jarvis_text: str) -> None:
    global _last_memory_input

    user_text   = (user_text   or "").strip()
    jarvis_text = (jarvis_text or "").strip()

    if len(user_text) < 5 or user_text == _last_memory_input:
        return
    _last_memory_input = user_text

    try:
        api_key = _get_api_key()
        if not should_extract_memory(user_text, jarvis_text, api_key):
            return
        data = extract_memory(user_text, jarvis_text, api_key)
        if data:
            update_memory(data)
            print(f"[Memory] ✅ {list(data.keys())}")
    except Exception as e:
        if "429" not in str(e):
            print(f"[Memory] ⚠️ {e}")

TOOL_DECLARATIONS = [
    {
        "name": "open_app",
        "description": (
            "Opens any application on the Windows computer. "
            "Use this whenever the user asks to open, launch, or start any app, "
            "website, or program. Always call this tool — never just say you opened it."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Exact name of the application (e.g. 'WhatsApp', 'Chrome', 'Spotify')"
                }
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "web_search",
        "description": "Searches the web for any information.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":  {"type": "STRING", "description": "Search query"},
                "mode":   {"type": "STRING", "description": "search (default) or compare"},
                "items":  {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Items to compare"},
                "aspect": {"type": "STRING", "description": "price | specs | reviews"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "weather_report",
        "description": "Gives the weather report to user",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {"type": "STRING", "description": "City name"}
            },
            "required": ["city"]
        }
    },
    {
        "name": "send_message",
        "description": (
            "Comando UNICO per inviare messaggi. Usalo quando l'utente dice "
            "'jarvis invia un messaggio', 'manda un messaggio', 'scrivi a ...', "
            "o quando dice 'rispondi con <testo>' dopo aver ricevuto una notifica.\n"
            "- Senza parametri: apre la DASHBOARD desktop (PyQt6) dove l'utente "
            "  sceglie piattaforma (WhatsApp / Telegram / Discord / Instagram), "
            "  fa la scansione completa delle chat, seleziona uno o piu' destinatari "
            "  e scrive il messaggio.\n"
            "- Con receiver + platform + message_text: invia DIRETTAMENTE via "
            "  API/token, senza aprire app o siti.\n"
            "- Per 'rispondi con <testo>' dopo una notifica: passa solo "
            "  message_text (lascia receiver e platform vuoti): il sistema usa "
            "  l'ultimo mittente memorizzato."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver":     {"type": "STRING", "description": "Destinatario (opzionale)"},
                "message_text": {"type": "STRING", "description": "Testo del messaggio"},
                "platform":     {"type": "STRING", "description": "whatsapp | telegram | discord | instagram (opzionale)"}
            },
            "required": []
        }
    },
    {
        "name": "check_messages",
        "description": (
            "Comando 'Jarvis ho messaggi da leggere?': controlla TUTTE le piattaforme "
            "collegate (WhatsApp, Telegram, Discord, Instagram) e ritorna i messaggi "
            "non letti riassunti per piattaforma e mittente. Usa SEMPRE questo tool "
            "quando l'utente chiede se ci sono messaggi nuovi, da leggere, o non letti."
        ),
        "parameters": {"type": "OBJECT", "properties": {}, "required": []}
    },
    {
        "name": "read_last_notifications",
        "description": (
            "Comando 'Jarvis leggimi le ultime N notifiche': legge ad alta voce il "
            "CONTENUTO delle ultime notifiche memorizzate (testo o 'messaggio vocale')."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "count": {"type": "INTEGER", "description": "Quante notifiche leggere (default 5, max 50)"},
            },
            "required": []
        }
    },
    {
        "name": "play_last_voice",
        "description": (
            "Comando 'Jarvis riproduci il vocale' / 'sì, riproducilo': riproduce "
            "l'ultimo messaggio vocale ricevuto (qualunque piattaforma). Usa ffmpeg "
            "se installato, altrimenti playsound. Opzionale: filtrare per piattaforma."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "platform": {"type": "STRING", "description": "whatsapp | telegram | discord | instagram (opzionale)"},
            },
            "required": []
        }
    },
    {
        "name": "record_whatsapp_voice",
        "description": (
            "Comando 'Jarvis registra un vocale per <X>' SOLO SU WHATSAPP. Registra "
            "dal microfono per N secondi (default 8) e invia il vocale al "
            "destinatario tramite il bridge whatsapp-web.js."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver": {"type": "STRING", "description": "Nome contatto o numero WhatsApp"},
                "seconds":  {"type": "NUMBER", "description": "Durata registrazione in secondi (1-60, default 8)"},
            },
            "required": ["receiver"]
        }
    },
    {
        "name": "suggest_reply",
        "description": (
            "Comando 'Jarvis suggeriscimi una risposta': genera 3 risposte AI brevi "
            "all'ultimo messaggio ricevuto e le legge ad alta voce. Dopo, l'utente "
            "puo' dire 'rispondi cosi'' per la prima o 'rispondi con la seconda/terza'."
        ),
        "parameters": {"type": "OBJECT", "properties": {}, "required": []}
    },
    {
        "name": "reply_with_picked",
        "description": (
            "Comando 'Jarvis rispondi cosi'' / 'rispondi con la seconda/terza': "
            "invia all'ULTIMO mittente sulla stessa piattaforma la risposta AI scelta. "
            "Da chiamare SOLO dopo suggest_reply."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "pick": {"type": "STRING", "description": "prima | seconda | terza (default: prima)"},
            },
            "required": []
        }
    },
    {
        "name": "start_call",
        "description": (
            "Comando 'Jarvis chiama <X> su <piattaforma>': avvia una chiamata vocale "
            "su WhatsApp, Telegram o Discord. Se l'app non e' aperta la apre e "
            "ASPETTA fino a 15 secondi che la finestra compaia prima di avviare la "
            "chiamata. WhatsApp accetta sia nome contatto sia numero +39..."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "platform": {"type": "STRING", "description": "whatsapp | telegram | discord"},
                "receiver": {"type": "STRING", "description": "Nome contatto, @username o numero"},
            },
            "required": ["receiver"]
        }
    },
    {
        "name": "reminder",
        "description": "Sets a timed reminder using Windows Task Scheduler.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date":    {"type": "STRING", "description": "Date in YYYY-MM-DD format"},
                "time":    {"type": "STRING", "description": "Time in HH:MM format (24h)"},
                "message": {"type": "STRING", "description": "Reminder message text"}
            },
            "required": ["date", "time", "message"]
        }
    },
    {
        "name": "youtube_video",
        "description": (
            "Controls YouTube. Use for: playing videos, summarizing a video's content, "
            "getting video info, or showing trending videos."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | summarize | get_info | trending (default: play)"},
                "query":  {"type": "STRING", "description": "Search query for play action"},
                "save":   {"type": "BOOLEAN", "description": "Save summary to Notepad (summarize only)"},
                "region": {"type": "STRING", "description": "Country code for trending e.g. TR, US"},
                "url":    {"type": "STRING", "description": "Video URL for get_info action"},
            },
            "required": []
        }
    },
    {
        "name": "screen_process",
        "description": (
            "Captures and analyzes the screen or webcam image. "
            "MUST be called when user asks what is on screen, what you see, "
            "analyze my screen, look at camera, etc. "
            "You have NO visual ability without this tool. "
            "After calling this tool, stay SILENT — the vision module speaks directly."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {"type": "STRING", "description": "'screen' to capture display, 'camera' for webcam. Default: 'screen'"},
                "text":  {"type": "STRING", "description": "The question or instruction about the captured image"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "computer_settings",
        "description": (
            "Controls the computer: volume, brightness, window management, keyboard shortcuts, "
            "typing text on screen, closing apps, fullscreen, dark mode, WiFi, restart, shutdown, "
            "scrolling, tab management, zoom, screenshots, lock screen, refresh/reload page. "
            "Use for ANY single computer control command. NEVER route to agent_task."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "The action to perform"},
                "description": {"type": "STRING", "description": "Natural language description of what to do"},
                "value":       {"type": "STRING", "description": "Optional value: volume level, text to type, etc."}
            },
            "required": []
        }
    },
    {
        "name": "browser_control",
        "description": (
            "Controls the web browser. Use for: opening websites, searching the web, "
            "clicking elements, filling forms, scrolling, any web-based task."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "go_to | search | click | type | scroll | fill_form | smart_click | smart_type | get_text | press | close"},
                "url":         {"type": "STRING", "description": "URL for go_to action"},
                "query":       {"type": "STRING", "description": "Search query for search action"},
                "selector":    {"type": "STRING", "description": "CSS selector for click/type"},
                "text":        {"type": "STRING", "description": "Text to click or type"},
                "description": {"type": "STRING", "description": "Element description for smart_click/smart_type"},
                "direction":   {"type": "STRING", "description": "up or down for scroll"},
                "key":         {"type": "STRING", "description": "Key name for press action"},
                "incognito":   {"type": "BOOLEAN", "description": "Open in private/incognito mode"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_controller",
        "description": "Manages files and folders: list, create, delete, move, copy, rename, read, write, find, disk usage.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "list | create_file | create_folder | delete | move | copy | rename | read | write | find | largest | disk_usage | organize_desktop | info"},
                "path":        {"type": "STRING", "description": "File/folder path or shortcut: desktop, downloads, documents, home"},
                "destination": {"type": "STRING", "description": "Destination path for move/copy"},
                "new_name":    {"type": "STRING", "description": "New name for rename"},
                "content":     {"type": "STRING", "description": "Content for create_file/write"},
                "name":        {"type": "STRING", "description": "File name to search for"},
                "extension":   {"type": "STRING", "description": "File extension to search (e.g. .pdf)"},
                "count":       {"type": "INTEGER", "description": "Number of results for largest"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "desktop_control",
        "description": "Controls the desktop: wallpaper, organize, clean, list, stats.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "wallpaper | wallpaper_url | organize | clean | list | stats | task"},
                "path":   {"type": "STRING", "description": "Image path for wallpaper"},
                "url":    {"type": "STRING", "description": "Image URL for wallpaper_url"},
                "mode":   {"type": "STRING", "description": "by_type or by_date for organize"},
                "task":   {"type": "STRING", "description": "Natural language desktop task"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "code_helper",
        "description": "Writes, edits, explains, runs, or builds code files.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "write | edit | explain | run | build | auto (default: auto)"},
                "description": {"type": "STRING", "description": "What the code should do or what change to make"},
                "language":    {"type": "STRING", "description": "Programming language (default: python)"},
                "output_path": {"type": "STRING", "description": "Where to save the file"},
                "file_path":   {"type": "STRING", "description": "Path to existing file for edit/explain/run/build"},
                "code":        {"type": "STRING", "description": "Raw code string for explain"},
                "args":        {"type": "STRING", "description": "CLI arguments for run/build"},
                "timeout":     {"type": "INTEGER", "description": "Execution timeout in seconds (default: 30)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "dev_agent",
        "description": "Builds complete multi-file projects from scratch: plans, writes files, installs deps, opens VSCode, runs and fixes errors.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description":  {"type": "STRING", "description": "What the project should do"},
                "language":     {"type": "STRING", "description": "Programming language (default: python)"},
                "project_name": {"type": "STRING", "description": "Optional project folder name"},
                "timeout":      {"type": "INTEGER", "description": "Run timeout in seconds (default: 30)"},
            },
            "required": ["description"]
        }
    },
    {
        "name": "agent_task",
        "description": (
            "Executes complex multi-step tasks requiring multiple different tools. "
            "Examples: 'research X and save to file', 'find and organize files'. "
            "DO NOT use for single commands. NEVER use for Steam/Epic — use game_updater."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal":     {"type": "STRING", "description": "Complete description of what to accomplish"},
                "priority": {"type": "STRING", "description": "low | normal | high (default: normal)"}
            },
            "required": ["goal"]
        }
    },
    {
        "name": "computer_control",
        "description": "Direct computer control: type, click, hotkeys, scroll, move mouse, screenshots, find elements on screen.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | screen_find | screen_click | random_data | user_data"},
                "text":        {"type": "STRING", "description": "Text to type or paste"},
                "x":           {"type": "INTEGER", "description": "X coordinate"},
                "y":           {"type": "INTEGER", "description": "Y coordinate"},
                "keys":        {"type": "STRING", "description": "Key combination e.g. 'ctrl+c'"},
                "key":         {"type": "STRING", "description": "Single key e.g. 'enter'"},
                "direction":   {"type": "STRING", "description": "up | down | left | right"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount (default: 3)"},
                "seconds":     {"type": "NUMBER",  "description": "Seconds to wait"},
                "title":       {"type": "STRING",  "description": "Window title for focus_window"},
                "description": {"type": "STRING",  "description": "Element description for screen_find/screen_click"},
                "type":        {"type": "STRING",  "description": "Data type for random_data"},
                "field":       {"type": "STRING",  "description": "Field for user_data: name|email|city"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
                "path":        {"type": "STRING",  "description": "Save path for screenshot"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "game_updater",
        "description": (
            "THE ONLY tool for ANY Steam or Epic Games request. "
            "Use for: installing, downloading, updating games, listing installed games, "
            "checking download status, scheduling updates. "
            "ALWAYS call directly for any Steam/Epic/game request. "
            "NEVER use agent_task, browser_control, or web_search for Steam/Epic."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING",  "description": "update | install | list | download_status | schedule | cancel_schedule | schedule_status (default: update)"},
                "platform":  {"type": "STRING",  "description": "steam | epic | both (default: both)"},
                "game_name": {"type": "STRING",  "description": "Game name (partial match supported)"},
                "app_id":    {"type": "STRING",  "description": "Steam AppID for install (optional)"},
                "hour":      {"type": "INTEGER", "description": "Hour for scheduled update 0-23 (default: 3)"},
                "minute":    {"type": "INTEGER", "description": "Minute for scheduled update 0-59 (default: 0)"},
                "shutdown_when_done": {"type": "BOOLEAN", "description": "Shut down PC when download finishes"},
            },
            "required": []
        }
    },
    {
        "name": "flight_finder",
        "description": "Searches Google Flights and speaks the best options.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "origin":      {"type": "STRING",  "description": "Departure city or airport code"},
                "destination": {"type": "STRING",  "description": "Arrival city or airport code"},
                "date":        {"type": "STRING",  "description": "Departure date (any format)"},
                "return_date": {"type": "STRING",  "description": "Return date for round trips"},
                "passengers":  {"type": "INTEGER", "description": "Number of passengers (default: 1)"},
                "cabin":       {"type": "STRING",  "description": "economy | premium | business | first"},
                "save":        {"type": "BOOLEAN", "description": "Save results to Notepad"},
            },
            "required": ["origin", "destination", "date"]
        }
    },
    {
    "name": "file_processor",
    "description": (
        "Processes any file that the user has uploaded or dropped onto the interface. "
        "Use this when the user refers to an uploaded file and wants an action on it. "
        "Supports: images (describe/ocr/resize/compress/convert), "
        "PDFs (summarize/extract_text/to_word), "
        "Word docs & text files (summarize/fix/reformat/translate), "
        "CSV/Excel (analyze/stats/filter/sort/convert), "
        "JSON/XML (validate/format/analyze), "
        "code files (explain/review/fix/optimize/run/document/test), "
        "audio (transcribe/trim/convert/info), "
        "video (trim/extract_audio/extract_frame/compress/transcribe/info), "
        "archives (list/extract), "
        "presentations (summarize/extract_text). "
        "ALWAYS call this tool when a file has been uploaded and the user gives a command about it. "
        "If the user's command is ambiguous, pick the most logical action for that file type."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "file_path": {
                "type": "STRING",
                "description": "Full path to the uploaded file. Leave empty to use the currently uploaded file."
            },
            "action": {
                "type": "STRING",
                "description": (
                    "What to do with the file. Examples by type:\n"
                    "image: describe | ocr | resize | compress | convert | info\n"
                    "pdf: summarize | extract_text | to_word | info\n"
                    "docx/txt: summarize | fix | reformat | translate_hint | word_count | to_bullet\n"
                    "csv/excel: analyze | stats | filter | sort | convert | info\n"
                    "json: validate | format | analyze | to_csv\n"
                    "code: explain | review | fix | optimize | run | document | test\n"
                    "audio: transcribe | trim | convert | info\n"
                    "video: trim | extract_audio | extract_frame | compress | transcribe | info | convert\n"
                    "archive: list | extract\n"
                    "pptx: summarize | extract_text | analyze"
                )
            },
            "instruction": {
                "type": "STRING",
                "description": "Free-form instruction if action doesn't cover it. E.g. 'translate this to Turkish', 'find all email addresses'"
            },
            "format": {
                "type": "STRING",
                "description": "Target format for conversion. E.g. 'mp3', 'pdf', 'csv', 'png'"
            },
            "width":     {"type": "INTEGER", "description": "Target width for image resize"},
            "height":    {"type": "INTEGER", "description": "Target height for image resize"},
            "scale":     {"type": "NUMBER",  "description": "Scale factor for image resize (e.g. 0.5)"},
            "quality":   {"type": "INTEGER", "description": "Quality 1-100 for image/video compress"},
            "start":     {"type": "STRING",  "description": "Start time for trim: seconds or HH:MM:SS"},
            "end":       {"type": "STRING",  "description": "End time for trim: seconds or HH:MM:SS"},
            "timestamp": {"type": "STRING",  "description": "Timestamp for video frame extraction HH:MM:SS"},
            "column":    {"type": "STRING",  "description": "Column name for CSV filter/sort"},
            "value":     {"type": "STRING",  "description": "Filter value for CSV filter"},
            "condition": {"type": "STRING",  "description": "Filter condition: equals|contains|gt|lt"},
            "ascending": {"type": "BOOLEAN", "description": "Sort order for CSV sort (default: true)"},
            "save":      {"type": "BOOLEAN", "description": "Save result to file (default: true)"},
            "destination": {"type": "STRING", "description": "Output folder for archive extract"},
        },
        "required": []
    }
},
    {
    "name": "shutdown_jarvis",
    "description": (
        "Shuts down the assistant completely. "
        "Call this when the user expresses intent to end the conversation, "
        "close the assistant, say goodbye, or stop Jarvis. "
        "The user can say this in ANY language."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {},
    }
    },
    {
        "name": "spotify_control",
        "description": (
            "Controls Spotify Desktop playback. Use this for ANY music request "
            "involving Spotify: playing a song or artist, pausing, resuming, "
            "skipping to next/previous track, or asking what is currently playing. "
            "Examples: 'play Bohemian Rhapsody', 'metti Imagine Dragons', "
            "'pausa', 'riprendi', 'prossima canzone', 'canzone precedente'. "
            "Always call this tool — never just say you played the song."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "play | pause | resume | next | previous | current (default: play)"
                },
                "song": {
                    "type": "STRING",
                    "description": "Song title and/or artist for the 'play' action (e.g. 'Bohemian Rhapsody Queen')"
                },
            },
            "required": ["action"]
        }
    },
    {
        "name": "qr_from_screen",
        "description": (
            "Genera un CODICE QR reale a partire dal link visibile sullo "
            "schermo. Usa questo tool quando l'utente dice cose come "
            "'jarvis crea il QR di questo link', 'genera un QR da quello che "
            "vedi', 'fammi il QR di questa pagina'. Se l'utente fornisce "
            "gia' l'URL passalo in 'url', altrimenti JARVIS legge lo schermo "
            "(OCR + AI) e ne estrae il link. Il QR viene mostrato in una "
            "finestra HUD sopra la UI."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "url": {"type": "STRING", "description": "URL opzionale (se non passato viene letto dallo schermo)"},
            },
            "required": []
        }
    },
    {
        "name": "jarvis_map",
        "description": (
            "Opens an interactive 2D JARVIS-style HUD map centered on a specific "
            "city or location and shows nearby points of interest with a brief "
            "live description (current weather, history, population). "
            "Use this whenever the user asks to SHOW, DISPLAY, OPEN or VISUALIZE "
            "a place on a map. Examples: 'show me New York', 'mostrami Roma', "
            "'visualizza Tokyo sulla mappa', 'open the map of Paris'. "
            "ALWAYS call this tool for any 'show me <place>' style request."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {
                    "type": "STRING",
                    "description": "City, country, landmark or any location name (e.g. 'New York', 'Mount Everest')"
                },
            },
            "required": ["city"]
        }
    },
    {
        "name": "home_screen",
        "description": (
            "Return JARVIS to its initial / home state by closing the tactical "
            "map window (or any other modal overlay) and going idle. "
            "Call this when the user says things like 'torna alla schermata "
            "iniziale', 'home', 'go back', 'chiudi la mappa', 'back to start', "
            "'reset view', 'close map'. Do NOT call this in response to a new "
            "request — only when the user explicitly asks to go back."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "open_chat",
        "description": (
            "Open the floating JARVIS chat overlay inside the main window. "
            "Use this when the user says things like 'jarvis apri la chat', "
            "'mostrami la chat', 'open chat'. The overlay can be dragged "
            "around. Does NOT replace the current view."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "show_stats",
        "description": (
            "Toggle the floating system-stats overlay (CPU, MEM, NET, GPU, "
            "TEMP, uptime, processes). Use this when the user says 'mostrami "
            "le statistiche del pc', 'mostra stats', 'apri il pannello "
            "statistiche', 'come va il pc', 'cpu ram'. NEVER call "
            "computer_settings with action='stats' for this — always call "
            "show_stats."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "whatsapp_control",
        "description": (
            "Controlla la mini-finestra di WhatsApp Web dentro JARVIS. "
            "USA SOLO per: aprire / chiudere / massimizzare / minimizzare / "
            "leggere chat la finestra. L'INVIO DI MESSAGGI NON e' qui: "
            "per inviare un messaggio usa SEMPRE il tool 'send_message' "
            "(apre la dashboard universale o invia via API/token). "
            "Comandi: 'jarvis apri whatsapp' (action=open), "
            "'jarvis mostrami le chat non lette' (action=read_chats), "
            "'jarvis chiudi whatsapp' (action=close), "
            "'jarvis whatsapp a schermo intero' (action=fullscreen), "
            "'jarvis minimizza whatsapp' (action=minimize)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "open | read_chats | fullscreen | minimize | close"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "create_shortcut",
        "description": (
            "Create a NEW persistent shortcut (scorciatoia) for the user. "
            "Use this whenever the user says 'jarvis crea scorciatoia' and "
            "provides a NAME and what it should DO. The shortcut is saved "
            "as a real .py file inside the 'scorciatoie/' folder so the user "
            "can also edit it manually. Examples of `action`: "
            "'cerca pizza margherita', 'apri chatgpt', 'avvia C:/Games/X.exe'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "name":   {"type": "STRING", "description": "Shortcut name (e.g. 'ricerca tonno')"},
                "action": {"type": "STRING", "description": "Natural language action: search query, app to open, file path, etc."},
            },
            "required": ["name", "action"]
        }
    },
    {
        "name": "run_shortcut",
        "description": (
            "Execute a previously created shortcut by name. Use when the user "
            "says 'jarvis esegui scorciatoia <nome>' or 'lancia scorciatoia "
            "<nome>'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "name": {"type": "STRING", "description": "Shortcut name or slug"},
            },
            "required": ["name"]
        }
    },
    {
        "name": "list_shortcuts",
        "description": (
            "List every shortcut created so far. Use when the user says "
            "'che scorciatoie ho', 'mostra le scorciatoie', 'list shortcuts'."
        ),
        "parameters": {"type": "OBJECT", "properties": {}, "required": []}
    },
    {
        "name": "create_desktop_shortcut",
        "description": (
            "Crea una scorciatoia FISICA sul desktop dell'utente (un vero "
            "collegamento .lnk su Windows, .desktop su Linux, .command su "
            "macOS) che, quando cliccato, esegue la scorciatoia logica "
            "corrispondente. Usa quando l'utente dice cose come "
            "'jarvis metti la scorciatoia sul desktop', 'crea un collegamento "
            "sul desktop per <nome>', 'voglio l'icona sul desktop'. "
            "Se la scorciatoia logica non esiste ancora, la crea al volo "
            "usando `action` come descrizione."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "name":   {"type": "STRING", "description": "Nome visibile del collegamento sul desktop"},
                "action": {"type": "STRING", "description": "(Opzionale) cosa deve fare, se la scorciatoia non esiste ancora"},
                "icon":   {"type": "STRING", "description": "(Opzionale) percorso a file .ico / .png per l'icona"},
            },
            "required": ["name"]
        }
    },
    {
        "name": "remove_desktop_shortcut",
        "description": (
            "Rimuove il collegamento fisico dal desktop lasciando "
            "intatta la scorciatoia logica in scorciatoie/. Usa quando "
            "l'utente dice 'togli la scorciatoia dal desktop'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "name": {"type": "STRING", "description": "Nome del collegamento sul desktop"},
            },
            "required": ["name"]
        }
    },
    {
        "name": "save_memory",
        "description": (
            "Save an important personal fact about the user to long-term memory. "
            "Call this silently whenever the user reveals something worth remembering: "
            "name, age, city, job, preferences, hobbies, relationships, projects, or future plans. "
            "Do NOT call for: weather, reminders, searches, or one-time commands. "
            "Do NOT announce that you are saving — just call it silently. "
            "Values must be in English regardless of the conversation language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": (
                        "identity — name, age, birthday, city, job, language, nationality | "
                        "preferences — favorite food/color/music/film/game/sport, hobbies | "
                        "projects — active projects, goals, things being built | "
                        "relationships — friends, family, partner, colleagues | "
                        "wishes — future plans, things to buy, travel dreams | "
                        "notes — habits, schedule, anything else worth remembering"
                    )
                },
                "key":   {"type": "STRING", "description": "Short snake_case key (e.g. name, favorite_food, sister_name)"},
                "value": {"type": "STRING", "description": "Concise value in English (e.g. NotVortex, pizza, older sister)"},
            },
            "required": ["category", "key", "value"]
        }
    },
]


class JarvisLive:

    def __init__(self, ui: JarvisUI):
        self.ui             = ui
        self.session        = None
        self.audio_in_queue = None
        self.out_queue      = None
        self._loop          = None
        self._is_speaking   = False
        self._speaking_lock = threading.Lock()
        # Dedup per il bug "due annunci": l'evento di nuovo messaggio puo'
        # arrivare due volte (poller HTTP + overlay UI WhatsApp Web).
        # Salviamo l'ultimo (platform, sender, body[:40]) e l'ora.
        self._last_notif_key: tuple[str, str, str] | None = None
        self._last_notif_ts: float = 0.0
        self._notif_lock = threading.Lock()
        self.ui.on_text_command = self._on_text_command
        # Registra callback per nuovi messaggi WhatsApp dal mini-overlay UI.
        try:
            self.ui.set_on_whatsapp_new_message(
                lambda contact: self._on_new_message("whatsapp", contact)
            )
        except Exception as _e:
            print(f"[JARVIS] WA hook skipped: {_e}")

    def _on_new_message(self, platform: str, contact_name: str,
                        body: str = "", kind: str = "text",
                        audio_url: str = "", audio_path: str = ""):
        """Nuovo messaggio in arrivo su una delle piattaforme collegate
        (WhatsApp / Telegram / Discord / Instagram).

        Inietta nel Gemini Live un turno di sistema che:
          1) annuncia vocalmente l'arrivo del messaggio.
          2) se e' testo -> chiede se vuole sapere il contenuto;
             se conferma, leggi il body.
          3) se e' vocale -> chiede se vuole riprodurre il vocale;
             se conferma, chiama play_last_voice.
          4) ricorda al modello che "rispondi con <testo>" instrada a
             send_message verso lo stesso contatto/piattaforma.
        """
        if not contact_name or not platform or not self._loop or not self.session:
            return
        cn = str(contact_name).replace("\n", " ").strip()
        plat = str(platform).strip().lower()
        plat_label = plat.capitalize()
        body_clean = (body or "").replace("\n", " ").strip()
        # ---- Dedup: ignora eventi duplicati entro 8s (poller HTTP + overlay UI)
        key = (plat, cn, body_clean[:40])
        now_ts = time.time()
        with self._notif_lock:
            if (self._last_notif_key == key
                    and (now_ts - self._last_notif_ts) < 8.0):
                return
            self._last_notif_key = key
            self._last_notif_ts = now_ts
        # IMPORTANTE: NON chiamare set_last_incoming qui senza body/kind/audio,
        # altrimenti sovrascriviamo il record completo gia' impostato dal
        # poller (perdendo kind='voice' e audio_url -> "Non ho un messaggio
        # vocale recente da riprodurre"). Il poller lo gestisce gia'.

        # ---- Animazione UI / Toast in alto a destra (qualsiasi piattaforma)
        try:
            if hasattr(self.ui, "show_message_notification"):
                self.ui.show_message_notification(plat, cn)
        except Exception as _e:
            print(f"[JARVIS] notif anim skipped: {_e}")

        # ---- Costruzione del contesto da iniettare a Gemini Live ----------
        if kind == "voice":
            ctx = (
                f"[NUOVO MESSAGGIO VOCALE {plat_label.upper()}]\n"
                f"E' arrivato un nuovo messaggio VOCALE su {plat_label} "
                f"dal contatto: {cn}.\n"
                f"ISTRUZIONI (in italiano, una sola breve frase per turno):\n"
                f"1) Annuncia: \"Signore, {cn} le ha inviato un messaggio "
                f"vocale su {plat_label}. Vuole che lo riproduca?\".\n"
                f"2) Se l'utente risponde affermativamente "
                f"(es. \"si\", \"sì\", \"riproduci\", \"ascolta\", \"play\", "
                f"\"fammelo sentire\"), DEVI chiamare IMMEDIATAMENTE il tool "
                f"'play_last_voice' con parameters={{\"platform\": \"{plat}\"}}.\n"
                f"3) Se l'utente dice \"rispondi con <testo>\", \"rispondigli "
                f"<testo>\", \"digli <testo>\" o equivalenti, chiama "
                f"send_message con receiver=\"{cn}\", platform=\"{plat}\", "
                f"message_text=<testo>. Non chiedere conferma."
            )
        elif body_clean:
            # Tronca per sicurezza nel prompt (max 600 char)
            body_for_prompt = body_clean if len(body_clean) <= 600 else body_clean[:600] + "..."
            ctx = (
                f"[NUOVO MESSAGGIO {plat_label.upper()}]\n"
                f"E' arrivato un nuovo messaggio TESTO su {plat_label} "
                f"dal contatto: {cn}.\n"
                f"Contenuto del messaggio (NON leggerlo subito): "
                f"\"{body_for_prompt}\"\n"
                f"ISTRUZIONI (in italiano, una sola breve frase per turno):\n"
                f"1) Annuncia: \"Signore, nuovo messaggio {plat_label} da "
                f"{cn}. Vuole sapere il contenuto?\". NON leggere ancora il "
                f"contenuto del messaggio.\n"
                f"2) Se l'utente risponde affermativamente "
                f"(es. \"si\", \"sì\", \"certo\", \"dimmi\", \"leggimelo\", "
                f"\"cosa dice\", \"cos'ha scritto\", \"leggilo\"), allora "
                f"leggi il contenuto del messaggio sopra riportato, in modo "
                f"naturale: \"{cn} ha scritto: <contenuto>\".\n"
                f"3) Se l'utente dice \"rispondi con <testo>\", \"rispondigli "
                f"<testo>\", \"digli <testo>\" o equivalenti, chiama "
                f"IMMEDIATAMENTE send_message con receiver=\"{cn}\", "
                f"platform=\"{plat}\", message_text=<testo>. Non chiedere "
                f"conferma, invia subito.\n"
                f"4) Dopo l'invio, conferma brevemente: \"Risposta inviata "
                f"a {cn} su {plat_label}, signore.\""
            )
        else:
            ctx = (
                f"[NUOVO MESSAGGIO {plat_label.upper()}]\n"
                f"E' arrivato un nuovo messaggio su {plat_label} dal "
                f"contatto: {cn}.\n"
                f"ISTRUZIONI:\n"
                f"1) Annuncia: \"Signore, nuovo messaggio {plat_label} da "
                f"{cn}\".\n"
                f"2) Se l'utente dice \"rispondi con <testo>\", chiama "
                f"send_message con receiver=\"{cn}\", platform=\"{plat}\", "
                f"message_text=<testo>."
            )
        try:
            asyncio.run_coroutine_threadsafe(
                self.session.send_client_content(
                    turns={"parts": [{"text": ctx}]},
                    turn_complete=True
                ),
                self._loop
            )
        except Exception as e:
            print(f"[JARVIS] new-msg inject ctx err: {e}")

    # Backward-compat alias (l'UI lo chiama ancora come _on_wa_new_message
    # nelle versioni vecchie).
    def _on_wa_new_message(self, contact_name: str):
        self._on_new_message("whatsapp", contact_name)

    def _on_text_command(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING")

    def speak(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        self.speak(f"Sir, {tool_name} encountered an error. {short}")

    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime

        memory     = load_memory()
        mem_str    = format_memory_for_prompt(memory)
        sys_prompt = _load_system_prompt()

        now      = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")
        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Use this to calculate exact times for reminders.\n\n"
        )

        parts = [time_ctx]
        if mem_str:
            parts.append(mem_str)

        # Iniettiamo l'elenco delle scorciatoie persistenti cosi'
        # JARVIS ricorda quali esistono dopo un riavvio.
        try:
            from actions.shortcut_creator import _load_index as _sc_index
            sc = (_sc_index() or {}).get("shortcuts") or {}
            if sc:
                lines = ["[SCORCIATOIE DISPONIBILI - usa run_shortcut con il name]"]
                for slug, meta in sc.items():
                    nm = meta.get("name", slug)
                    kind = (meta.get("action") or {}).get("kind", "?")
                    raw = (meta.get("raw") or "").strip()
                    lines.append(f"- name: \"{nm}\" (slug: {slug}, kind: {kind}) -> {raw[:80]}")
                parts.append("\n".join(lines) + "\n")
        except Exception as _e:
            print(f"[Shortcuts] inject error: {_e}")

        parts.append(sys_prompt)

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
            session_resumption=types.SessionResumptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Charon"
                    )
                )
            ),
        )

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        print(f"[JARVIS] 🔧 {name}  {args}")
        self.ui.set_state("THINKING")

        # ── Auto-close JARVIS map window when an unrelated command is issued ──
        # If the user is invoking ANY tool other than `jarvis_map` itself,
        # `home_screen` or the silent `save_memory`, dismiss the tactical
        # map and return to the initial state.
        # ECCEZIONI: open_chat / show_stats sono overlay aggiuntivi -> NON
        # devono chiudere la mappa (richiesta utente).
        _MAP_KEEP_OPEN = (
            "jarvis_map", "home_screen", "save_memory",
            "open_chat", "show_stats", "whatsapp_control",
        )
        if name not in _MAP_KEEP_OPEN:
            try:
                from actions.jarvis_map import close_jarvis_map
                if close_jarvis_map():
                    print("[JARVIS] 🗺️ Closed JARVIS map (unrelated command).")
            except Exception as _e:
                print(f"[JARVIS] map close skipped: {_e}")

        if name == "save_memory":
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            if key and value:
                update_memory({category: {key: {"value": value}}})
                print(f"[Memory] 💾 save_memory: {category}/{key} = {value}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "ok", "silent": True}
            )

        loop   = asyncio.get_event_loop()
        result = "Done."

        try:
            if name == "open_app":
                r = await loop.run_in_executor(None, lambda: open_app(parameters=args, response=None, player=self.ui))
                result = r or f"Opened {args.get('app_name')}."

            elif name == "weather_report":
                r = await loop.run_in_executor(None, lambda: weather_action(parameters=args, player=self.ui))
                result = r or "Weather delivered."

            elif name == "browser_control":
                r = await loop.run_in_executor(None, lambda: browser_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "file_controller":
                r = await loop.run_in_executor(None, lambda: file_controller(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "send_message":
                r = await loop.run_in_executor(None, lambda: send_message(parameters=args, response=None, player=self.ui, session_memory=None))
                result = r or f"Message sent to {args.get('receiver')}."

            elif name == "check_messages":
                r = await loop.run_in_executor(None, lambda: check_messages(parameters=args, response=None, player=self.ui, session_memory=None))
                result = r or "Nessun messaggio non letto."

            elif name == "read_last_notifications":
                r = await loop.run_in_executor(None, lambda: read_last_notifications(parameters=args, response=None, player=self.ui, session_memory=None))
                result = r or "Nessuna notifica recente."

            elif name == "play_last_voice":
                r = await loop.run_in_executor(None, lambda: play_last_voice(parameters=args, response=None, player=self.ui, session_memory=None))
                result = r or "Riproduzione vocale eseguita."

            elif name == "record_whatsapp_voice":
                r = await loop.run_in_executor(None, lambda: record_whatsapp_voice(parameters=args, response=None, player=self.ui, session_memory=None))
                result = r or "Vocale WhatsApp inviato."

            elif name == "suggest_reply":
                r = await loop.run_in_executor(None, lambda: suggest_reply(parameters=args, response=None, player=self.ui, session_memory=None))
                result = r or "Non sono riuscito a suggerire risposte."

            elif name == "reply_with_picked":
                r = await loop.run_in_executor(None, lambda: reply_with_picked(parameters=args, response=None, player=self.ui, session_memory=None))
                result = r or "Risposta inviata."

            elif name == "start_call":
                r = await loop.run_in_executor(None, lambda: start_call(parameters=args, response=None, player=self.ui, session_memory=None))
                result = r or "Chiamata avviata."

            elif name == "reminder":
                r = await loop.run_in_executor(None, lambda: reminder(parameters=args, response=None, player=self.ui))
                result = r or "Reminder set."

            elif name == "youtube_video":
                r = await loop.run_in_executor(None, lambda: youtube_video(parameters=args, response=None, player=self.ui))
                result = r or "Done."
            elif name == "file_processor":
                if not args.get("file_path") and self.ui.current_file:
                    args["file_path"] = self.ui.current_file
                r = await loop.run_in_executor(
                    None,
                    lambda: file_processor(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Done."


            elif name == "screen_process":
                threading.Thread(
                    target=screen_process,
                    kwargs={"parameters": args, "response": None,
                            "player": self.ui, "session_memory": None},
                    daemon=True
                ).start()
                result = "Vision module activated. Stay completely silent — vision module will speak directly."

            elif name == "computer_settings":
                r = await loop.run_in_executor(None, lambda: computer_settings(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "desktop_control":
                r = await loop.run_in_executor(None, lambda: desktop_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "code_helper":
                r = await loop.run_in_executor(None, lambda: code_helper(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "dev_agent":
                r = await loop.run_in_executor(None, lambda: dev_agent(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "agent_task":
                from agent.task_queue import get_queue, TaskPriority
                priority_map = {"low": TaskPriority.LOW, "normal": TaskPriority.NORMAL, "high": TaskPriority.HIGH}
                priority = priority_map.get(args.get("priority", "normal").lower(), TaskPriority.NORMAL)
                task_id  = get_queue().submit(goal=args.get("goal", ""), priority=priority, speak=self.speak)
                result   = f"Task started (ID: {task_id})."

            elif name == "web_search":
                r = await loop.run_in_executor(None, lambda: web_search_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "computer_control":
                r = await loop.run_in_executor(None, lambda: computer_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "game_updater":
                r = await loop.run_in_executor(None, lambda: game_updater(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "flight_finder":
                r = await loop.run_in_executor(None, lambda: flight_finder(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "spotify_control":
                r = await loop.run_in_executor(None, lambda: spotify_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "jarvis_map":
                r = await loop.run_in_executor(None, lambda: jarvis_map(parameters=args, player=self.ui))
                result = r or "Map deployed."

            elif name == "qr_from_screen":
                r = await loop.run_in_executor(
                    None, lambda: qr_from_screen(parameters=args, player=self.ui)
                )
                result = r or "QR generato."

            elif name == "open_chat":
                try:
                    self.ui.show_chat_overlay()
                    result = "Apro la chat, signore."
                except Exception as e:
                    result = f"Errore apertura chat: {e}"

            elif name == "show_stats":
                try:
                    self.ui.show_stats_overlay()
                    result = "Mostro le statistiche, signore."
                except Exception as e:
                    result = f"Errore stats: {e}"

            elif name == "whatsapp_control":
                try:
                    sub = (args.get("action") or "open").lower().strip()
                    self.ui.show_whatsapp_overlay(sub, "", "")
                    if sub == "read_chats":
                        result = "Sto leggendo le chat WhatsApp non lette, signore."
                    elif sub in ("close", "hide", "chiudi"):
                        result = "Chiudo WhatsApp, signore."
                    elif sub in ("fullscreen", "maximize", "schermo_intero", "fullscreen_on"):
                        result = "WhatsApp a schermo intero, signore."
                    elif sub in ("minimize", "windowed", "restore", "finestra"):
                        result = "Rimetto WhatsApp in finestrella, signore."
                    else:
                        result = "Apro WhatsApp, signore."
                except Exception as e:
                    result = f"Errore WhatsApp: {e}"

            elif name == "create_shortcut":
                r = await loop.run_in_executor(
                    None, lambda: shortcut_create(parameters=args, player=self.ui)
                )
                result = r or "Scorciatoia creata."

            elif name == "run_shortcut":
                r = await loop.run_in_executor(
                    None, lambda: shortcut_run(parameters=args, player=self.ui)
                )
                result = r or "Scorciatoia eseguita."

            elif name == "list_shortcuts":
                r = await loop.run_in_executor(
                    None, lambda: shortcut_list(parameters=args, player=self.ui)
                )
                result = r or "Nessuna scorciatoia."

            elif name == "create_desktop_shortcut":
                r = await loop.run_in_executor(
                    None, lambda: shortcut_desktop_create(parameters=args, player=self.ui)
                )
                result = r or "Collegamento sul desktop creato."

            elif name == "remove_desktop_shortcut":
                r = await loop.run_in_executor(
                    None, lambda: shortcut_desktop_remove(parameters=args, player=self.ui)
                )
                result = r or "Collegamento rimosso dal desktop."

            elif name == "home_screen":
                # Return to initial JARVIS state: close ALL overlays
                # (map, chat, stats, whatsapp) e ripristina il layout iniziale.
                try:
                    from actions.jarvis_map import close_jarvis_map
                    close_jarvis_map()
                except Exception:
                    pass
                try:
                    self.ui.return_home()
                except Exception:
                    pass
                result = "Returning to home screen, sir."

            elif name == "shutdown_jarvis":
                self.ui.write_log("SYS: Shutdown requested.")
                self.speak("Goodbye, sir.")

                def _shutdown():
                    import time, sys, os
                    time.sleep(1)
                    os._exit(0)

                threading.Thread(target=_shutdown, daemon=True).start()
            elif name == "addon_macro_panel":
                # Apre il pannello grafico delle scorciatoie nella finestra
                try:
                    self.ui._macro_sig.emit()
                    result = "Pannello scorciatoie aperto, signore."
                except Exception as e:
                    result = f"Pannello non disponibile: {e}"

            elif name.startswith("addon_"):
                # Nuovi addon vocali (addons/voice_bridge.py)
                r = await loop.run_in_executor(
                    None, lambda: execute_addon(name, args)
                )
                result = r or "Addon eseguito."

            else:
                result = f"Unknown tool: {name}"

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            self.speak_error(name, e)

        if not self.ui.muted:
            self.ui.set_state("LISTENING")

        print(f"[JARVIS] 📤 {name} → {str(result)[:80]}")

        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result}
        )

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            await self.session.send_realtime_input(media=msg)

    async def _listen_audio(self):
        print("[JARVIS] 🎤 Mic started")
        loop = asyncio.get_running_loop()

        def _enqueue_audio(payload):
            # BUGFIX: put_nowait su coda bounded (maxsize=10) sollevava
            # asyncio.QueueFull dentro l'event loop ad ogni chunk quando la
            # rete era lenta -> traceback a ripetizione + audio perso.
            # Ora scartiamo il frame piu' vecchio (la voce e' real-time,
            # meglio perdere un frame vecchio che accumulare ritardo).
            try:
                self.out_queue.put_nowait(payload)
            except asyncio.QueueFull:
                try:
                    self.out_queue.get_nowait()
                    self.out_queue.put_nowait(payload)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass

        def callback(indata, frames, time_info, status):
            with self._speaking_lock:
                jarvis_speaking = self._is_speaking
            if not jarvis_speaking and not self.ui.muted:
                data = indata.tobytes()
                loop.call_soon_threadsafe(
                    _enqueue_audio,
                    {"data": data, "mime_type": "audio/pcm"}
                )

        try:
            with sd.InputStream(
                samplerate=SEND_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                callback=callback,
            ):
                print("[JARVIS] 🎤 Mic stream open")
                while True:
                    # CPU-friendly idle: il microfono e' guidato dal callback
                    # di sounddevice (event-driven), questo task serve solo
                    # a tenere il TaskGroup vivo, quindi possiamo dormire a
                    # lungo senza impattare la latenza audio.
                    await asyncio.sleep(0.5)
        except Exception as e:
            print(f"[JARVIS] ❌ Mic: {e}")
            raise

    async def _receive_audio(self):
        print("[JARVIS] 👂 Recv started")
        out_buf, in_buf = [], []

        try:
            while True:
                got_any = False
                async for response in self.session.receive():
                    got_any = True

                    if response.data:
                        self.audio_in_queue.put_nowait(response.data)

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            self.set_speaking(True)
                            txt = sc.output_transcription.text.strip()
                            if txt:
                                out_buf.append(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = sc.input_transcription.text.strip()
                            if txt:
                                in_buf.append(txt)

                        if sc.turn_complete:
                            self.set_speaking(False)

                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                self.ui.write_log(f"You: {full_in}")
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                self.ui.write_log(f"Jarvis: {full_out}")
                            out_buf = []

                            # Fast-path scorciatoie vocali (ADDITIVO):
                            # match ESATTO parola-per-parola -> la sequenza
                            # di addon parte subito, senza attendere il modello.
                            if full_in:
                                try:
                                    from addons.voice_macros import try_fast_path
                                    try_fast_path(full_in, self)
                                except Exception:
                                    pass

                            if full_in and len(full_in) > 5:
                                threading.Thread(
                                    target=_update_memory_async,
                                    args=(full_in, full_out),
                                    daemon=True
                                ).start()

                    if response.tool_call:
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            print(f"[JARVIS] 📞 {fc.name}")
                            fr = await self._execute_tool(fc)
                            fn_responses.append(fr)
                        await self.session.send_tool_response(
                            function_responses=fn_responses
                        )

                # BUGFIX: se receive() termina senza yield ne' eccezioni
                # (stream chiuso dal server) il while True rientrava subito
                # nel generatore -> spin tight-loop a CPU 100%.
                if not got_any:
                    await asyncio.sleep(0.05)

        except Exception as e:
            print(f"[JARVIS] ❌ Recv: {e}")
            traceback.print_exc()
            raise

    async def _play_audio(self):
        print("[JARVIS] 🔊 Play started")
        loop = asyncio.get_running_loop()

        stream = sd.RawOutputStream(
            samplerate=RECEIVE_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK_SIZE,
        )
        stream.start()
        try:
            while True:
                chunk = await self.audio_in_queue.get()
                self.set_speaking(True)
                await asyncio.to_thread(stream.write, chunk)
        except Exception as e:
            print(f"[JARVIS] ❌ Play: {e}")
            raise
        finally:
            self.set_speaking(False)
            stream.stop()
            stream.close()

    async def run(self):
        client = genai.Client(
            api_key=_get_api_key(),
            http_options={"api_version": "v1beta"}
        )

        while True:
            try:
                print("[JARVIS] 🔌 Connecting...")
                self.ui.set_state("THINKING")
                config = self._build_config()

                async with (
                    client.aio.live.connect(model=LIVE_MODEL, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session        = session
                    self._loop          = asyncio.get_event_loop()
                    self.audio_in_queue = asyncio.Queue()
                    self.out_queue      = asyncio.Queue(maxsize=10)

                    print("[JARVIS] ✅ Connected.")
                    self.ui.set_state("LISTENING")
                    self.ui.write_log("SYS: JARVIS online.")

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())

                    # Avvia i poller di notifiche per WhatsApp / Telegram /
                    # Discord / Instagram. Idempotente: non riparte se
                    # gia' attivo. Il secondo argomento e' la callback
                    # invocata ad ogni nuovo messaggio in arrivo:
                    # informa il modello Gemini cosi' che "rispondi con X"
                    # possa essere instradato a send_message correttamente.
                    try:
                        start_notification_pollers(
                            self.speak,
                            on_new_message=self._on_new_message,
                        )
                    except Exception as _e:
                        print(f"[JARVIS] notify pollers skipped: {_e}")
                    
            except Exception as e:
                print(f"[JARVIS] ⚠️ {e}")
                traceback.print_exc()

            self.set_speaking(False)
            self.ui.set_state("THINKING")
            print("[JARVIS] 🔄 Reconnecting in 3s...")
            await asyncio.sleep(3)

# ---------------------------------------------------------------------------
# Addon vocali (ADDITIVO): collega le ~70 funzioni di addons/ ai comandi
# vocali come tool Gemini Live. Se gli addon non sono presenti, JARVIS
# funziona esattamente come prima.
# ---------------------------------------------------------------------------
try:
    from addons.voice_bridge import build_tool_declarations, execute_addon
    TOOL_DECLARATIONS.extend(build_tool_declarations())
    print(f"[JARVIS] ✅ {len(build_tool_declarations())} addon vocali collegati")
except Exception as _e:
    def execute_addon(name, args):
        return f"Addons non disponibili: {_e}"
    print(f"[JARVIS] ⚠️ addons non caricati: {_e}")


def main():
    ui = JarvisUI("face.png")
    # Collega la UI principale al modulo jarvis_map cosi' la mappa
    # viene renderizzata DENTRO la stessa finestra (no nuova scheda).
    try:
        from actions.jarvis_map import set_ui_reference
        set_ui_reference(ui)
    except Exception as _e:
        print(f"[JARVIS] map UI link skipped: {_e}")

    def runner():
        ui.wait_for_api_key()
        jarvis = JarvisLive(ui)
        try:
            asyncio.run(jarvis.run())
        except KeyboardInterrupt:
            print("\n🔴 Shutting down...")

    threading.Thread(target=runner, daemon=True).start()
    ui.root.mainloop()


if __name__ == "__main__":
    main()
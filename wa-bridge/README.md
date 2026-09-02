# wa-bridge (JARVIS + WhatsApp Web)

Bridge HTTP locale che collega **JARVIS** a **WhatsApp Web** via `whatsapp-web.js`.
Espone un piccolo server Express su `http://127.0.0.1:8765` con questi endpoint:

| Metodo | Path              | Descrizione                                            |
|--------|-------------------|--------------------------------------------------------|
| GET    | `/status`         | `{ ready, qr, online, error }`                         |
| GET    | `/chats`          | lista chat                                             |
| GET    | `/unread`         | messaggi non letti (li **consuma** dalla coda)         |
| POST   | `/send`           | `{ to \| name, text }` invia un messaggio di testo     |
| POST   | `/sendVoice`      | multipart `file` + `to` — invia un **vocale**          |
| GET    | `/media/:msgId`   | scarica un allegato audio ricevuto                     |

## Avvio (una tantum)

```bash
cd wa-bridge
npm install
npm start
```

La **prima volta** viene stampato in console un **QR** da scansionare dal telefono
(WhatsApp → Impostazioni → Dispositivi collegati). La sessione viene salvata in
`.wwebjs_auth/` — successive esecuzioni **NON richiedono più il QR**.

## Variabili d'ambiente

- `WA_HOST` (default `127.0.0.1`)
- `WA_PORT` (default `8765`)
- `CHROME_PATH` (path a `chrome.exe` / `msedge` se puppeteer non trova un browser
  di sistema — utile su Windows con path che contengono spazi).

## Integrazione con JARVIS

`actions/whatsapp_bridge.py` legge la variabile `WHATSAPP_BRIDGE_URL` dal file
`.env` della root (default `http://127.0.0.1:8765`), quindi assicurati che il
bridge sia in esecuzione **prima** di lanciare JARVIS.

Quando dici **"Jarvis apri WhatsApp"** o **"Jarvis tendina WhatsApp"**, JARVIS
non apre più l'app desktop: apre una **tendina HUD** (slide-in da destra)
che carica WhatsApp Web in un webview e mostra il badge dei messaggi non letti.

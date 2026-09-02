// wa-bridge/server.js
// JARVIS - bridge HTTP locale per WhatsApp via whatsapp-web.js.
// Esposto su http://127.0.0.1:8765 (override con env WA_PORT / WA_HOST).
//
// Endpoint:
//   GET  /status   -> { ready, qr, online:true }
//   GET  /chats    -> { chats: [{ id, name, isGroup }] }
//   GET  /unread   -> { messages: [{ id, from, body }] }
//   POST /send     -> body { to|name, text }  invio messaggio
//
// La sessione viene salvata in `wa-bridge/.wwebjs_auth/` cosi' il QR
// viene chiesto SOLO al primo avvio.
//
// === Fix per Windows ===
// Su Windows 10/11, il Chromium "bundled" di puppeteer puo' crashare
// con codice 3221226505 (0xC0000409 STATUS_STACK_BUFFER_OVERRUN),
// soprattutto se il path contiene SPAZI o caratteri non-ASCII (es.
// "C:\\Users\\windows\\Downloads\\EJAAAAA DIO\\wa-bridge").
// Soluzione: usiamo il Chrome / Edge installato di sistema invece di
// quello scaricato da puppeteer. Cerchiamo l'eseguibile nelle posizioni
// canoniche; in alternativa puoi passare CHROME_PATH come env var.

const express = require("express");
const qrcode  = require("qrcode-terminal");
const fs      = require("fs");
const path    = require("path");
const { Client, LocalAuth } = require("whatsapp-web.js");

const HOST = process.env.WA_HOST || "127.0.0.1";
const PORT = parseInt(process.env.WA_PORT || "8765", 10);

function findSystemBrowser() {
  if (process.env.CHROME_PATH && fs.existsSync(process.env.CHROME_PATH)) {
    return process.env.CHROME_PATH;
  }
  const candidates = [];
  if (process.platform === "win32") {
    const PF   = process.env["ProgramFiles"]        || "C:\\Program Files";
    const PFX  = process.env["ProgramFiles(x86)"]   || "C:\\Program Files (x86)";
    const LAD  = process.env["LOCALAPPDATA"]        || "";
    candidates.push(
      path.join(PF,  "Google\\Chrome\\Application\\chrome.exe"),
      path.join(PFX, "Google\\Chrome\\Application\\chrome.exe"),
      LAD && path.join(LAD, "Google\\Chrome\\Application\\chrome.exe"),
      path.join(PF,  "Microsoft\\Edge\\Application\\msedge.exe"),
      path.join(PFX, "Microsoft\\Edge\\Application\\msedge.exe"),
    );
  } else if (process.platform === "darwin") {
    candidates.push(
      "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
      "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    );
  } else {
    candidates.push(
      "/usr/bin/google-chrome",
      "/usr/bin/chromium",
      "/usr/bin/chromium-browser",
      "/usr/bin/microsoft-edge",
    );
  }
  for (const p of candidates.filter(Boolean)) {
    try { if (fs.existsSync(p)) return p; } catch (_) {}
  }
  return null;
}

const SYS_BROWSER = findSystemBrowser();
if (SYS_BROWSER) {
  console.log(`[wa-bridge] usero' il browser di sistema: ${SYS_BROWSER}`);
} else {
  console.warn("[wa-bridge] Browser di sistema non trovato (Chrome/Edge). " +
               "Verra' usato il Chromium bundled di puppeteer (puo' fallire su " +
               "Windows se il path contiene spazi). Installa Chrome o imposta " +
               "la variabile CHROME_PATH=...\\chrome.exe.");
}

const app = express();
app.use(express.json({ limit: "1mb" }));

let lastQR    = null;
let isReady   = false;
let initError = null;          // ultimo errore di avvio puppeteer
const unread  = [];
const seenIds = new Set();

const puppeteerOpts = {
  headless: true,
  args: [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-extensions",
    "--no-first-run",
    "--no-default-browser-check",
  ],
};
if (SYS_BROWSER) puppeteerOpts.executablePath = SYS_BROWSER;

const client = new Client({
  authStrategy: new LocalAuth({ clientId: "jarvis" }),
  puppeteer: puppeteerOpts,
});

client.on("qr", (qr) => {
  lastQR = qr;
  console.log("\n[wa-bridge] Scansiona questo QR con WhatsApp > Dispositivi collegati:\n");
  qrcode.generate(qr, { small: true });
});
client.on("ready", () => {
  isReady = true; lastQR = null; initError = null;
  console.log("[wa-bridge] WhatsApp pronto.");
});
client.on("auth_failure", (m) => { initError = "auth_failure: " + m; console.error(initError); });
client.on("disconnected", (r) => { isReady = false; console.warn("[wa-bridge] disconnesso", r); });

client.on("message", async (msg) => {
  try {
    if (msg.fromMe) return;
    if (seenIds.has(msg.id._serialized)) return;
    seenIds.add(msg.id._serialized);
    let from = msg.from;
    try {
      const c = await msg.getChat();
      from = (c && c.name) ? c.name : from;
    } catch (_) {}
    unread.push({ id: msg.id._serialized, from, body: msg.body || "" });
    if (unread.length > 500) unread.splice(0, unread.length - 250);
  } catch (e) {
    console.error("[wa-bridge] err msg", e);
  }
});

client.initialize().catch((e) => {
  initError = String(e && e.message || e);
  console.error("[wa-bridge] init err", e);
  console.error(
    "\nSUGGERIMENTI:\n" +
    " 1) Installa Google Chrome (o Microsoft Edge) e riavvia.\n" +
    " 2) Sposta la cartella in un percorso SENZA spazi o caratteri " +
    "speciali (es. C:\\jarvis\\wa-bridge invece di 'EJAAAAA DIO').\n" +
    " 3) Imposta CHROME_PATH puntando a chrome.exe e riavvia.\n" +
    " 4) Disattiva temporaneamente l'antivirus al primo avvio."
  );
});

// ---------------- API ----------------
app.get("/status", (_req, res) =>
  res.json({ ready: isReady, qr: lastQR, online: true, error: initError })
);

app.get("/chats", async (_req, res) => {
  if (!isReady) return res.json({ chats: [], ready: false, error: initError });
  try {
    const chats = await client.getChats();
    res.json({
      chats: chats.map((c) => ({
        id:   c.id && c.id._serialized ? c.id._serialized : String(c.id || ""),
        name: c.name || (c.formattedTitle) || (c.id && c.id.user) || "(chat)",
        isGroup: !!c.isGroup,
      })),
    });
  } catch (e) {
    res.status(500).json({ error: String(e) });
  }
});

app.get("/unread", (_req, res) => {
  const out = unread.splice(0, unread.length);
  res.json({ messages: out });
});

app.post("/send", async (req, res) => {
  if (!isReady) return res.status(503).json({ ok: false, error: "WhatsApp non pronto, scansiona il QR." });
  const { to, name, text } = req.body || {};
  const message = (text || "").toString();
  if (!message) return res.status(400).json({ ok: false, error: "text mancante" });
  try {
    let target = (to || "").toString();
    if (!target.includes("@")) {
      const chats = await client.getChats();
      const needle = ((name || to) || "").toString().toLowerCase();
      const match = chats.find((c) => (c.name || "").toLowerCase() === needle)
                 || chats.find((c) => (c.name || "").toLowerCase().includes(needle));
      if (!match) return res.status(404).json({ ok: false, error: "chat non trovata" });
      target = match.id._serialized;
    }
    await client.sendMessage(target, message);
    res.json({ ok: true });
  } catch (e) {
    res.status(500).json({ ok: false, error: String(e) });
  }
});

// --- Voice addon (sendVoice + /media/:msgId) ---
try {
  require("./voice_addon")(app, client);
  console.log("[wa-bridge] voice_addon attivo (POST /sendVoice, GET /media/:id)");
} catch (e) {
  console.warn("[wa-bridge] voice_addon non caricato:", e.message);
}

app.listen(PORT, HOST, () => {
  console.log(`[wa-bridge] listening on http://${HOST}:${PORT}`);
});

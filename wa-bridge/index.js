// wa-bridge/index.js
// Bridge HTTP locale per JARVIS.
// Espone su http://127.0.0.1:8765:
//   GET  /chats   -> lista nomi chat
//   GET  /unread  -> messaggi arrivati da quando il bridge gira (consumati)
//   POST /send    -> { to, text } invia messaggio (matching per nome chat)
//   GET  /status  -> stato connessione
//
// Avvio (la PRIMA volta scansiona il QR code dal telefono, dopo zero login):
//   npm install
//   npm start
//
// La sessione viene salvata nella cartella .wwebjs_auth/ e funziona da "token"
// permanente.

const { Client, LocalAuth } = require("whatsapp-web.js");
const qrcode = require("qrcode-terminal");
const express = require("express");

const PORT = parseInt(process.env.PORT || "8765", 10);

const client = new Client({
  authStrategy: new LocalAuth({ clientId: "jarvis" }),
  puppeteer: {
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
  },
});

let ready = false;
let lastQr = null;
const incomingQueue = []; // { id, from, body, timestamp }

client.on("qr", (qr) => {
  lastQr = qr;
  console.log("\n[wa-bridge] Scansiona questo QR dal tuo telefono "
              + "(WhatsApp > Impostazioni > Dispositivi collegati):\n");
  qrcode.generate(qr, { small: true });
});

client.on("ready", () => {
  ready = true;
  console.log("[wa-bridge] Pronto. Sessione salvata, login una sola volta.");
});

client.on("authenticated", () => {
  console.log("[wa-bridge] Autenticato.");
});

client.on("auth_failure", (m) => {
  console.error("[wa-bridge] Auth fallito:", m);
});

client.on("disconnected", (r) => {
  ready = false;
  console.warn("[wa-bridge] Disconnesso:", r);
});

client.on("message", (m) => {
  // ignora i messaggi inviati da te stesso
  if (m.fromMe) return;
  incomingQueue.push({
    id: m.id && m.id._serialized,
    from: (m._data && m._data.notifyName) || m.from,
    body: m.body || "",
    timestamp: m.timestamp || Math.floor(Date.now() / 1000),
  });
  // evita crescita illimitata
  if (incomingQueue.length > 500) incomingQueue.splice(0, incomingQueue.length - 250);
});

const app = express();
app.use(express.json({ limit: "1mb" }));

app.get("/status", (_req, res) => {
  res.json({ ready, hasQr: !!lastQr });
});

app.get("/chats", async (_req, res) => {
  if (!ready) return res.json({ chats: [] });
  try {
    const chats = await client.getChats();
    res.json({
      chats: chats.map((c) => ({
        name: c.name || c.formattedTitle || c.id._serialized,
        id: c.id._serialized,
        isGroup: !!c.isGroup,
        unread: c.unreadCount || 0,
      })).map((c) => c.name),  // JARVIS usa una lista di stringhe
    });
  } catch (e) {
    res.status(500).json({ error: String(e) });
  }
});

// JARVIS chiama /unread e CONSUMA la coda (toglie i messaggi gia' notificati).
app.get("/unread", (_req, res) => {
  const messages = incomingQueue.splice(0, incomingQueue.length);
  res.json({ messages });
});

app.post("/send", async (req, res) => {
  if (!ready) return res.json({ ok: false, error: "bridge not ready" });
  const to = (req.body && req.body.to) || "";
  const text = (req.body && req.body.text) || "";
  if (!to || !text) return res.json({ ok: false, error: "missing to/text" });
  try {
    const chats = await client.getChats();
    const needle = to.toLowerCase().trim();
    const t = chats.find((c) =>
      ((c.name || c.formattedTitle || "").toLowerCase() === needle)
    ) || chats.find((c) =>
      ((c.name || c.formattedTitle || "").toLowerCase().includes(needle))
    );
    if (!t) return res.json({ ok: false, error: "chat not found" });
    await client.sendMessage(t.id._serialized, text);
    res.json({ ok: true });
  } catch (e) {
    res.json({ ok: false, error: String(e) });
  }
});

app.listen(PORT, () => {
  console.log(`[wa-bridge] HTTP server in ascolto su http://127.0.0.1:${PORT}`);
});

client.initialize();

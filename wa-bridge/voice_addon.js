// wa-bridge/voice_addon.js
// Estensione MODULARE del bridge whatsapp-web.js: NON modifica server.js.
// Aggiunge due endpoint:
//   POST /sendVoice    multipart  field 'file' + 'to'   -> invia vocale
//   GET  /media/:msgId                                  -> scarica media in arrivo
//
// USO nel server.js esistente (basta UNA riga in fondo, prima di app.listen):
//
//   require('./voice_addon')(app, client);
//
// Richiede:  npm install express multer
// (multer probabilmente non c'e' ancora nel bridge: aggiungilo).

const fs = require('fs');
const path = require('path');
const multer = require('multer');
const { MessageMedia } = require('whatsapp-web.js');

const upload = multer({ dest: path.join(__dirname, 'tmp_voice') });

// Cache locale dei messaggi vocali ricevuti, per il GET /media/:msgId.
const incomingMediaCache = new Map();

module.exports = function attachVoiceAddon(app, client) {
  // Hook: salva in cache ogni messaggio con media audio.
  try {
    client.on('message', async (msg) => {
      try {
        if (msg.hasMedia && (msg.type === 'ptt' || msg.type === 'audio')) {
          const media = await msg.downloadMedia();
          if (media && media.data) {
            incomingMediaCache.set(msg.id._serialized, {
              data:     media.data,        // base64
              mimetype: media.mimetype,
              filename: media.filename || (msg.id._serialized + '.ogg'),
            });
            // mantieni cache piccola
            if (incomingMediaCache.size > 300) {
              const firstKey = incomingMediaCache.keys().next().value;
              incomingMediaCache.delete(firstKey);
            }
          }
        }
      } catch (_) { /* ignore */ }
    });
  } catch (e) {
    console.warn('[voice_addon] hook message KO:', e.message);
  }

  // GET /media/:msgId  -> binario
  app.get('/media/:msgId', (req, res) => {
    const id = req.params.msgId;
    const entry = incomingMediaCache.get(id);
    if (!entry) return res.status(404).json({ ok: false, error: 'not found' });
    const buf = Buffer.from(entry.data, 'base64');
    res.setHeader('Content-Type', entry.mimetype || 'audio/ogg');
    res.setHeader('Content-Disposition',
      'inline; filename="' + (entry.filename || 'voice.ogg') + '"');
    res.send(buf);
  });

  // POST /sendVoice   multipart: file=<binario>, to=<numero o jid>
  app.post('/sendVoice', upload.single('file'), async (req, res) => {
    try {
      const to = (req.body && req.body.to) || '';
      if (!to) return res.json({ ok: false, error: 'missing to' });
      if (!req.file) return res.json({ ok: false, error: 'missing file' });
      const buf = fs.readFileSync(req.file.path);
      const b64 = buf.toString('base64');
      const mime = req.file.mimetype || 'audio/ogg; codecs=opus';
      const media = new MessageMedia(mime, b64, 'voice.ogg');
      // sendAudioAsVoice rende il messaggio un VOCALE (waveform) e non un file audio.
      let chatId = to;
      if (!chatId.includes('@')) {
        const digits = chatId.replace(/[^\d]/g, '');
        chatId = digits + '@c.us';
      }
      await client.sendMessage(chatId, media, { sendAudioAsVoice: true });
      fs.unlink(req.file.path, () => {});
      return res.json({ ok: true });
    } catch (e) {
      console.error('[voice_addon] /sendVoice err', e);
      try { if (req.file) fs.unlink(req.file.path, () => {}); } catch (_) {}
      return res.json({ ok: false, error: String(e && e.message || e) });
    }
  });
};

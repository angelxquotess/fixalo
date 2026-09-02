# JARVIS — 100+ Idee (implementate e proposte)

Legenda: ✅ implementata in questa versione (additiva) · 💡 proposta futura

## Performance & stabilità
1. ✅ Cache API key/prompt (jarvis_perf)
2. ✅ FPS adattivi quando finestra nascosta
3. ✅ Probe GPU/temperatura con caching (fix ui.py)
4. ✅ Enqueue audio anti-QueueFull (fix main.py)
5. ✅ Guardia anti spin-loop receive (fix main.py)
6. ✅ Intervallo minimo QTimer
7. ✅ GC tuning + freeze
8. ✅ Flag QtWebEngine leggeri
9. ✅ Launcher boosted (`start_jarvis_boosted.py`)
10. 💡 Lazy import dei moduli actions (avvio più rapido)
11. 💡 Cache risposte tool ripetute (TTL 30s)
12. 💡 Pre-connessione sessione Gemini all'avvio
13. 💡 Compressione PNG screenshot (oxipng/pillow ottimizzato)
14. 💡 Pool di thread condiviso per gli executor
15. 💡 Profilatore integrato (`py-spy` toggle da UI)

## Produttività
16. ✅ Note veloci con ricerca
17. ✅ Pomodoro con notifiche
18. ✅ Habit tracker con streak
19. ✅ Expense tracker per categoria
20. ✅ Timer e sveglie vocali
21. ✅ Cronometro
22. ✅ Promemoria "tra N minuti"
23. ✅ Meeting notes con timestamp + export
24. ✅ Lista siti-distrazione (focus mode base)
25. 💡 Integrazione Google Calendar
26. 💡 To-do list con priorità e scadenze
27. 💡 Riepilogo mattutino vocale (meteo + agenda + notizie)
28. 💡 Lettura email ad alta voce
29. 💡 Dettatura lunga in file markdown
30. 💡 Modalità "non disturbare" con eccezioni urgenti

## Sistema & file
31. ✅ System report completo
32. ✅ Top processi + kill per nome
33. ✅ File più grandi / analisi disco
34. ✅ Ricerca duplicati (hash)
35. ✅ Organizza cartella per estensione
36. ✅ Pulizia file temporanei
37. ✅ Backup zip con timestamp
38. ✅ Spegni/riavvia/sospendi/blocca con ritardo
39. ✅ Ricerca file per pattern
40. 💡 Watch cartella con azioni automatiche (es. converti immagini)
41. 💡 Cestino intelligente con auto-pulizia
42. 💡 Sync clipboard tra PC (LAN)
43. 💡 Gestore startup app
44. 💡 Monitor spazio disco con alert soglia
45. 💡 Rename batch con pattern

## Rete
46. ✅ IP pubblico/locale/dettagli geo
47. ✅ Speed test download
48. ✅ Ping
49. ✅ Port scanner porte comuni
50. ✅ RSS headlines
51. ✅ Flush DNS / DNS lookup
52. 💡 Wake-on-LAN
53. 💡 Monitor uptime siti con alert
54. 💡 Condivisione file LAN (mini HTTP server)
55. 💡 Whois lookup
56. 💡 VPN toggle rapido

## Sicurezza & utility
57. ✅ Generatore password + passphrase
58. ✅ Calcolatrice sicura (no eval libero)
59. ✅ Convertitore unità
60. ✅ World clock
61. ✅ Statistiche e trasformazioni testo
62. 💡 Cifratura file AES (cryptography)
63. 💡 Password strength checker
64. ✅ Generatore QR code (vocale: "crea un QR per questo link") + lettura QR da schermo
65. 💡 Hash file (MD5/SHA256)
66. 💡 Scansione allegati sospetti

## Meteo & informazioni (senza API key — open-meteo)
67. ✅ Meteo attuale esteso
68. ✅ Qualità dell'aria
69. 💡 Previsioni 7 giorni vocali
70. 💡 Alert pioggia nelle prossime ore
71. 💡 Orari alba/tramonto
72. 💡 Fase lunare

## Media & schermo
73. ✅ Screenshot istantaneo
74. ✅ Color picker pixel
75. ✅ Registrazione audio WAV
76. ✅ Clipboard get/set + storico 100 voci
77. ✅ Typing macro (anche Unicode via clipboard)
78. ✅ Posizione mouse
79. 💡 Registrazione schermo (mss + ffmpeg)
80. ✅ OCR da screenshot (comando vocale "leggi cosa c'è scritto")
81. 💡 Firma digitale documenti
82. 💡 Slideshow foto comandato a voce

## Benessere
83. ✅ Promemoria 20-20-20 occhi
84. ✅ Promemoria acqua
85. ✅ Promemoria stretching
86. ✅ Consigli postura
87. 💡 Blue-light filter serale automatico
88. 💡 Diario del sonno
89. 💡 Esercizi respirazione guidati
90. 💡 Log umore giornaliero

## Divertimento
91. ✅ Citazioni tech
92. ✅ Barzellette
93. ✅ Trivia
94. ✅ Dadi e moneta
95. 💡 Impiccato vocale
96. 💡 Indovina il numero
97. 💡 Radio online via voce
98. 💡 Effetti sonori ironici

## Casa & automazione
99. 💡 Luci smart (Tapo/Philips Hue)
100. 💡 Presa smart con statistiche consumo
101. 💡 Scenari ("modalità cinema": luci + volume + schermo)
102. 💡 Comando vocale robot aspirapolvere

## Assistente
103. 💡 Memoria a lungo termine con embedding locali
104. 💡 Riassunto conversazioni giornaliere
105. 💡 Personalità multiple selezionabili
106. 💡 Modalità traduttore simultaneo
107. 💡 Lettura documenti PDF ad alta voce
108. 💡 Controllo totale da Telegram remoto
109. ✅ Scorciatoie vocali parola-per-parola (macro: frase esatta -> sequenza di addon) + pannello grafico nella finestra per modificarle
110. 💡 Dashboard web locale opzionale (solo locale, opt-in)
111. ✅ UI futuristica MARK XLII: HUD neon, barre segmentate, addons browser, quick actions
112. ✅ Boot sequence stile Iron Man all'avvio (typewriter + progress bar)
113. ✅ Mini player Spotify nella finestra (brano + copertina + controlli)

**Totale: 113 idee — 72 implementate ✅ / 41 proposte 💡**

## Update: addon vocali
Le ~70 funzioni degli addon sono ora collegate ai comandi vocali di JARVIS:
`addons/voice_bridge.py` genera 55 tool Gemini Live dedicati (con parametri
tipizzati in italiano) + un runner generico `addon_run` che raggiunge TUTTI
gli addon del registro. `main.py` li carica all'avvio e li smista in
`_execute_tool`. Se la cartella addons manca, JARVIS funziona come prima.
Per l'OCR serve Tesseract (`pip install pytesseract` + installer Windows);
se manca, viene usato un modello vision OpenRouter come fallback.

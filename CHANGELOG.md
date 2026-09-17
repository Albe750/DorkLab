# Changelog

Il formato segue [Keep a Changelog](https://keepachangelog.com/it/1.1.0/).

## [1.6.0] - 2026-09-17

### Aggiunto

- Profili di rete (Impostazioni -> Download): regolano ritardo, variabilita'
  casuale (jitter) e User-Agent con un'unica scelta.
  - **Standard**: ritardo breve, User-Agent DorkLab identificabile.
  - **Discreto**: ritardi piu' lunghi e variabili per non pesare sul server e
    non somigliare a una raffica di richieste.
  - **Impronta minima (occultamento)**: di default usa solo fonti d'archivio
    (il sito non viene contattato, quindi non registra nulla); quando un
    contatto e' inevitabile usa un User-Agent da browser e ritardi lunghi e
    casuali. Non altera i log del server ne' rende anonimi: da usare solo dove
    si e' autorizzati, e il gate di autorizzazione sulle fonti attive resta.
- Scheda Scoperta: interruttore "Solo fonti d'archivio: non contattare il
  sito", allineato al profilo scelto, che esclude dalla scansione ogni fonte
  che tocca il server.
- Ritardo fra le richieste con jitter (variazione casuale) in sondaggio,
  crawler e download.

## [1.5.0] - 2026-09-17

### Aggiunto

- Fingerprint della tecnologia del sito: dalla scheda Scoperta, il pulsante
  "Fingerprint e dork" riconosce lo stack (ASP.NET/IIS, PHP, WordPress, Joomla,
  Drupal, Java, Apache, nginx) da estensioni, percorsi, intestazioni HTTP e
  cookie, e propone i dork piu' adatti a quella tecnologia; ogni dork si carica
  nel Costruttore con un clic. 33 dork suggeriti su 8 tecnologie.

### Corretto

- Scheda Scoperta: se un filtro "tipi di documento" e' attivo e la scansione
  non trova nulla, ora l'avviso spiega che il filtro sta escludendo le pagine
  (.aspx, .php) e le directory, invece di lasciare intendere che il sito non
  abbia contenuti.

## [1.4.0] - 2026-09-17

### Corretto

- Sondaggio percorsi: i siti che rispondono 200 a qualsiasi URL (soft-404)
  producevano decine di falsi positivi - documenti segnalati come presenti che
  poi non erano scaricabili. Ora il sondaggio stabilisce una baseline con due
  percorsi inventati: se il sito e' soft-404, riporta solo i contenuti
  realmente diversi dalla pagina generica (veri file, lunghezza diversa) e le
  risorse protette (401/403), escludendo i falsi 200.
- Ritardo fra le richieste impostato a 0 veniva ignorato e forzato a 1 secondo
  (`config.get(...) or default` trasformava lo 0 in default). Nuovo helper
  `Config.number()` che rispetta lo zero; corretto in sondaggio, crawler,
  download e impostazioni.

## [1.3.0] - 2026-09-17

### Aggiunto

- Selezione interattiva della cartella di destinazione al download: un selettore
  di cartella (che parte da quella predefinita) sia nella scheda Risultati sia
  in Scoperta. La scelta viene ricordata per la volta successiva e la cartella
  viene creata se non esiste.
- A fine download, proposta di aprire la cartella di destinazione: aiuta a
  trovare subito i file scaricati.

## [1.2.0] - 2026-09-17

### Cambiato

- Il motore agentico **Claude non richiede piu' il pacchetto `anthropic`**: se
  installato lo usa, altrimenti chiama l'API Messages via HTTP diretto con
  `requests` (gia' dipendenza). Funziona quindi in qualsiasi ambiente, anche
  dove l'SDK non e' installabile; basta la chiave API. Il pacchetto `anthropic`
  diventa una dipendenza opzionale.

## [1.1.0] - 2026-09-17

### Aggiunto

- Scheda **Scoperta**: contenuto pubblico non indicizzato dai motori, da sei
  fonti — Wayback Machine (con copia archiviata recuperabile anche di pagine non
  piu' online), Common Crawl, Certificate Transparency (crt.sh), sitemap e
  robots.txt, crawler di directory aperte e sondaggio di percorsi a dizionario.
- Opzione "Scarica dalla copia archiviata": recupera il documento dallo snapshot
  quando il vivo non risponde piu'.
- Gli URL scoperti confluiscono nella scheda Risultati per download ed
  estrazione dei metadati.
- Il sondaggio attivo dei percorsi e' vincolato alla conferma di autorizzazione,
  come l'audit difensivo.

### Corretto

- "Cerca" apriva il browser invece di riportare i risultati nell'app quando era
  selezionato un motore browser: ora "Cerca" e' riservato ai motori API e
  agentici, mentre i motori browser usano "Apri nel browser" (con conferma).
- Tavily restituiva zero risultati perche' riceveva come query l'intero blocco
  di istruzioni in linguaggio naturale: ora gli viene passata una query di
  ricerca concisa e i vincoli di dominio vanno nel filtro `include_domains`.

## [1.0.0] - 2026-09-17

### Aggiunto

- Costruttore visuale di dork a bolle, con chip modificabili in linea,
  negazione, legame logico AND/OR e riordino.
- Parser con round-trip: qualsiasi dork incollato torna a essere bolle.
- Catalogo di 36 operatori su 6 categorie, con supporto per motore e
  segnalazione degli operatori dismessi.
- 10 gruppi di tipi di documento e 22 ricette di ricerca pronte.
- 16 motori di ricerca su tre famiglie: browser, API e agentici.
- Tavily come motore predefinito, sempre in modalità avanzata, con
  scomposizione della query in varianti per superare il tetto per chiamata.
- Estrazione approfondita del contenuto delle pagine tramite `/extract`.
- Verifica lato client dei vincoli della query, con esito per ogni risultato.
- Download dei documenti con rispetto di `robots.txt`, ritardo configurabile e
  tetto di dimensione.
- Estrazione e aggregazione dei metadati da PDF, OOXML e ODF.
- Scheda di audit difensivo con 14 famiglie di controlli, gate di
  autorizzazione e perimetro forzato su ogni query.
- Catalogo GHDB di 54 voci con gravità e rimedi, estendibile via JSON o CSV.
- Report di audit in Markdown, HTML e CSV; export dei risultati in quattro
  formati.
- Cronologia e dork salvati su SQLite.
- Tema chiaro e scuro con rilevamento automatico.

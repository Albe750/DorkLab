# Changelog

Il formato segue [Keep a Changelog](https://keepachangelog.com/it/1.1.0/).

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

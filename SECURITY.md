# Politica di sicurezza e uso responsabile

## Cosa fa e cosa non fa DorkLab

DorkLab **compone interrogazioni per i motori di ricerca** e ne legge i
risultati. Non esegue exploit, non forza autenticazioni, non effettua scansioni
attive di rete e non accede a contenuti che i motori non abbiano già indicizzato.

## Vincoli di progetto

L'audit difensivo non è una funzione libera:

- `audit.build_plan()` solleva `AuthorizationError` senza conferma esplicita di
  titolarità o autorizzazione scritta;
- `audit.enforce_scope()` garantisce che ogni query generata contenga un
  vincolo `site:` **e** menzioni il dominio dichiarato: i controlli sullo
  storage cloud, il cui `site:` punta a un provider di terze parti, ricevono il
  dominio autorizzato come termine obbligatorio;
- entrambe le garanzie sono verificate dalla suite di test.

## Gestione delle credenziali

Le chiavi API sono salvate in `~/.config/dorklab/config.json` con permessi
`600`. Sono in chiaro: chi preferisce non scriverle su disco può esportarle come
variabili d'ambiente, che hanno la precedenza sul file di configurazione.

## Segnalazione di vulnerabilità

Apri una issue su https://github.com/Albe750/DorkLab/issues descrivendo il
problema. Per questioni che riguardano dati sensibili, usa una segnalazione
privata invece di un'issue pubblica.

## Se trovi un'esposizione di terzi

Se durante una ricerca emergono dati che non ti appartengono:

1. non scaricarli e non diffonderli;
2. segnala al titolare del dominio, se individuabile;
3. in caso di dati personali, considera la segnalazione all'autorità di
   controllo competente.

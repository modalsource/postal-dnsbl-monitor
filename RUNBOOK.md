# Guida Completa: Esecuzione Dry Run Postal DNSBL Monitor

## Prerequisiti

1. **Python 3.14+** (o compatibile) e `uv` installati
2. **Docker** e **Docker Compose** per il database locale
3. **API Token Jira** da https://id.atlassian.com/manage-profile/security/api-tokens

---

## Passo 1: Avviare il Database MySQL Locale

Avvia il container MariaDB con i dati di test:

```bash
cd /home/fulgidus/Documenti/postal-dnsbl-monitor
docker compose up -d
```

Verifica che il database sia attivo:

```bash
# Attendere circa 10 secondi per l'inizializzazione
docker compose logs db

# Connettersi al database per verificare
docker compose exec db mysql -uroot -proot postal -e "SELECT id, ipv4, hostname, priority, blockingLists FROM ip_addresses;"
```

Dovresti vedere 8 IP address con priority=100 e blockingLists vuoto.

Puoi anche usare Adminer per esplorare il database:
- URL: http://localhost:8080
- Server: `db`
- Username: `root`
- Password: `root`
- Database: `postal`

---

## Passo 2: Configurare le Variabili d'Ambiente

Modifica il file `.env` nella root del progetto:

```bash
nano .env
```

**IMPORTANTE**: Sostituisci `YOUR_JIRA_API_TOKEN_HERE` con il tuo API token Jira reale:

```env
JIRA_API_TOKEN=tuo_api_token_qui
```

Verifica tutte le altre configurazioni (dovrebbero essere già corrette):

```bash
cat .env
```

---

## Passo 3: Installare le Dipendenze

Le dipendenze sono già installate con `uv sync`. Verifica:

```bash
uv run python -c "import mysql.connector; import jira; import dns.resolver; print('Dependencies OK')"
```

---

## Passo 4: Eseguire la Dry Run

Esegui il monitor in modalità DRY_RUN (nessuna modifica al DB o Jira):

```bash
uv run python -m src.main
```

### Output Atteso

Vedrai log JSON strutturati simili a:

```json
{"timestamp": "2025-12-17T...", "level": "INFO", "message": "Starting Postal DNSBL Monitor"}
{"timestamp": "2025-12-17T...", "level": "INFO", "message": "Configuration loaded: 95 DNSBL zones configured"}
{"timestamp": "2025-12-17T...", "level": "INFO", "message": "DRY_RUN mode enabled - no database writes or Jira actions will occur"}
{"timestamp": "2025-12-17T...", "level": "INFO", "message": "Loaded 8 IP addresses from database"}

# Per ogni IP, vedrai:
{
  "timestamp": "2025-12-17T...",
  "level": "INFO",
  "ip": "195.231.36.228",
  "listed_zones": [...],
  "unknown_zones": [...],
  "decision": "CLEAN" | "LISTED",
  "db_changes": false,
  "jira_action": "no_action",
  "duration_ms": 1234
}

# Summary finale:
{
  "timestamp": "2025-12-17T...",
  "level": "INFO",
  "total_ips": 8,
  "listed": 0,
  "cleaned": 0,
  "unchanged": 8,
  "jira_created": 0,
  "jira_updated": 0,
  "dns_failures": 0,
  "duration_sec": 12.34
}
```

### Interpretazione dei Risultati

- **decision: CLEAN** -> IP non è in nessuna blacklist
- **decision: LISTED** -> IP trovato in almeno una blacklist
- **listed_zones** -> Lista delle blacklist dove l'IP è presente
- **unknown_zones** -> Zone che non hanno risposto (timeout/errore DNS)
- **jira_action: no_action** -> In DRY_RUN, nessuna azione Jira viene eseguita

---

## Passo 5: Test con Modifiche Reali (Opzionale)

Se vuoi testare le scritture reali sul database locale (ma NON su Jira), modifica `.env`:

```bash
# Cambia solo per test locale! Non usare in produzione senza verificare!
DRY_RUN=false
```

Poi esegui di nuovo:

```bash
uv run python -m src.main
```

**ATTENZIONE**: Questo creerà ticket Jira reali! Usa con cautela.

Per testare SOLO le scritture DB (senza Jira), puoi commentare temporaneamente la sezione Jira nel codice o usare un progetto Jira di test.

---

## Passo 6: Verificare le Modifiche al Database

Dopo un'esecuzione con DRY_RUN=false, controlla le modifiche:

```bash
docker compose exec db mysql -uroot -proot postal -e "SELECT id, ipv4, priority, oldPriority, blockingLists, lastEvent FROM ip_addresses;"
```

Cerca:
- **priority** cambiato da 100 a 9 per IP bloccati
- **oldPriority** salvato con valore originale (100)
- **blockingLists** popolato con zone (es. "zen.spamhaus.org,bl.spamcop.net")
- **lastEvent** con descrizione del cambiamento

---

## Passo 7: Pulizia e Reset

Per resettare il database ai dati iniziali:

```bash
docker compose down -v
docker compose up -d
# Attendere 10 secondi per re-inizializzazione
```

---

## Troubleshooting

### Errore: "mysql.connector.errors.InterfaceError: Can't connect"

Il database non è ancora pronto. Aspetta qualche secondo e riprova.

### Errore: "JiraError: 401 Unauthorized"

Il token Jira in `.env` non è valido. Genera un nuovo token da:
https://id.atlassian.com/manage-profile/security/api-tokens

### Errore: "ValueError: Required environment variable ... is not set"

Verifica che tutte le variabili richieste in `.env` siano configurate.

### Warning: "No 'Done' transition found"

Il progetto Jira POSTALMON non ha una transizione "Done". Controlla i workflow Jira e aggiorna il codice se necessario per usare una transizione diversa (es. "Close", "Resolve").

---

## Prossimi Passi

1. **Test su Database Reale**: Modifica `.env` per puntare a `postal-database.k8s.nurtigomail.com:3306` (assicurati che le colonne `oldPriority`, `blockingLists`, `lastEvent` esistano!)

2. **Deploy su Kubernetes**: Usa i manifest in `kubernetes/` dopo aver verificato che tutto funzioni localmente

3. **Monitoraggio**: Integra i log JSON con il tuo stack di logging (es. ELK, Loki)


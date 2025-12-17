#!/bin/bash
# Helper script per eseguire dry run del Postal DNSBL Monitor

set -e

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Postal DNSBL Monitor - Dry Run${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Verifica che .env esista
if [ ! -f .env ]; then
    echo -e "${RED}Errore: File .env non trovato!${NC}"
    echo "Copia .env.example a .env e configuralo con le tue credenziali."
    exit 1
fi

# Verifica che il database sia raggiungibile
echo -e "${YELLOW}Verificando connessione al database...${NC}"
if docker compose exec -T db mysql -uroot -proot -e "SELECT 1" &>/dev/null; then
    echo -e "${GREEN}✓ Database raggiungibile${NC}"
else
    echo -e "${RED}✗ Database non raggiungibile${NC}"
    echo "Avvia il database con: docker compose up -d"
    exit 1
fi

# Conta gli IP nel database
IP_COUNT=$(docker compose exec -T db mysql -uroot -proot postal -Nse "SELECT COUNT(*) FROM ip_addresses WHERE ipv4 IS NOT NULL;")
echo -e "${GREEN}✓ ${IP_COUNT} IP addresses trovati nel database${NC}"
echo ""

# Esegui il monitor
echo -e "${YELLOW}Eseguendo Postal DNSBL Monitor...${NC}"
echo ""

uv run --env-file .env python -m src.main

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Dry run completata!${NC}"
echo -e "${GREEN}========================================${NC}"

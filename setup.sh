#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting IAQ stack...${NC}"

# Check if .env exists
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        echo -e "${RED}.env file not found. Creating from .env.example...${NC}"
        cp .env.example .env
        echo -e "${RED}Please edit .env file with your credentials and run this script again.${NC}"
        exit 1
    else
        echo -e "${RED}Neither .env nor .env.example found!${NC}"
        exit 1
    fi
fi

# Load environment variables
export $(cat .env | grep -v '^#' | xargs)

# Start Docker containers
echo -e "${GREEN}Starting containers...${NC}"
docker-compose up -d

# Wait for PostgreSQL to be ready
echo -e "${GREEN}Waiting for PostgreSQL...${NC}"
until docker exec -e PGPASSWORD=${POSTGRES_PASSWORD} timescaledb-iaq pg_isready -U ${POSTGRES_USER:-postgres} > /dev/null 2>&1; do
    echo -n "."
    sleep 1
done
echo ""

# Wait an extra second for stability
sleep 1

# Create database if it doesn't exist
docker exec -e PGPASSWORD=${POSTGRES_PASSWORD} timescaledb-iaq psql -U ${POSTGRES_USER:-postgres} -tc "SELECT 1 FROM pg_database WHERE datname = '${POSTGRES_DB:-iaq}'" | grep -q 1 || \
    docker exec -e PGPASSWORD=${POSTGRES_PASSWORD} timescaledb-iaq psql -U ${POSTGRES_USER:-postgres} -c "CREATE DATABASE ${POSTGRES_DB:-iaq};"

# Setup TimescaleDB and create table
echo -e "${GREEN}Setting up database...${NC}"

# Enable TimescaleDB extension
docker exec -e PGPASSWORD=${POSTGRES_PASSWORD} timescaledb-iaq psql -U ${POSTGRES_USER:-postgres} -d ${POSTGRES_DB:-iaq} -c "CREATE EXTENSION IF NOT EXISTS timescaledb;"

# Create table
docker exec -e PGPASSWORD=${POSTGRES_PASSWORD} timescaledb-iaq psql -U ${POSTGRES_USER:-postgres} -d ${POSTGRES_DB:-iaq} -c "CREATE TABLE IF NOT EXISTS iaq_measurements (
  time        TIMESTAMPTZ       NOT NULL,
  device_id   TEXT              NOT NULL DEFAULT 'offline_csv',
  temp_c      DOUBLE PRECISION,
  rh_pct      DOUBLE PRECISION,
  co2_ppm     DOUBLE PRECISION,
  tvoc_ppb    DOUBLE PRECISION,
  iaq_score   INTEGER,
  PRIMARY KEY (time, device_id)
);"

# Convert to hypertable
docker exec -e PGPASSWORD=${POSTGRES_PASSWORD} timescaledb-iaq psql -U ${POSTGRES_USER:-postgres} -d ${POSTGRES_DB:-iaq} -c "SELECT create_hypertable('iaq_measurements', 'time', if_not_exists => TRUE);"

# Verify table creation
TABLE_EXISTS=$(docker exec -e PGPASSWORD=${POSTGRES_PASSWORD} timescaledb-iaq psql -U ${POSTGRES_USER:-postgres} -d ${POSTGRES_DB:-iaq} -tAc "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'iaq_measurements');")

if [ "$TABLE_EXISTS" = "t" ]; then
    echo -e "${GREEN}✓ Setup completed successfully!${NC}"
    echo ""
    echo "Services available at:"
    echo "  - TimescaleDB: localhost:5433"
    echo "  - Grafana: http://localhost:3001 (admin/admin)"
    echo ""
    echo "To connect to the database:"
    echo "  docker exec -it timescaledb-iaq psql -U ${POSTGRES_USER:-postgres} -d ${POSTGRES_DB:-iaq}"
else
    echo -e "${RED}✗ Table creation failed. Check the error messages above.${NC}"
    exit 1
fi
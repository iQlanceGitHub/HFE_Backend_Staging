#!/usr/bin/env sh
while ! pg_isready -h localhost -U postgres -d postgres; do sleep 1; done
echo "postgres is up"

PGPASSWORD=postgres psql -h localhost -U postgres -c 'drop database if exists "fast-scan";'
PGPASSWORD=postgres psql -h localhost -U postgres -c 'create database "fast-scan";'

echo "fast-scan database created"
cat secrets_test.json

exit 0

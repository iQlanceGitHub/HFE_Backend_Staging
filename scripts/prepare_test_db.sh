#!/usr/bin/env sh
while ! pg_isready -h postgres -U postgres -d postgres; do sleep 1; done
echo "postgres is up"

PGPASSWORD=postgres psql -h postgres -U postgres -c 'drop database if exists "fast-scan-test";'
PGPASSWORD=postgres psql -h postgres -U postgres -c 'create database "fast-scan-test";'

echo "fast-scan-test database created"
cat secrets_test.json

exit 0

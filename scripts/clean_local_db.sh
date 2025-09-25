#!/usr/bin/env sh

# Database name to drop
DATABASE_NAME="fast-scan"

# Wait for PostgreSQL to be ready
while ! pg_isready -h localhost -U postgres -d postgres; do
    sleep 1
done
echo "PostgreSQL is up"

# Terminate all active connections to the database
PGPASSWORD=postgres psql -h localhost -U postgres -c "SELECT pg_terminate_backend(pg_stat_activity.pid) FROM pg_stat_activity WHERE pg_stat_activity.datname = '$DATABASE_NAME';"

# Drop the database if it exists
PGPASSWORD=postgres psql -h localhost -U postgres -c "DROP DATABASE IF EXISTS \"$DATABASE_NAME\";"

echo "Database $DATABASE_NAME has been forcefully dropped"

exit 0
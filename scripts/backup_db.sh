#!/bin/bash

# Variables
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/home/skymoon/Projects/recipes/backups"
DB_NAME="food_recipes"
DB_USER="skymoon"
DB_HOST="localhost"
DB_PORT="5432"

# Create backup directory if it doesn't exist
mkdir -p $BACKUP_DIR

# Dump the database
pg_dump -U $DB_USER -h $DB_HOST -p $DB_PORT $DB_NAME > $BACKUP_DIR/backup_$DATE.sql

# Compress the backup
gzip $BACKUP_DIR/backup_$DATE.sql

# Keep only last 7 backups (optional)
cd $BACKUP_DIR
ls -t backup_*.sql.gz | tail -n +8 | xargs -r rm

echo "Backup completed: backup_$DATE.sql.gz"

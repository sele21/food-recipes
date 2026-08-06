import os
import subprocess
from django.core.management.base import BaseCommand
from django.conf import settings

class Command(BaseCommand):
    help = 'Backup the database'

    def handle(self, *args, **options):
        backup_dir = os.path.join(settings.BASE_DIR, 'backups')
        os.makedirs(backup_dir, exist_ok=True)

        date = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'backup_{date}.sql.gz'
        filepath = os.path.join(backup_dir, filename)

        command = f'pg_dump -U skymoon -h localhost food_recipes | gzip > {filepath}'
        subprocess.run(command, shell=True, check=True)

        self.stdout.write(self.style.SUCCESS(f'Backup created: {filename}'))

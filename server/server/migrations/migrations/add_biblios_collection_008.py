from common.arangodb import get_db
from migrations.base import Migration


class SecondMigration(Migration):
    migration_id = 'add_biblios_collection_008'
    tasks = ['create_collection']

    def create_collection(self):
        db = get_db()

        biblios = db.create_collection('biblios')
        biblios.add_hash_index(fields=['uid'], unique=True)

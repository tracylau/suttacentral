from common.arangodb import get_db
from migrations.base import Migration


class InitialMigration(Migration):
    migration_id = 'add_hash_indexes_for_menu_uids_023'
    tasks = ['add_hash_indexes']

    def add_hash_indexes(self):
        db = get_db()

        db['po_strings'].add_hash_index(fields=['menu_uids[*]'], unique=False, sparse=True)
        db['html_text'].add_hash_index(fields=['menu_uids[*]'], unique=False, sparse=True)
        

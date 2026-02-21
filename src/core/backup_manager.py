"""
Backup Manager - Nightly Database Backups
Nexira / Ultimate AI System v8.0 - Phase 4
Created by Xeeker & Claude - February 2026

Creates a ZIP backup of the database nightly.
Keeps the last 7 backups, deletes older ones automatically.
"""

import os
import shutil
import zipfile
from datetime import datetime
from typing import List, Dict


MAX_BACKUPS = 7


class BackupManager:
    """Manages automatic nightly backups of the Nexira database."""

    def __init__(self, base_dir: str):
        self.base_dir   = base_dir
        self.db_dir     = os.path.join(base_dir, 'data', 'databases')
        self.backup_dir = os.path.join(base_dir, 'data', 'backups')
        os.makedirs(self.backup_dir, exist_ok=True)

    def run_backup(self) -> Dict:
        """
        Create a ZIP backup of all database files.
        Returns a summary dict.
        """
        now       = datetime.now()
        timestamp = now.strftime('%Y%m%d_%H%M%S')
        zip_name  = f'nexira_backup_{timestamp}.zip'
        zip_path  = os.path.join(self.backup_dir, zip_name)

        result = {
            'timestamp':  now.isoformat(),
            'filename':   zip_name,
            'success':    False,
            'size_kb':    0,
            'files':      [],
            'error':      ''
        }

        try:
            files_added = []
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                # Back up all .db files
                for fname in os.listdir(self.db_dir):
                    if fname.endswith('.db'):
                        fpath = os.path.join(self.db_dir, fname)
                        zf.write(fpath, fname)
                        files_added.append(fname)

                # Also back up config
                config_path = os.path.join(self.base_dir, 'config', 'default_config.json')
                if os.path.exists(config_path):
                    zf.write(config_path, 'default_config.json')
                    files_added.append('default_config.json')

            size_kb = os.path.getsize(zip_path) / 1024
            result.update({
                'success':  True,
                'size_kb':  round(size_kb, 1),
                'files':    files_added
            })

            print(f"✓ Backup created: {zip_name} ({size_kb:.1f} KB, {len(files_added)} files)")

            # Prune old backups
            pruned = self._prune_old_backups()
            if pruned:
                print(f"  🗑  Pruned {len(pruned)} old backup(s)")

        except Exception as e:
            result['error'] = str(e)
            print(f"⚠️  Backup failed: {e}")

        return result

    def _prune_old_backups(self) -> List[str]:
        """Delete backups older than the last MAX_BACKUPS."""
        backups = self.list_backups()
        to_delete = backups[MAX_BACKUPS:]  # already sorted newest-first
        deleted = []
        for b in to_delete:
            try:
                os.remove(b['path'])
                deleted.append(b['filename'])
            except Exception:
                pass
        return deleted

    def list_backups(self) -> List[Dict]:
        """List all backups sorted newest first."""
        backups = []
        for fname in os.listdir(self.backup_dir):
            if fname.startswith('nexira_backup_') and fname.endswith('.zip'):
                fpath = os.path.join(self.backup_dir, fname)
                stat  = os.stat(fpath)
                backups.append({
                    'filename': fname,
                    'path':     fpath,
                    'size_kb':  round(stat.st_size / 1024, 1),
                    'created':  datetime.fromtimestamp(stat.st_mtime).isoformat()
                })
        backups.sort(key=lambda x: x['created'], reverse=True)
        return backups

    def restore_backup(self, filename: str) -> Dict:
        """Restore a specific backup (replaces current databases)."""
        zip_path = os.path.join(self.backup_dir, filename)
        if not os.path.exists(zip_path):
            return {'success': False, 'error': 'Backup file not found'}
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                for name in zf.namelist():
                    if name.endswith('.db'):
                        zf.extract(name, self.db_dir)
            return {'success': True, 'message': f'Restored from {filename}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

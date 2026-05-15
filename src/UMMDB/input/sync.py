import os
import subprocess

class RepoSynchronizer:
    def __init__(self, repo_path: str, poll_interval: int = 60):
        self.repo_path = repo_path
        self.poll_interval = poll_interval
        self.last_commit = None
        
    def get_head_commit(self) -> str:
        if not os.path.isdir(self.repo_path):
            return None
        try:
            result = subprocess.run(
                ['git', 'rev-parse', 'HEAD'],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return None
        except Exception:
            return None
            
    def poll(self) -> bool:
        current_commit = self.get_head_commit()
        if not current_commit:
            return False
            
        if self.last_commit != current_commit:
            self.last_commit = current_commit
            return True
            
        return False

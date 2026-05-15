import subprocess
from typing import Dict, Optional

class StateIndex:
    def __init__(self):
        self._state: Dict[str, str] = {}

    def get_state(self, repo_path: Optional[str] = None):
        if repo_path is None:
            return self._state
        return self._state.get(repo_path)

    def update_state(self, repo_path: str, commit_hash: str) -> None:
        self._state[repo_path] = commit_hash

class GitPoller:
    def get_current_commit_hash(self, repo_path: str) -> str:
        result = subprocess.run(
            ["git", "-C", repo_path, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()

class PollingPipeline:
    def __init__(self, state_index: StateIndex):
        self.state_index = state_index
        self.poller = GitPoller()

    def poll(self, repo_path: str) -> bool:
        current_hash = self.poller.get_current_commit_hash(repo_path)
        previous_hash = self.state_index.get_state(repo_path)
        
        if current_hash != previous_hash:
            self.state_index.update_state(repo_path, current_hash)
            return True
        return False

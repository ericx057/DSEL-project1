import pytest
from unittest.mock import patch, MagicMock
from UMMDB.input.polling import StateIndex, GitPoller, PollingPipeline

def test_state_index_initialization():
    index = StateIndex()
    assert index.get_state() == {}

def test_state_index_update():
    index = StateIndex()
    index.update_state("repo_a", "hash1")
    assert index.get_state("repo_a") == "hash1"

def test_git_poller_get_current_hash():
    with patch("subprocess.run") as mock_run:
        mock_result = MagicMock()
        mock_result.stdout = "new_hash_123"
        mock_run.return_value = mock_result
        
        poller = GitPoller()
        current_hash = poller.get_current_commit_hash("/path/to/repo")
        
        assert current_hash == "new_hash_123"
        mock_run.assert_called_once()

def test_polling_pipeline_no_change():
    index = StateIndex()
    index.update_state("/path/to/repo", "hash_abc")
    
    with patch("UMMDB.input.polling.GitPoller.get_current_commit_hash", return_value="hash_abc"):
        pipeline = PollingPipeline(index)
        changed = pipeline.poll("/path/to/repo")
        assert changed is False

def test_polling_pipeline_with_change():
    index = StateIndex()
    index.update_state("/path/to/repo", "old_hash")
    
    with patch("UMMDB.input.polling.GitPoller.get_current_commit_hash", return_value="new_hash"):
        pipeline = PollingPipeline(index)
        changed = pipeline.poll("/path/to/repo")
        assert changed is True
        assert index.get_state("/path/to/repo") == "new_hash"

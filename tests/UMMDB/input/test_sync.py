import os
import tempfile
import subprocess
from UMMDB.input.sync import RepoSynchronizer

def test_repo_synchronizer_no_repo():
    sync = RepoSynchronizer("/non/existent/path")
    assert sync.get_head_commit() is None
    assert sync.poll() is False

def test_repo_synchronizer_with_repo():
    with tempfile.TemporaryDirectory() as temp_dir:
        subprocess.run(['git', 'init'], cwd=temp_dir, capture_output=True, check=True)
        
        sync = RepoSynchronizer(temp_dir)
        # Empty repo has no head commit
        assert sync.get_head_commit() is None
        assert sync.poll() is False
        
        # Create a commit
        with open(os.path.join(temp_dir, 'test.txt'), 'w') as f:
            f.write("hello")
        subprocess.run(['git', 'add', 'test.txt'], cwd=temp_dir, capture_output=True, check=True)
        subprocess.run(['git', 'commit', '-m', 'Initial commit'], cwd=temp_dir, capture_output=True, check=True)
        
        head1 = sync.get_head_commit()
        assert head1 is not None
        
        assert sync.poll() is True
        assert sync.last_commit == head1
        assert sync.poll() is False
        
        # Second commit
        with open(os.path.join(temp_dir, 'test.txt'), 'w') as f:
            f.write("world")
        subprocess.run(['git', 'add', 'test.txt'], cwd=temp_dir, capture_output=True, check=True)
        subprocess.run(['git', 'commit', '-m', 'Second commit'], cwd=temp_dir, capture_output=True, check=True)
        
        head2 = sync.get_head_commit()
        assert head2 is not None
        assert head1 != head2
        
        assert sync.poll() is True
        assert sync.last_commit == head2
        assert sync.poll() is False

def test_repo_synchronizer_exception(monkeypatch):
    import subprocess
    def mock_run(*args, **kwargs):
        raise Exception("Mock Exception")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        monkeypatch.setattr(subprocess, "run", mock_run)
        sync = RepoSynchronizer(temp_dir)
        assert sync.get_head_commit() is None

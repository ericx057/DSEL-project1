import subprocess
import sys


def test_desktop_module_exposes_canonical_help_command():
    result = subprocess.run(
        [sys.executable, "-m", "src.desktop", "--help"],
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    assert "Ctrl+Alt" in result.stdout
    assert "--no-hotkey" in result.stdout

import os
import tempfile
import pytest
from unittest.mock import patch
from UMMDB.parser.filters import FileHeuristics

def test_file_does_not_exist():
    heuristics = FileHeuristics()
    assert not heuristics.is_human_readable("non_existent_file.txt")

def test_exclude_patterns():
    heuristics = FileHeuristics(exclude_patterns=["bad_file"])
    with tempfile.NamedTemporaryFile(suffix="bad_file.txt") as tmp:
        assert not heuristics.is_human_readable(tmp.name)

def test_empty_file():
    heuristics = FileHeuristics()
    with tempfile.NamedTemporaryFile() as tmp:
        assert heuristics.is_human_readable(tmp.name)

def test_binary_ratio():
    heuristics = FileHeuristics(max_binary_ratio=0.1)
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        # Create a file with 2 null bytes in 10 bytes -> ratio 0.2
        tmp.write(b"a" * 8 + b"\x00" * 2)
        tmp_name = tmp.name
    try:
        assert not heuristics.is_human_readable(tmp_name)
    finally:
        os.remove(tmp_name)

def test_max_line_length():
    heuristics = FileHeuristics(max_line_length=10)
    with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as tmp:
        tmp.write(("ok\n" * 10) + ("a" * 15) + "\n")
        tmp_name = tmp.name
    try:
        assert not heuristics.is_human_readable(tmp_name)
    finally:
        os.remove(tmp_name)

def test_unicode_decode_error():
    heuristics = FileHeuristics()
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        # Write invalid utf-8 sequence without null bytes to pass binary check
        tmp.write(b'\xff\xfe\xfd')
        tmp_name = tmp.name
    try:
        assert not heuristics.is_human_readable(tmp_name)
    finally:
        os.remove(tmp_name)

@patch('builtins.open')
def test_general_exception(mock_open):
    heuristics = FileHeuristics()
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(b"hello")
        tmp_name = tmp.name
    
    mock_open.side_effect = Exception("General error")
    try:
        assert not heuristics.is_human_readable(tmp_name)
    finally:
        os.remove(tmp_name)

def test_human_readable_file():
    heuristics = FileHeuristics()
    with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as tmp:
        tmp.write("hello\nworld\n")
        tmp_name = tmp.name
    try:
        assert heuristics.is_human_readable(tmp_name)
    finally:
        os.remove(tmp_name)

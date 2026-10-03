"""Append one JSONL record under an OS flock; no temporary/unlocked fallback."""
import fcntl
import json
import os
import sys

record = json.loads(sys.stdin.read())
line = (json.dumps(record, separators=(',', ':'), ensure_ascii=True) + '\n').encode('utf-8')
fd = os.open(sys.argv[1], os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
try:
    fcntl.flock(fd, fcntl.LOCK_EX)
    # Cooperating writers hold the same inode lock across the complete record.
    view = memoryview(line)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError('audit append failed')
        view = view[written:]
    os.fsync(fd)
finally:
    os.close(fd)

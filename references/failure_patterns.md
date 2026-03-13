# Common Failure Patterns and Fixes

Reference for the Dojo analyzer when deciding how to fix identified weaknesses.

## Terminal / Command Execution

| Error Pattern | Root Cause | Fix |
|---|---|---|
| "command not found" | Tool/binary not in PATH | Add `which` check before execution, suggest install |
| "permission denied" | File/dir not writable | Check permissions first, suggest `chmod` or `sudo` |
| "no such file or directory" | Path doesn't exist | Validate path exists before operations |
| "syntax error" | Bad shell syntax | Use proper quoting and escaping |
| "killed" / exit code 137 | OOM or timeout | Add memory/time limits, suggest smaller scope |

## Web / Network

| Error Pattern | Root Cause | Fix |
|---|---|---|
| "timeout" / "ETIMEDOUT" | Slow server or network | Add retry with backoff, increase timeout |
| "connection refused" | Service not running | Check if service is up before connecting |
| "rate limit" / 429 | API throttling | Add rate limiting, exponential backoff |
| "404 not found" | Wrong URL | Validate URL format, check for typos |
| "SSL certificate" | Cert issues | Flag to user, don't auto-skip verification |

## File Operations

| Error Pattern | Root Cause | Fix |
|---|---|---|
| "ENOENT" | File not found | Check existence first |
| "EACCES" | Permission denied | Check read/write permissions |
| "EISDIR" | Expected file, got dir | Validate file type before operation |
| "disk full" / "ENOSPC" | No space | Check available space, suggest cleanup |

## User Correction Signals

| Pattern | Meaning | Action |
|---|---|---|
| "no, I meant..." | Misunderstood intent | Improve skill instructions for disambiguation |
| "wrong file/path" | Path resolution error | Add more context-aware path resolution |
| "try again" | Non-specific failure | Need more error details in skill |
| "that broke" | Side effect caused damage | Add safety checks and dry-run options |
| "undo" / "revert" | Want to roll back | Add undo capability to skill |

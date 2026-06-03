import os
import json
import time
import difflib
import subprocess
import threading
from pathlib import Path
from datetime import datetime
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, Annotated
import sys
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.rule import Rule
from rich.live import Live
from rich import box
from rich.syntax import Syntax

from agno.agent import Agent
from agno.models.ollama import Ollama
from agno.models.google import Gemini
from agno.models.anthropic import Claude
from agno.models.groq import Groq

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(script_dir)

try:
    import locvecwrapper as lvw
    _LVW_AVAILABLE = True
except ImportError:
    _LVW_AVAILABLE = False

THEME = {
    "primary":   "bold #00d7ff",
    "secondary": "#5f87ff",
    "accent":    "bold #ff5f87",
    "success":   "bold #5fff87",
    "warning":   "bold #ffd700",
    "error":     "bold #ff5f5f",
    "muted":     "#4e4e4e",
    "tool":      "#d7af5f",
    "tool_res":  "#87d7af",
    "user":      "#d787ff",
    "dim":       "dim #8a8a8a",
}

console = Console(highlight=False)

MAX_HISTORY_TOKENS = 6_000
APPROX_CHARS_PER_TOKEN = 4

PERMISSIONS: dict[str, bool] = {
    "shell":      True,
    "web":        True,
    "file_read":  True,
    "file_write": True,
}
SHELL_BLOCKLIST = ["rm -rf /", "mkfs", "dd if="]

def check_permission(category: str) -> bool:
    return PERMISSIONS.get(category, True)

def _blocked_shell(cmd: str) -> bool:
    return any(bad in cmd for bad in SHELL_BLOCKLIST)

_file_snapshots: dict[str, list[str]] = {}

def _snapshot(path: str):
    p = Path(path)
    if p.exists() and p.is_file():
        try:
            _file_snapshots[path] = p.read_text(errors="replace").splitlines(keepends=True)
        except Exception:
            pass

def _show_diff(path: str):
    p = Path(path)
    if not p.exists():
        return
    try:
        after = p.read_text(errors="replace").splitlines(keepends=True)
    except Exception:
        return
    before = _file_snapshots.get(path, [])
    if before == after:
        return
    diff = list(difflib.unified_diff(before, after, fromfile=f"a/{path}", tofile=f"b/{path}", lineterm=""))
    if not diff:
        return
    colored = Text()
    for line in diff[:80]:
        if line.startswith("+++") or line.startswith("---"):
            colored.append(line + "\n", style="bold white")
        elif line.startswith("+"):
            colored.append(line + "\n", style="#5fff87")
        elif line.startswith("-"):
            colored.append(line + "\n", style="#ff5f5f")
        elif line.startswith("@@"):
            colored.append(line + "\n", style="#5f87ff")
        else:
            colored.append(line + "\n", style=THEME["dim"])
    if len(diff) > 80:
        colored.append(f"… ({len(diff)-80} more lines)\n", style=THEME["dim"])
    console.print(Panel(colored, title=f"[{THEME['success']}]Δ diff › {path}[/]",
                        border_style="#5fff87", padding=(0, 1)))

def shell(command: str) -> str:
    """Run a shell command and return stdout + stderr. Use for creating folders, running scripts, installing packages, executing Python, etc."""
    if not check_permission("shell"):
        return "PERMISSION_DENIED: shell is disabled."
    if _blocked_shell(command):
        return "PERMISSION_DENIED: dangerous command blocked."
    console.print(Panel(
        Text(command, style=THEME["tool"]),
        title=f"[{THEME['tool']}]⚙  SHELL[/]",
        border_style="#d7af5f", padding=(0, 1)
    ))
    result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60)
    output = ""
    if result.stdout:
        output += result.stdout
    if result.stderr:
        output += "\nSTDERR: " + result.stderr
    output = output.strip() or "(no output)"
    console.print(Panel(
        Text(output[:600] + ("…" if len(output) > 600 else ""), style=THEME["tool_res"]),
        title=f"[{THEME['tool_res']}]✔  RESULT[/]",
        border_style="#87d7af", padding=(0, 1)
    ))
    return output

def read_file(path: str) -> str:
    """Read the contents of a file at the given path."""
    if not check_permission("file_read"):
        return "PERMISSION_DENIED: file_read is disabled."
    console.print(Panel(
        Text(path, style=THEME["tool"]),
        title=f"[{THEME['tool']}]⚙  READ FILE[/]",
        border_style="#d7af5f", padding=(0, 1)
    ))
    p = Path(path)
    if not p.exists():
        return f"ERROR: File not found: {path}"
    try:
        content = p.read_text(errors="replace")
        result = content[:3000] + ("…(truncated)" if len(content) > 3000 else "")
        console.print(Panel(
            Text(result[:400] + ("…" if len(result) > 400 else ""), style=THEME["tool_res"]),
            title=f"[{THEME['tool_res']}]✔  FILE CONTENTS[/]",
            border_style="#87d7af", padding=(0, 1)
        ))
        return result
    except Exception as e:
        return f"ERROR reading file: {e}"

def write_file(path: str, content: str) -> str:
    """Write content to a file, creating it and any parent directories if needed."""
    if not check_permission("file_write"):
        return "PERMISSION_DENIED: file_write is disabled."
    console.print(Panel(
        Text(f"{path}\n{content[:200]}{'…' if len(content) > 200 else ''}", style=THEME["tool"]),
        title=f"[{THEME['tool']}]⚙  WRITE FILE[/]",
        border_style="#d7af5f", padding=(0, 1)
    ))
    _snapshot(path)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    _show_diff(path)
    result = f"Written {len(content)} chars to {path}"
    console.print(Panel(
        Text(result, style=THEME["tool_res"]),
        title=f"[{THEME['tool_res']}]✔  FILE WRITTEN[/]",
        border_style="#87d7af", padding=(0, 1)
    ))
    return result

def list_files(path: str = ".") -> str:
    """List files and directories at the given path."""
    if not check_permission("file_read"):
        return "PERMISSION_DENIED: file_read is disabled."
    console.print(Panel(
        Text(path, style=THEME["tool"]),
        title=f"[{THEME['tool']}]⚙  LIST FILES[/]",
        border_style="#d7af5f", padding=(0, 1)
    ))
    p = Path(path)
    if not p.exists():
        return f"ERROR: Path not found: {path}"
    entries = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
    lines = []
    for e in entries:
        kind = "FILE" if e.is_file() else "DIR"
        size = f" ({e.stat().st_size}B)" if e.is_file() else ""
        lines.append(f"[{kind}] {e.name}{size}")
    result = "\n".join(lines) if lines else "(empty directory)"
    console.print(Panel(
        Text(result[:400], style=THEME["tool_res"]),
        title=f"[{THEME['tool_res']}]✔  LISTING[/]",
        border_style="#87d7af", padding=(0, 1)
    ))
    return result

def web_search(query: str) -> str:
    """Search the web for information. Returns a summary of results."""
    if not check_permission("web"):
        return "PERMISSION_DENIED: web is disabled."
    console.print(Panel(
        Text(query, style=THEME["tool"]),
        title=f"[{THEME['tool']}]⚙  WEB SEARCH[/]",
        border_style="#d7af5f", padding=(0, 1)
    ))
    try:
        from duckduckgo_search import DDGS
        results = DDGS().text(query, max_results=3)
        result = str(results)[:2000]
        result = result + ("…(truncated)" if len(str(results)) > 2000 else "")
        console.print(Panel(
            Text(result[:400] + ("…" if len(result) > 400 else ""), style=THEME["tool_res"]),
            title=f"[{THEME['tool_res']}]✔  SEARCH RESULTS[/]",
            border_style="#87d7af", padding=(0, 1)
        ))
        return result
    except Exception as e:
        return f"Search failed: {e}"

TOOLS = [shell, read_file, write_file, list_files, web_search]

@dataclass
class ContextMemory:
    messages: deque = field(default_factory=lambda: deque(maxlen=40))
    session_id: str = field(default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S"))
    task_log: list = field(default_factory=list)
    file_changes: list = field(default_factory=list)
    summary: str = ""

    def add(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})

    def record_task(self, task: str):
        self.task_log.append(task)

    def record_file(self, path: str):
        self.file_changes.append(path)

    def build_system_prompt(self) -> str:
        parts = [
            "You are an autonomous research agent. You have tools to run shell commands, "
            "read/write files, list directories, and search the web.",
            "",
            "RULES:",
            "1. ALWAYS use your tools to complete tasks. Never fake or simulate tool calls.",
            "2. READ files before editing them.",
            "3. After completing a task, give a concise 1-3 line summary of what was done.",
            "4. If a tool fails, report the error honestly. Do not invent results.",
            "5. When writing code to generate visualizations, actually execute it with the shell tool.",
            "6. Save all output files to the current working directory or a subfolder.",
            "7. ALWAYS use `write_file` to write Python scripts to disk, THEN run them with `shell`. NEVER use bash heredocs (e.g. `python3 - <<EOF`) as they cause syntax escapes.",
            "8. ONLY invoke tools via the native structured function calling API. Rely EXCLUSIVELY on the backend JSON schema. Do not write raw XML tags in your plaintext response.",
            "9. STRIVE FOR EXTRAORDINARY QUALITY. If a user request is open-ended or vague, proactively expand the scope to deliver a comprehensive, premium-tier result. Do not do the bare minimum.",
            "10. BE RELENTLESS. If a tool fails or data is missing, immediately pivot to alternative methods. Do not skip steps, simulate success, or quit early.",
        ]
        
        if self.messages:
            parts.append("\n=== RECENT CHAT HISTORY ===")
            for m in list(self.messages)[-15:]:
                parts.append(f"{m['role'].upper()}: {m['content']}")
            parts.append("===========================\n")
            
        if self.task_log:
            parts.append("\nCompleted tasks:")
            parts.extend(f"  ✓ {t}" for t in self.task_log[-5:])
            
        if self.file_changes:
            recent = list(dict.fromkeys(self.file_changes))[-8:]
            parts.append("\nFiles touched:")
            parts.extend(f"  • {f}" for f in recent)
            
        return "\n".join(parts)

    def save(self, path: Path):
        data = {
            "session_id": self.session_id,
            "summary": self.summary,
            "task_log": self.task_log,
            "file_changes": self.file_changes,
            "messages": list(self.messages),
        }
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, path: Path) -> "ContextMemory":
        data = json.loads(path.read_text())
        obj = cls()
        obj.session_id   = data["session_id"]
        obj.summary      = data.get("summary", "")
        obj.task_log     = data.get("task_log", [])
        obj.file_changes = data.get("file_changes", [])
        obj.messages     = deque(data.get("messages", []), maxlen=40)
        return obj

def _detect_cuda() -> bool:
    nvcc_ok = subprocess.run(["nvcc", "--version"], capture_output=True).returncode == 0
    smi_ok  = subprocess.run(["nvidia-smi"], capture_output=True).returncode == 0
    return nvcc_ok and smi_ok

def ensure_ollama_model(model_id: str) -> bool:
    which = subprocess.run(["which", "ollama"], capture_output=True)
    if which.returncode != 0:
        console.print(f"[{THEME['error']}]✘[/]  'ollama' not found. Install from https://ollama.com")
        return False
    result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
    local_models = [line.split()[0] for line in result.stdout.splitlines()
                    if line.strip() and not line.startswith("NAME")]
    if any(model_id == m or model_id == m.split(":")[0] for m in local_models):
        console.print(f"[{THEME['dim']}]Model '{model_id}' already available locally.[/]")
        return True
    console.print(f"[{THEME['warning']}]⬇  Pulling '{model_id}' from Ollama…[/]")
    pull = subprocess.run(["ollama", "pull", model_id])
    if pull.returncode == 0:
        console.print(f"[{THEME['success']}]✔[/]  Pulled '{model_id}' successfully.")
        return True
    console.print(f"[{THEME['error']}]✘[/]  Failed to pull '{model_id}'.")
    return False

def load_env():
    env_file = Path(".env")
    if env_file.exists():
        for line in env_file.read_text(errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ[key.strip()] = val.strip()

def save_env(key: str, val: str):
    env_file = Path(".env")
    lines = env_file.read_text(errors="ignore").splitlines() if env_file.exists() else []
    updated = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={val}"
            updated = True
            break
    if not updated:
        lines.append(f"{key}={val}")
    env_file.write_text("\n".join(lines))

def ensure_api_keys(model_id: str):
    mid = model_id.lower()
    
    def _prompt_and_save(key_name: str, msg: str):
        if not os.environ.get(key_name):
            val = Prompt.ask(msg, password=True, console=console).strip()
            if val:
                os.environ[key_name] = val
                save_env(key_name, val)

    if "gemini" in mid:
        _prompt_and_save("GOOGLE_API_KEY", f"[{THEME['warning']}]GOOGLE_API_KEY[/]")
    if "claude" in mid:
        _prompt_and_save("ANTHROPIC_API_KEY", f"[{THEME['warning']}]ANTHROPIC_API_KEY[/]")
    if mid.startswith("openai/"):
        _prompt_and_save("OPENAI_API_KEY", f"[{THEME['warning']}]OPENAI_API_KEY[/]")
    if mid.startswith("groq/"):
        if not os.environ.get("GROQ_API_KEY"):
            console.print(f"  [{THEME['dim']}]Get your API key at https://console.groq.com[/]")
            _prompt_and_save("GROQ_API_KEY", f"[{THEME['warning']}]GROQ_API_KEY[/]")

def build_llm(model_id: str):
    if model_id.startswith("groq/"):
        return Groq(id=model_id[5:])
    if model_id.startswith("openai/"):
        from agno.models.openai import OpenAIChat
        return OpenAIChat(id=model_id[7:])
    if model_id.startswith("ollama/"):
        id_str = model_id[7:]
        ensure_ollama_model(id_str)
        return Ollama(id=id_str)
    
    mid = model_id.lower()
    if "gemini" in mid:
        return Gemini(id=model_id)
    elif "claude" in mid:
        return Claude(id=model_id)
    else:
        return Ollama(id=model_id)

def decompose_task(llm, task: str) -> list[str]:
    console.print(f"\n[{THEME['dim']}]Decomposing task into steps…[/]\n")
    prompt = (
        f'Break this task into highly detailed, exhaustive ordered atomic steps: "{task}"\n\n'
        'You MUST proactively expand vague requests to include rigorous research, robust error-handling, edge-case coverage, and professional quality assurance.\n'
        'Assume the user wants a premium, production-level outcome and DO NOT take shortcuts.\n'
        'Reply ONLY with a JSON array of strings like: ["step 1", "step 2"]\n'
        'No explanation, no markdown, just the JSON array.'
    )
    try:
        agent = Agent(model=llm, markdown=False)
        resp = agent.run(prompt)
        text = resp.content.strip() if hasattr(resp, 'content') and resp.content else ""
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        steps = json.loads(text.strip())
        if isinstance(steps, list) and steps:
            return [str(s) for s in steps]
    except Exception:
        pass
    return [task]

def build_agent(llm, mem: ContextMemory) -> Agent:
    return Agent(
        model=llm,
        tools=TOOLS,
        description=mem.build_system_prompt(),
        markdown=True
    )

def run_step(agent: Agent, mem: ContextMemory, step: str, step_num: int, total: int) -> str:
    console.print()
    console.print(Rule(f"[{THEME['primary']}]Step {step_num}/{total}[/]", style=THEME["secondary"]))
    console.print(Panel(
        Text(step, style=THEME["user"]),
        title=f"[{THEME['user']}]📋 Task[/]",
        border_style=THEME["secondary"], padding=(0, 2)
    ))

    max_retries = 3
    content = ""
    start = time.time()
    current_step_prompt = step

    for attempt in range(max_retries):
        try:
            response = agent.run(current_step_prompt)
            if hasattr(response, 'content') and response.content:
                content = str(response.content)
            else:
                content = str(response)
            
            break # Success, break out of retry loop
            
        except Exception as exc:
            err_msg = str(exc)
            
            if attempt < max_retries - 1:
                console.print(f"[{THEME['warning']}]⚠ API Exception caught (Attempt {attempt+1}/{max_retries}). LLM self-correcting syntax...[/]")
                console.print(f"[{THEME['dim']}]Error details: {err_msg}[/]")
                # Feed the failure traceback back into the LLM context so it can fix itself
                current_step_prompt = (
                    f"SYSTEM ALERT: Your previous tool execution crashed the API with this validation error:\n{err_msg}\n\n"
                    "You failed to use proper native JSON tooling schemas. Please correct your formatting syntax immediately and retry executing the tools to fulfill the user's task."
                )
                time.sleep(2)
            else:
                content = f"[ERROR] {err_msg}"
                console.print(f"[{THEME['error']}]✘ Final attempt failed: {content}[/]")

    elapsed = time.time() - start

    if content and not content.startswith("[ERROR]"):
        console.print()
        console.print(Panel(
            Text(content),
            title=f"[{THEME['success']}]✦ Agent  {elapsed:.1f}s[/]",
            border_style="#5fff87", padding=(1, 2)
        ))
        mem.add("assistant", content)

    return content

def print_header():
    header = Text()
    header.append("  ╔══════════════════════════════════════╗\n", style=THEME["secondary"])
    header.append("  ║", style=THEME["secondary"])
    header.append("  AUTONOMOUS RESEARCH AGENT           ", style=THEME["primary"])
    header.append("║\n", style=THEME["secondary"])
    header.append("  ║", style=THEME["secondary"])
    header.append("  Deep Research Studio  ·  v2.0       ", style=THEME["muted"])
    header.append("║\n", style=THEME["secondary"])
    header.append("  ╚══════════════════════════════════════╝\n", style=THEME["secondary"])
    console.print(header)

def print_help():
    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    table.add_column(style=THEME["tool"])
    table.add_column(style=THEME["dim"])
    table.add_row("/exit",          "Quit the session")
    table.add_row("/history",       "Show task log")
    table.add_row("/clear",         "Clear context")
    table.add_row("/save",          "Save session")
    table.add_row("/model",         "Switch model")
    table.add_row("/perms",         "Show permissions")
    table.add_row("/permit <tool>", "Enable: shell | web | file_read | file_write")
    table.add_row("/deny <tool>",   "Disable a permission")
    console.print(Panel(table, title="[dim]Commands[/dim]", border_style=THEME["muted"]))

def get_ollama_models() -> list[str]:
    result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
    if result.returncode != 0:
        return []
    models = []
    for line in result.stdout.splitlines():
        if line.strip() and not line.startswith("NAME"):
            models.append(line.split()[0])
    return models

def select_model() -> str:
    while True:
        console.print()
        choice = Prompt.ask(f"[{THEME['user']}]Provider (api / ollama)[/]", choices=["api", "ollama"], default="api", console=console)
        
        if choice == "api":
            provider = Prompt.ask(
                f"[{THEME['user']}]Select API Provider[/]", 
                choices=["groq", "google", "anthropic", "openai"], 
                default="groq", console=console
            )
            
            if provider == "groq":
                ensure_api_keys("groq/dummy")
                api_key = os.environ.get("GROQ_API_KEY")
                
                console.print(f"[{THEME['dim']}]Fetching live Groq models...[/]")
                try:
                    import requests
                    url = "https://api.groq.com/openai/v1/models"
                    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                    resp = requests.get(url, headers=headers, timeout=5)
                    if resp.status_code == 401:
                        console.print(f"[{THEME['error']}]✘ Authentication failed. API key is unauthorized.[/]")
                        os.environ.pop("GROQ_API_KEY", None)
                        continue
                    resp.raise_for_status()
                    
                    data = resp.json()
                    available = sorted([m["id"] for m in data.get("data", []) if "whisper" not in m["id"].lower()])
                    
                    if available:
                        table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
                        table.add_column(style=THEME["dim"])
                        table.add_column(style=THEME["dim"])
                        table.add_column(style=THEME["dim"])
                        for i in range(0, len(available), 3):
                            chunk = available[i:i+3]
                            while len(chunk) < 3:
                                chunk.append("")
                            table.add_row(*chunk)
                        console.print(Panel(table, title="[dim]Available API Models[/dim]", border_style=THEME["muted"]))
                except Exception as e:
                    console.print(f"[{THEME['warning']}]Could not fetch live Groq models ({e})[/]")
                    console.print(f"[{THEME['dim']}]Examples: llama-3.3-70b-versatile, mixtral-8x7b-32768, qwen-2.5-32b[/]")
                    
                base_id = Prompt.ask(f"[{THEME['user']}]Enter Groq Model[/]", default="llama-3.3-70b-versatile", console=console)
                model_id = "groq/" + base_id
                
            elif provider == "google":
                console.print(f"[{THEME['dim']}]Examples: gemini-2.5-flash, gemini-2.0-pro[/]")
                base_id = Prompt.ask(f"[{THEME['user']}]Enter Gemini Model[/]", default="gemini-2.5-flash", console=console)
                model_id = base_id
                
            elif provider == "anthropic":
                console.print(f"[{THEME['dim']}]Examples: claude-3-7-sonnet-latest, claude-3-5-sonnet-latest[/]")
                base_id = Prompt.ask(f"[{THEME['user']}]Enter Claude Model[/]", default="claude-3-7-sonnet-latest", console=console)
                model_id = base_id
                
            elif provider == "openai":
                console.print(f"[{THEME['dim']}]Examples: gpt-4o, o3-mini[/]")
                base_id = Prompt.ask(f"[{THEME['user']}]Enter OpenAI Model[/]", default="gpt-4o", console=console)
                model_id = "openai/" + base_id
        else:
            models = get_ollama_models()
            if not models:
                console.print(f"[{THEME['error']}]✘ No local Ollama models found.[/]")
                continue
            console.print(f"[{THEME['dim']}]Locally available: {', '.join(models)}[/]")
            base_id = Prompt.ask(f"[{THEME['user']}]Enter Ollama Model[/]", default=models[0] if models else "llama3.2", console=console)
            model_id = "ollama/" + base_id
            
        console.print(f"[{THEME['dim']}]Testing tool-call capabilities for '{base_id}'...[/]")
        
        while True:
            try:
                ensure_api_keys(model_id)
                llm = build_llm(model_id)
                test_agent = Agent(model=llm, tools=[list_files])
                resp = test_agent.run("List files in the current directory.")
                
                if not getattr(resp, "content", None):
                    raise ValueError("Empty response received. This model likely does not natively support tool calling.")
                
                console.print(f"[{THEME['success']}]✔ Model '{base_id}' authenticated and supports tool-calling.[/]")
                return model_id
            except Exception as e:
                error_str = str(e).lower()
                is_auth_error = any(key in error_str for key in ["401", "unauthorized", "authentication", "api_key", "invalid api"])
                
                if is_auth_error:
                    console.print(f"[{THEME['error']}]✘ API Key Invalid or Expired: {e}[/]")
                    if "groq" in model_id.lower(): os.environ.pop("GROQ_API_KEY", None)
                    if "gemini" in model_id.lower(): os.environ.pop("GOOGLE_API_KEY", None)
                    if "claude" in model_id.lower(): os.environ.pop("ANTHROPIC_API_KEY", None)
                    if "openai" in model_id.lower(): os.environ.pop("OPENAI_API_KEY", None)
                    
                    retry = Confirm.ask(f"[{THEME['dim']}]Try entering a new key for API provider?[/]", default=True, console=console)
                    if not retry:
                        break # Goes back to selecting a new model provider
                else:
                    console.print(f"[{THEME['error']}]✘ Model '{base_id}' rejected tool-calls or lacked capabilities: {e}[/]\n[{THEME['warning']}]Please select a different model.[/]")
                    break

SESSIONS_DIR = Path(".agent_sessions")

def save_session(mem: ContextMemory):
    SESSIONS_DIR.mkdir(exist_ok=True)
    path = SESSIONS_DIR / f"{mem.session_id}.json"
    mem.save(path)
    console.print(f"[{THEME['success']}]✔[/] Session saved → {path}")

def load_last_session() -> Optional[ContextMemory]:
    if not SESSIONS_DIR.exists():
        return None
    sessions = sorted(SESSIONS_DIR.glob("*.json"))
    if not sessions:
        return None
    try:
        mem = ContextMemory.load(sessions[-1])
        console.print(f"[{THEME['dim']}]Loaded session {mem.session_id} ({len(mem.messages)} messages)[/]")
        return mem
    except Exception:
        return None

def select_project():
    PROJECTS_DIR = Path.home() / ".deepresearch" / "projects"
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    
    while True:
        projects = [d for d in PROJECTS_DIR.iterdir() if d.is_dir()]
        projects.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        console.print(f"\n[{THEME['primary']}]Registered Projects:[/]")
        if not projects:
            console.print(f"  [{THEME['dim']}]No projects found.[/]")
        else:
            for i, p in enumerate(projects, 1):
                console.print(f"  [{THEME['tool']}]{i}.[/] {p.name}")
        
        console.print(f"\n[{THEME['dim']}]Enter a number to select, or type 'new <name>' to create a project.[/]")
        choice = Prompt.ask(f"[{THEME['user']}]Project[/]", console=console).strip()
        
        if choice.lower().startswith("new "):
            name = choice[4:].strip()
            if name:
                new_proj = PROJECTS_DIR / name
                new_proj.mkdir(parents=True, exist_ok=True)
                os.chdir(new_proj)
                console.print(f"[{THEME['success']}]✔ Created and switched to project: {name}[/]\n")
                return
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(projects):
                os.chdir(projects[idx])
                console.print(f"[{THEME['success']}]✔ Switched to project: {projects[idx].name}[/]\n")
                return
        
        console.print(f"[{THEME['warning']}]Invalid choice. Try again.[/]")

def edit_plan(steps: list[str]) -> list[str]:
    if not steps: return steps
    
    while True:
        console.print(f"\n[{THEME['primary']}]Current Implementation Plan ({len(steps)} steps):[/]")
        for i, s in enumerate(steps, 1):
            console.print(f"  [{THEME['tool']}]{i}.[/] {s}")
            
        console.print(f"\n[{THEME['dim']}]Commands: 'start' to proceed | 'add <text>' | 'edit <num> <text>' | 'del <num>'[/]")
        cmd_input = Prompt.ask(f"[{THEME['user']}]Plan Action[/]", default="start", show_default=False, console=console).strip()
        parts = cmd_input.split(" ", 2)
        cmd = parts[0].lower()
        
        if cmd == "start" or not cmd:
            return steps
        elif cmd == "add" and len(parts) >= 2:
            steps.append(cmd_input[4:].strip())
        elif cmd == "del" and len(parts) >= 2 and parts[1].isdigit():
            idx = int(parts[1]) - 1
            if 0 <= idx < len(steps):
                steps.pop(idx)
        elif cmd == "edit" and len(parts) >= 3 and parts[1].isdigit():
            idx = int(parts[1]) - 1
            if 0 <= idx < len(steps):
                steps[idx] = parts[2].strip()
        else:
            console.print(f"[{THEME['warning']}]Invalid command.[/]")

def main():
    load_env()
    print_header()
    select_project()

    mem: ContextMemory
    if SESSIONS_DIR.exists() and any(SESSIONS_DIR.glob("*.json")):
        resume = Confirm.ask(f"[{THEME['dim']}]Resume last session?[/]", default=True, console=console)
        mem = load_last_session() if resume else ContextMemory()
    else:
        mem = ContextMemory()

    console.print(f"[{THEME['dim']}]Session: {mem.session_id}[/]\n")

    model_id = select_model()
    llm = build_llm(model_id)
    agent = build_agent(llm, mem)

    console.print(f"\n[{THEME['success']}]✔[/] Agent ready  [{THEME['dim']}]model={model_id}  framework=Agno[/]")
    print_help()

    while True:
        console.print()
        console.print(Rule(style=THEME["muted"]))
        task = Prompt.ask(f"\n[{THEME['primary']}]❯[/]", console=console).strip()

        if not task:
            continue

        if task.lower() in ("/exit", "exit", "quit"):
            save_session(mem)
            console.print(f"\n[{THEME['dim']}]Goodbye.[/]\n")
            break

        if task.lower() == "/history":
            if mem.task_log:
                for i, t in enumerate(mem.task_log, 1):
                    console.print(f"  [{THEME['dim']}]{i}.[/] {t}")
            else:
                console.print(f"[{THEME['dim']}]No tasks yet.[/]")
            continue

        if task.lower() == "/clear":
            mem = ContextMemory()
            agent = build_agent(llm, mem)
            console.print(f"[{THEME['warning']}]Context cleared.[/]")
            continue

        if task.lower() == "/save":
            save_session(mem)
            continue

        if task.lower() == "/model":
            model_id = select_model()
            llm = build_llm(model_id)
            agent = build_agent(llm, mem)
            console.print(f"[{THEME['success']}]✔[/] Switched to [{THEME['primary']}]{model_id}[/]")
            continue

        if task.lower() == "/perms":
            t = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
            t.add_column(style=THEME["tool"])
            t.add_column()
            for k, v in PERMISSIONS.items():
                t.add_row(k, f"[{THEME['success']}]✔ enabled[/]" if v else f"[{THEME['error']}]✘ disabled[/]")
            console.print(Panel(t, title="[dim]Permissions[/dim]", border_style=THEME["muted"]))
            continue

        if task.lower().startswith("/permit ") or task.lower().startswith("/deny "):
            action, _, key = task.partition(" ")
            key = key.strip().lower()
            if key not in PERMISSIONS:
                console.print(f"[{THEME['error']}]Unknown: '{key}'. Use: {', '.join(PERMISSIONS)}[/]")
            else:
                PERMISSIONS[key] = action.lower() == "/permit"
                state = f"[{THEME['success']}]enabled[/]" if PERMISSIONS[key] else f"[{THEME['error']}]disabled[/]"
                console.print(f"[{THEME['warning']}]{key}[/] → {state}")
            continue

        steps = decompose_task(llm, task)
        steps = edit_plan(steps)

        initial_len = len(steps)
        completed = 0
        
        while steps:
            step = steps.pop(0)
            completed += 1
            
            mem.add("user", step)
            agent = build_agent(llm, mem)
            run_step(agent, mem, step, completed, completed + len(steps))
            mem.record_task(step)
            
            if steps:
                proceed = Prompt.ask(
                    f"\n[{THEME['warning']}]▶ Next up:[/] {steps[0][:80]}...\n[{THEME['dim']}]Press Enter to proceed, type 'edit' to change remaining plan, or 'stop' to cancel[/]",
                    default="", show_default=False, console=console
                ).strip().lower()
                
                if proceed == "stop":
                    console.print(f"[{THEME['warning']}]⏸  Execution stopped.[/]")
                    break
                elif proceed == "edit":
                    steps = edit_plan(steps)

        save_session(mem)

if __name__ == "__main__":
    main()
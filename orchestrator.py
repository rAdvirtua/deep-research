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

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_anthropic import ChatAnthropic
from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(script_dir)
os.chdir(current_dir)
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

@tool
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

@tool
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

@tool
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

@tool
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

@tool
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
        from langchain_community.tools import DuckDuckGoSearchRun
        search = DuckDuckGoSearchRun()
        result = search.run(query)
        result = result[:2000] + ("…(truncated)" if len(result) > 2000 else "")
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
        ]
        if self.task_log:
            parts.append("\nCompleted tasks:")
            parts.extend(f"  ✓ {t}" for t in self.task_log[-5:])
        if self.file_changes:
            recent = list(dict.fromkeys(self.file_changes))[-8:]
            parts.append("\nFiles touched:")
            parts.extend(f"  • {f}" for f in recent)
        return "\n".join(parts)

    def to_lc_messages(self) -> list:
        result = []
        for m in self.messages:
            if m["role"] == "user":
                result.append(HumanMessage(content=m["content"]))
            elif m["role"] == "assistant":
                result.append(AIMessage(content=m["content"]))
        return result

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

def ensure_api_keys(model_id: str):
    mid = model_id.lower()
    if "gemini" in mid and not os.environ.get("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = Prompt.ask(
            f"[{THEME['warning']}]GOOGLE_API_KEY[/]", password=True, console=console)
    if "claude" in mid and not os.environ.get("ANTHROPIC_API_KEY"):
        os.environ["ANTHROPIC_API_KEY"] = Prompt.ask(
            f"[{THEME['warning']}]ANTHROPIC_API_KEY[/]", password=True, console=console)
    if any(x in mid for x in ["llama", "mixtral", "gemma", "deepseek", "groq/", "qwen/qwen3-32b"]) or mid.startswith("groq/"):
        if not os.environ.get("GROQ_API_KEY"):
            console.print(f"  [{THEME['dim']}]Free key at https://console.groq.com[/]")
            os.environ["GROQ_API_KEY"] = Prompt.ask(
                f"[{THEME['warning']}]GROQ_API_KEY[/]", password=True, console=console)

def build_llm(model_id: str):
    mid = model_id.lower().replace("groq/", "")
    if "gemini" in mid:
        return ChatGoogleGenerativeAI(model=model_id, temperature=0)
    elif "claude" in mid:
        return ChatAnthropic(model=model_id, temperature=0)
    elif any(x in mid for x in ["llama", "mixtral", "gemma", "deepseek", "qwen2-", "qwen/qwen3-"]):
        return ChatGroq(model=mid, temperature=0)
    else:
        ensure_ollama_model(model_id)
        return ChatOllama(model=model_id, temperature=0)

def decompose_task(llm, task: str) -> list[str]:
    console.print(f"\n[{THEME['dim']}]Decomposing task into steps…[/]\n")
    prompt = (
        f'Break this task into ordered atomic steps: "{task}"\n\n'
        'Reply ONLY with a JSON array of strings like: ["step 1", "step 2"]\n'
        'No explanation, no markdown, just the JSON array.'
    )
    try:
        resp = llm.invoke([HumanMessage(content=prompt)])
        text = resp.content.strip()
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

def run_step(agent, mem: ContextMemory, step: str, step_num: int, total: int) -> str:
    console.print()
    console.print(Rule(f"[{THEME['primary']}]Step {step_num}/{total}[/]", style=THEME["secondary"]))
    console.print(Panel(
        Text(step, style=THEME["user"]),
        title=f"[{THEME['user']}]📋 Task[/]",
        border_style=THEME["secondary"], padding=(0, 2)
    ))

    history = mem.to_lc_messages()
    messages = history + [HumanMessage(content=step)]

    start = time.time()
    content = ""
    tool_calls_made = []

    try:
        result = agent.invoke({"messages": messages})
        all_messages = result.get("messages", [])

        for msg in all_messages:
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_calls_made.append(tc.get("name", "unknown"))
            if isinstance(msg, AIMessage) and msg.content:
                content = msg.content if isinstance(msg.content, str) else str(msg.content)

    except Exception as exc:
        content = f"[ERROR] {exc}"
        console.print(f"[{THEME['error']}]{content}[/]")

    elapsed = time.time() - start

    if content:
        console.print()
        console.print(Panel(
            Text(content),
            title=f"[{THEME['success']}]✦ Agent  {elapsed:.1f}s[/]",
            border_style="#5fff87", padding=(1, 2)
        ))
        mem.add("assistant", content)

    if tool_calls_made:
        console.print(f"[{THEME['dim']}]Tools used: {', '.join(tool_calls_made)}[/]")

    return content

def print_header():
    header = Text()
    header.append("  ╔══════════════════════════════════════╗\n", style=THEME["secondary"])
    header.append("  ║  ", style=THEME["secondary"])
    header.append("AUTONOMOUS RESEARCH AGENT", style=THEME["primary"])
    header.append("  ║\n", style=THEME["secondary"])
    header.append("  ║  ", style=THEME["secondary"])
    header.append("Deep Research Studio  ·  v1.0          ", style=THEME["muted"])
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

def select_model(default: str = "llama-3.3-70b-versatile") -> str:
    console.print(f"\n[{THEME['dim']}]Groq (free): llama-3.3-70b-versatile · mixtral-8x7b-32768  |  "
                  f"API: gemini-2.0-flash · claude-haiku-4-5-20251001  |  Local: qwen2.5:7b-instruct[/]")
    return Prompt.ask(f"[{THEME['user']}]Model[/]", default=default, console=console)

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

def main():
    print_header()

    mem: ContextMemory
    if SESSIONS_DIR.exists() and any(SESSIONS_DIR.glob("*.json")):
        resume = Confirm.ask(f"[{THEME['dim']}]Resume last session?[/]", default=True, console=console)
        mem = load_last_session() if resume else ContextMemory()
    else:
        mem = ContextMemory()

    console.print(f"[{THEME['dim']}]Session: {mem.session_id}[/]\n")

    model_id = select_model()
    ensure_api_keys(model_id)

    llm = build_llm(model_id)
    agent = create_react_agent(llm, TOOLS, prompt=mem.build_system_prompt())

    console.print(f"\n[{THEME['success']}]✔[/] Agent ready  [{THEME['dim']}]model={model_id}  framework=LangChain[/]")
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
            agent = create_react_agent(llm, TOOLS, prompt=mem.build_system_prompt())
            console.print(f"[{THEME['warning']}]Context cleared.[/]")
            continue

        if task.lower() == "/save":
            save_session(mem)
            continue

        if task.lower() == "/model":
            model_id = select_model(default=model_id)
            ensure_api_keys(model_id)
            llm = build_llm(model_id)
            agent = create_react_agent(llm, TOOLS, prompt=mem.build_system_prompt())
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

        if len(steps) > 1:
            console.print(f"\n[{THEME['primary']}]Task decomposed into {len(steps)} steps:[/]")
            for i, s in enumerate(steps, 1):
                console.print(f"  [{THEME['muted']}]{i}.[/] {s}")
            console.print()

        for i, step in enumerate(steps, 1):
            if i > 1:
                proceed = Confirm.ask(
                    f"\n[{THEME['warning']}]▶ Proceed with step {i}/{len(steps)}?[/]  [{THEME['dim']}]{step[:80]}[/]",
                    default=True, console=console
                )
                if not proceed:
                    console.print(f"[{THEME['warning']}]⏸  Stopped at step {i}.[/]")
                    break

            mem.add("user", step)
            run_step(agent, mem, step, i, len(steps))
            mem.record_task(step)

        save_session(mem)

if __name__ == "__main__":
    main()
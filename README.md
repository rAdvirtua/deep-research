# Deep Research Studio (Agno Engine)

An extraordinarily capable, terminal-based autonomous AI research and engineering agent. Built dynamically on top of the powerful **Agno Framework**, it can scan code, read local files, execute custom terminal setups, surf the web via DuckDuckGo, and write advanced multi-file Python architecture across isolated project workspaces.

---

## ⚡ One-Liner Installation

You can securely install and automatically deploy the orchestrator to your system path in seconds. Open your terminal and paste the single command corresponding to your OS:

### MacOS / Linux / WSL (Bash/ZSH)
```bash
curl -fsSL https://raw.githubusercontent.com/rAdvirtua/deep-research/main/install.sh | bash
```

### Windows (PowerShell)
```powershell
iwr https://raw.githubusercontent.com/rAdvirtua/deep-research/main/install.ps1 -useb | iex
```

*(Note: On Windows, you may need to close and reopen your PowerShell terminal once so that it can register the global `deep-research` command!)*

---

## 🚀 Features & Capabilities

1. **Intelligent Provider Abstractions**: Directly query open-source local LLMs (via Ollama) or instantly hook into cloud giants like Groq, Google Gemini, Anthropic Claude, and OpenAI without touching backend code.
2. **Project Context Isolation**: Deep Research inherently organizes its memory. The moment you type `deep-research`, it acts as a project dashboard, instantly restoring memory context for your isolated tasks.
3. **Interactive Plan Hacking**: After the AI analyzes your grand objective, it splits out a task checklist. Instead of instantly executing it, the orchestrator pauses and lets you locally add, edit, or delete the agent's planned subtasks dynamically!
4. **Agentic System Authorities**: The AI natively has real operating system access to manipulate files, run bash commands, and download modules on demand. 

---

## 🛡️ Avoiding Errors & Tool Halucinations

Because the Deep Research orchestrator operates fully autonomously, occasionally smaller open-source models (specifically fine-tuned Llama-3 endpoints running on Groq) will accidentally experience "syntax hallucinations". The model attempts to emit a raw `<function="shell">` XML tag instead of securely pushing strict JSON through the structured tools API, causing a 400 Validation Error.

**Do not panic. You do not need to do anything.**

- **Auto-Healing**: The engine has a bespoke multi-threaded recovery cycle. If Groq rejects the LLM's syntax, the orchestrator will intercept the crash silently, pause for 2 seconds, and forcefully inject the stack-trace back into the LLM's brain, commanding it to instantly rewrite its syntax organically. 
- **Switching Models**: If a specific LLM gets completely stuck in a loop trying to execute a tool (e.g., throwing repeated warnings), simply type `/model` in the console and immediately pivot to **OpenAI** or **Anthropic**. Commercial models drastically scale back syntax hallucinations and process tool executions virtually flawlessly on the first try!

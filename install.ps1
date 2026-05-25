$installDir = "$HOME\.deepresearch"
Write-Host "Setting up DeepResearch Pipeline in $installDir" -ForegroundColor Cyan

New-Item -ItemType Directory -Force -Path $installDir
cd $installDir
python -m venv venv

.\venv\Scripts\pip install agno rich requests psutil langchain-groq langchain-google-genai langchain-anthropic langchain-ollama langgraph

$shortcutPath = "$HOME\AppData\Local\Microsoft\WindowsApps\deep-research.bat"
$scriptPath = "$installDir\orchestrator.py"
"@echo off`n`"$installDir\venv\Scripts\python.exe`" `"$scriptPath`" %*" | Out-File $shortcutPath -Encoding ascii

Write-Host "--- Setup complete! Just run 'deep-research' in PowerShell. ---" -ForegroundColor Green
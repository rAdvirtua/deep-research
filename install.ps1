$projectDir = "$HOME\.deepresearch\repo"
$venvDir = "$HOME\.deepresearch\venv"
$scriptPath = "$projectDir\orchestrator.py"
$shortcutPath = "$HOME\AppData\Local\Microsoft\WindowsApps\deep-research.bat"

"@echo off`n`"$venvDir\Scripts\python.exe`" `"$scriptPath`" %*" | Out-File $shortcutPath -Encoding ascii

Write-Host "Fixed! Testing..." -ForegroundColor Green
deep-research
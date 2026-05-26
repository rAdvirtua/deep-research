$projectDir = Get-Location
$venvDir = "$HOME\.deepresearch\venv"
$scriptPath = "$projectDir\orchestrator.py"

$shortcutPath = "$HOME\AppData\Local\Microsoft\WindowsApps\deep-research.bat"

"@echo off`n`"$venvDir\Scripts\python.exe`" `"$scriptPath`" %*" | Out-File $shortcutPath -Encoding ascii

Write-Host "--- Setup complete! ---" -ForegroundColor Green
Write-Host "The command 'deep-research' now points to: $scriptPath" -ForegroundColor Cyan   
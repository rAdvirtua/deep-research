$deepResearchDir = "$HOME\.deepresearch"
$venvDir = "$deepResearchDir\venv"
$repoDir = "$deepResearchDir\repo"
$scriptPath = "$repoDir\orchestrator.py"
$shortcutPath = "$HOME\AppData\Local\Microsoft\WindowsApps\deep-research.bat"

Write-Host "Cloning repo..." -ForegroundColor Cyan
git clone https://github.com/rAdvirtua/deep-research.git $repoDir


Write-Host "Creating virtual environment..." -ForegroundColor Cyan
python -m venv $venvDir


Write-Host "Installing dependencies..." -ForegroundColor Cyan
& "$venvDir\Scripts\pip.exe" install -r "$repoDir\requirements.txt"

"@echo off`n`"$venvDir\Scripts\python.exe`" `"$scriptPath`" %*" | Out-File $shortcutPath -Encoding ascii

Write-Host "--- Setup complete! ---" -ForegroundColor Green
Write-Host "Run 'deep-research' to start." -ForegroundColor Cyan
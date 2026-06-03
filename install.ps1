$deepResearchDir = "$HOME\.deepresearch"
$venvDir = "$deepResearchDir\venv"
$repoDir = "$deepResearchDir\deep-research"

Write-Host "--- Setting up DeepResearch Pipeline ---" -ForegroundColor Cyan

if (-Not (Test-Path -Path $deepResearchDir)) {
    New-Item -ItemType Directory -Path $deepResearchDir | Out-Null
}

Set-Location $deepResearchDir

if (-Not (Test-Path -Path $repoDir)) {
    Write-Host "Cloning repo..." -ForegroundColor Cyan
    git clone https://github.com/rAdvirtua/deep-research.git $repoDir
} else {
    Write-Host "Updating repo..." -ForegroundColor Cyan
    Set-Location $repoDir
    git pull
    Set-Location $deepResearchDir
}

if (-Not (Test-Path -Path $venvDir)) {
    Write-Host "Creating virtual environment..." -ForegroundColor Cyan
    python -m venv $venvDir
}

$scriptPath = "$repoDir\orchestrator.py"
if (-Not (Test-Path -Path $scriptPath)) {
    $scriptPath = "$repoDir\deep-research\orchestrator.py"
}

Write-Host "Installing dependencies..." -ForegroundColor Cyan
& "$venvDir\Scripts\python.exe" -m pip install --upgrade pip

$reqPath = "$repoDir\deep-research\requirements.txt"
if (-Not (Test-Path -Path $reqPath)) {
    $reqPath = "$repoDir\requirements.txt"
}
if (Test-Path -Path $reqPath) {
    & "$venvDir\Scripts\pip.exe" install -r $reqPath
}

$localBin = "$HOME\.local\bin"
if (-Not (Test-Path -Path $localBin)) {
    New-Item -ItemType Directory -Path $localBin | Out-Null
}

$shortcutPath = "$localBin\deep-research.bat"
"@echo off`n`"$venvDir\Scripts\python.exe`" `"$scriptPath`" %*" | Out-File -FilePath $shortcutPath -Encoding ascii

$userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($userPath -notlike "*$localBin*") {
    Write-Host "Adding $localBin to User PATH..." -ForegroundColor Yellow
    [Environment]::SetEnvironmentVariable("PATH", "$userPath;$localBin", "User")
    Write-Host "Please restart your terminal if deep-research command is not recognized." -ForegroundColor Cyan
}

Write-Host "--- Setup complete! ---" -ForegroundColor Green
Write-Host "Run 'deep-research' to start." -ForegroundColor Cyan
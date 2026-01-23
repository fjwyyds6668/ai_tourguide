# Install dependencies script - prefer pre-compiled wheels
Write-Host "Upgrading pip..." -ForegroundColor Green
python -m pip install --upgrade pip

Write-Host "`nInstalling build tools..." -ForegroundColor Green
pip install setuptools>=69.0.0 wheel>=0.42.0

Write-Host "`nInstalling numpy (prefer pre-compiled wheels)..." -ForegroundColor Green
# Try to install pre-compiled numpy first
pip install numpy --only-binary :all: --upgrade 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Pre-compiled version not available, trying latest version..." -ForegroundColor Yellow
    pip install numpy --upgrade
}

Write-Host "`nInstalling pandas..." -ForegroundColor Green
pip install pandas --only-binary :all: --upgrade 2>$null
if ($LASTEXITCODE -ne 0) {
    pip install pandas --upgrade
}

Write-Host "`nInstalling other dependencies..." -ForegroundColor Green
pip install -r requirements.txt

Write-Host "`nInstallation completed!" -ForegroundColor Green


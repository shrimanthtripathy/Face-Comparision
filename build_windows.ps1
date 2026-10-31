# Builds dist\Nodal\Nodal.exe and installer\Nodal-Setup.exe  (run from the project folder, venv active)
$ErrorActionPreference = "Stop"
pip install -r requirements.txt pyinstaller
python -c "from insightface.app import FaceAnalysis; a=FaceAnalysis(name='buffalo_l',providers=['CPUExecutionProvider']); a.prepare(ctx_id=-1)"
$cal = @(); if (Test-Path backend\calibration.json) { $cal = @("--add-data", "backend\calibration.json;backend") }
pyinstaller launcher.py --name Nodal --noconfirm --windowed --onedir `
  --add-data "frontend;frontend" `
  --add-data "$env:USERPROFILE\.insightface\models\buffalo_l;models\models\buffalo_l" `
  --collect-all mediapipe --collect-all insightface --collect-all onnxruntime --collect-all reportlab `
  --collect-submodules uvicorn --collect-submodules multipart --hidden-import backend.main @cal
if (Get-Command iscc -ErrorAction SilentlyContinue) { iscc installer.iss } else { Write-Host "Inno Setup not found: zip dist\Nodal instead." }

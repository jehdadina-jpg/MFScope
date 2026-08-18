Set-Location 'C:\Users\mdadi\Downloads\MFScope'
Write-Host 'Backend starting on http://localhost:8000' -ForegroundColor Cyan
& 'C:\Users\mdadi\Downloads\MFScope\.venv\Scripts\uvicorn.exe' backend.api.main:app --reload --port 8000
Read-Host 'Press Enter to close'

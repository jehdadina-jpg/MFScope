@echo off
:: Launches start.ps1 via PowerShell — avoids all batch quoting issues.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"

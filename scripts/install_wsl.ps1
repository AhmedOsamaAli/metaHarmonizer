# One-shot elevated helper: install the WSL2 backend Docker Desktop needs.
# Run elevated. Writes a transcript to %TEMP%\wsl_install.log so the outer
# (non-elevated) session can read the result. A reboot is required afterward.
$log = Join-Path $env:TEMP 'wsl_install.log'
Start-Transcript -Path $log -Force | Out-Null
try {
    Write-Output "Enabling VirtualMachinePlatform + WSL features..."
    dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
    dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
    Write-Output "Running wsl --install --no-distribution..."
    wsl.exe --install --no-distribution
    Write-Output ("WSL_EXIT=" + $LASTEXITCODE)
}
catch {
    Write-Output ("ERROR: " + $_.Exception.Message)
}
finally {
    Write-Output "DONE"
    Stop-Transcript | Out-Null
}

param([ValidateSet('setup','chrome','check','collect')][string]$Mode)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
try {
    $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
    Set-Location -LiteralPath $ProjectRoot
    $Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
    $Profile = Join-Path $env:LOCALAPPDATA 'Autoblog\ChromeProfile'
    $Endpoint = 'http://127.0.0.1:9222'
    $env:PYTHONUTF8 = '1'

    function Assert-Chrome {
        $listeners = @(Get-NetTCPConnection -LocalPort 9222 -State Listen -ErrorAction SilentlyContinue)
        if ($listeners.Count -eq 0) { throw 'Run 02-open-naver-chrome.cmd first.' }
        foreach ($listener in $listeners) {
            if ($listener.LocalAddress -notin @('127.0.0.1','::1')) { throw 'CDP is not restricted to localhost.' }
            $owner = Get-CimInstance Win32_Process -Filter ("ProcessId = " + $listener.OwningProcess)
            $profileMatches = $false
            if ($owner -and $owner.CommandLine) {
                $match = [regex]::Match($owner.CommandLine, '(?:^|\s)--user-data-dir=(?:"([^"]+)"|([^\s"]+))(?=\s|$)')
                if ($match.Success) {
                    $actual = if ($match.Groups[1].Success) { $match.Groups[1].Value } else { $match.Groups[2].Value }
                    $profileMatches = [string]::Equals([IO.Path]::GetFullPath($actual).TrimEnd('\'),
                        [IO.Path]::GetFullPath($Profile).TrimEnd('\'), [StringComparison]::OrdinalIgnoreCase)
                }
            }
            if (-not $owner -or $owner.Name -ne 'chrome.exe' -or -not $profileMatches -or
                $owner.CommandLine -notmatch '(?:^|\s)--remote-debugging-port=9222(?=\s|$)') {
                throw 'Port 9222 belongs to another process/profile. Check and close only that process yourself.'
            }
        }
        $version = Invoke-RestMethod -Uri ($Endpoint + '/json/version') -TimeoutSec 5
        if (-not $version.webSocketDebuggerUrl) { throw 'CDP address not available.' }
    }

    if ($Mode -eq 'setup') {
        if (-not (Test-Path -LiteralPath $Python)) {
            $launcher = $null
            foreach ($candidate in @('py','python')) {
                if (Get-Command $candidate -ErrorAction SilentlyContinue) {
                    try {
                        & $candidate -c "import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)" 2>$null
                        if ($LASTEXITCODE -eq 0) { $launcher = $candidate; break }
                    } catch {
                        # Windows Store aliases or broken launchers may emit stderr.
                        # Try the next candidate before showing installation guidance.
                        continue
                    }
                }
            }
            if (-not $launcher) { throw 'Install Python 3.12 or newer from python.org with PATH enabled, then retry.' }
            & $launcher -m venv (Join-Path $ProjectRoot '.venv')
            if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
        }
        & $Python -c "import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)"
        if ($LASTEXITCODE -ne 0) { throw 'Existing .venv uses old Python. Rename .venv and retry.' }
        & $Python -m pip install -r requirements-browser.txt
        if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
        & $Python -m playwright install chromium
        if ($LASTEXITCODE -ne 0) { throw 'Test Chromium download failed.' }
        & $Python -m unittest discover -s tests -v
        if ($LASTEXITCODE -ne 0) { throw 'Tests failed. Save this output.' }
        Write-Host 'Setup complete. Next: 02-open-naver-chrome.cmd'
        exit 0
    }

    if ($Mode -eq 'chrome') {
        $listeners = @(Get-NetTCPConnection -LocalPort 9222 -State Listen -ErrorAction SilentlyContinue)
        if ($listeners.Count -eq 0) {
            $x86 = [Environment]::GetEnvironmentVariable('ProgramFiles(x86)')
            $candidates = @(
                (Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'),
                (Join-Path $env:LOCALAPPDATA 'Google\Chrome\Application\chrome.exe')
            )
            if ($x86) { $candidates += (Join-Path $x86 'Google\Chrome\Application\chrome.exe') }
            $chrome = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
            if (-not $chrome) { throw 'Install Google Chrome, then retry.' }
            New-Item -ItemType Directory -Force -Path $Profile | Out-Null
            $arguments = @(
                ('--user-data-dir="' + $Profile + '"'),
                '--remote-debugging-address=127.0.0.1',
                '--remote-debugging-port=9222',
                '--no-first-run',
                '--no-default-browser-check',
                'https://www.naver.com/'
            )
            Start-Process -FilePath $chrome -ArgumentList $arguments | Out-Null
            $ready = $false
            for ($i = 0; $i -lt 30; $i++) {
                Start-Sleep -Milliseconds 500
                if (@(Get-NetTCPConnection -LocalPort 9222 -State Listen -ErrorAction SilentlyContinue).Count -gt 0) {
                    Assert-Chrome
                    $ready = $true
                    break
                }
            }
            if (-not $ready) { throw 'CDP did not start. Close only the dedicated Autoblog Chrome and retry.' }
        } else { Assert-Chrome }
        Write-Host ('Dedicated Chrome ready. Profile: ' + $Profile)
        Write-Host 'Sign in to Naver yourself in this Chrome window and keep it open.'
        Write-Host 'CDP readiness does not verify Naver login or profile restart persistence.'
        exit 0
    }

    if (-not (Test-Path -LiteralPath $Python)) { throw 'Run 01-setup-windows.cmd first.' }
    Assert-Chrome
    $env:NAVER_CDP_ENDPOINT = $Endpoint
    $env:NAVER_CDP_PERSISTENT_CONTEXT = '1'
    $env:NAVER_PROFILE_CONTEXT = 'windows-autoblog-dedicated-profile'
    $env:NAVER_LOGIN_CONTEXT = 'windows-user-managed-login-not-verified'
    if ($Mode -eq 'check') {
        & $Python scripts/naver_collect.py --doctor
        if ($LASTEXITCODE -ne 0) { throw 'Collector diagnostic failed.' }
        & $Python scripts/windows/check_connection.py
        exit $LASTEXITCODE
    }
    if (-not (Test-Path -LiteralPath 'brief.json')) { throw 'Missing brief.json.' }
    $brief = Get-Content -LiteralPath 'brief.json' -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($brief.topic -is [string] -and -not [string]::IsNullOrWhiteSpace($brief.topic)) {
        foreach ($file in @('classification.json','naver-selectors.json')) {
            if (-not (Test-Path -LiteralPath $file)) { throw ('Missing ' + $file + '. Read docs/windows-pc.md.') }
        }
    }
    $output = 'runs/windows-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,8)
    & $Python scripts/naver_collect.py --brief brief.json --classification classification.json --selectors naver-selectors.json --output $output
    $result = $LASTEXITCODE
    Write-Host ('Evidence: ' + (Join-Path $ProjectRoot $output))
    exit $result
} catch {
    Write-Host ('BLOCKED: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}

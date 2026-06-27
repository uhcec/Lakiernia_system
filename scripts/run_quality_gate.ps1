$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command,

        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    & $Command
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "$Label failed with exit code $exitCode."
    }
}

Push-Location $repoRoot
try {
    Invoke-CheckedCommand { python -m pytest } "Backend tests"
    Invoke-CheckedCommand { python -m alembic upgrade head } "Alembic upgrade"
    Invoke-CheckedCommand { python -m alembic check } "Alembic check"

    Push-Location frontend
    try {
        Invoke-CheckedCommand { npm run test } "Frontend tests"
        Invoke-CheckedCommand { npm run build } "Frontend build"
    }
    finally {
        Pop-Location
    }
}
finally {
    Pop-Location
}

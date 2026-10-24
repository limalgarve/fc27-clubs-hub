$ErrorActionPreference = "Stop"
$folder = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $folder
$log = Join-Path $folder "LOG_FC27_WEB.txt"
$stdout = Join-Path $folder "LOG_SERVIDOR_FC27.txt"
$stderr = Join-Path $folder "LOG_SERVIDOR_FC27_ERROS.txt"

function Write-Log([string]$msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | $msg"
    Add-Content -Path $log -Value $line -Encoding UTF8
    Write-Host $msg
}
function Test-PortFree([int]$port) {
    return ($null -eq (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue))
}

"============================================================" | Set-Content $log -Encoding UTF8
"FC27 CLUBS HUB WEB - LOG V5" | Add-Content $log -Encoding UTF8
"Iniciado: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Add-Content $log -Encoding UTF8
"============================================================" | Add-Content $log -Encoding UTF8

try {
    if (Get-Command py -ErrorAction SilentlyContinue) { $python = "py" }
    elseif (Get-Command python -ErrorAction SilentlyContinue) { $python = "python" }
    else { throw "Python nao encontrado." }

    Write-Log "Python: $python"
    & $python --version 2>&1 | Tee-Object -FilePath $log -Append

    Write-Log "Verificando dependencias..."
    & $python -m pip install --disable-pip-version-check -q fastapi uvicorn jinja2 pandas openpyxl tzdata 2>&1 |
        Tee-Object -FilePath $log -Append
    if ($LASTEXITCODE -ne 0) { throw "Falha nas dependencias. Codigo $LASTEXITCODE" }

    $port = $null
    for ($p=8000; $p -le 8099; $p++) {
        if (Test-PortFree $p) { $port=$p; break }
        Write-Log "Porta $p ocupada. Tentando a proxima..."
    }
    if ($null -eq $port) { throw "Nenhuma porta livre entre 8000 e 8099." }

    $url = "http://127.0.0.1:$port"
    "FC27 Clubs Hub: $url" | Set-Content (Join-Path $folder "ENDERECO_FC27_WEB.txt") -Encoding UTF8
    if (Test-Path $stdout) { Remove-Item $stdout -Force }
    if (Test-Path $stderr) { Remove-Item $stderr -Force }

    Write-Log "Porta selecionada: $port"
    Write-Log "Iniciando servidor em $url"

    $args = @("-m","uvicorn","app:app","--host","127.0.0.1","--port","$port","--access-log")
    $proc = Start-Process -FilePath $python -ArgumentList $args -WorkingDirectory $folder `
        -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru

    Write-Log "Servidor iniciado. PID=$($proc.Id)"

    $ok=$false
    for($i=0;$i -lt 40;$i++){
        Start-Sleep -Milliseconds 500
        if($proc.HasExited){break}
        try {
            $r=Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
            if($r.StatusCode -eq 200){$ok=$true;break}
        } catch {}
    }
    if(-not $ok){
        if(Test-Path $stdout){Get-Content $stdout | Add-Content $log}
        if(Test-Path $stderr){Get-Content $stderr | Add-Content $log}
        throw "Servidor nao respondeu em $url."
    }

    Write-Log "Servidor respondendo normalmente."
    Start-Process $url
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Green
    Write-Host " FC27 CLUBS HUB ESTA RODANDO" -ForegroundColor Green
    Write-Host " $url" -ForegroundColor Cyan
    Write-Host "============================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "NAO FECHE ESTA JANELA enquanto estiver usando o site." -ForegroundColor Yellow
    Write-Host "Para encerrar, feche esta janela ou pressione CTRL+C." -ForegroundColor Yellow
    Write-Host ""

    # V5: não usa Read-Host/ENTER. A janela permanece viva enquanto o servidor existir.
    while(-not $proc.HasExited){
        Start-Sleep -Seconds 2
    }

    Write-Log "O processo do servidor terminou. Codigo=$($proc.ExitCode)"
    if(Test-Path $stderr){
        $err = Get-Content $stderr -Raw
        if($err){ Add-Content $log "`r`n--- LOG DO SERVIDOR ---`r`n$err" }
    }
}
catch {
    Write-Log ("ERRO: " + $_.Exception.Message)
    Write-Log ("Detalhes: " + ($_ | Out-String))
    if(Test-Path $stdout){ Add-Content $log "`r`n--- STDOUT ---"; Get-Content $stdout | Add-Content $log }
    if(Test-Path $stderr){ Add-Content $log "`r`n--- STDERR ---"; Get-Content $stderr | Add-Content $log }
    Write-Host ""
    Write-Host "Consulte LOG_FC27_WEB.txt." -ForegroundColor Yellow
    pause
    exit 1
}

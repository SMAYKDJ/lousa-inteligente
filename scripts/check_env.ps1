# SmartBoard Classroom — verificação do ambiente (Windows)
# Apenas lê informações; não instala nem altera nada.

Write-Host "=== Sistema ==="
$os = Get-CimInstance Win32_OperatingSystem
Write-Host "$($os.Caption) $($os.Version) ($($os.OSArchitecture))"

Write-Host "`n=== Python ==="
foreach ($cmd in @("py", "python", "python3")) {
    $found = Get-Command $cmd -ErrorAction SilentlyContinue
    if ($found) { Write-Host "$cmd -> $($found.Source) : $(& $cmd --version 2>&1)" }
}
if (Get-Command py -ErrorAction SilentlyContinue) {
    Write-Host "Versoes registradas no launcher:"
    py -0p 2>&1
}

Write-Host "`n=== Bibliotecas relevantes ==="
$code = @"
import importlib
for mod in ['aiohttp', 'cryptography', 'PySide6', 'cv2', 'numpy', 'pytest', 'websockets']:
    try:
        m = importlib.import_module(mod)
        print(f'{mod}: {getattr(m, "__version__", "instalado")}')
    except Exception:
        print(f'{mod}: nao instalado')
"@
if (Get-Command python -ErrorAction SilentlyContinue) { python -c $code } else { Write-Host "python nao encontrado" }

Write-Host "`n=== Ferramentas ==="
foreach ($tool in @("pip", "node", "npm", "git")) {
    $found = Get-Command $tool -ErrorAction SilentlyContinue
    if ($found) { Write-Host "${tool}: $(& $tool --version 2>&1 | Select-Object -First 1)" }
    else { Write-Host "${tool}: nao encontrado" }
}

Write-Host "`n=== Rede (IPv4) ==="
Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
    ForEach-Object { Write-Host "$($_.InterfaceAlias): $($_.IPAddress)" }
Write-Host "Wi-Fi:"
netsh wlan show interfaces 2>$null | Select-String "SSID|Perfil|Profile" | Select-Object -First 2

Write-Host "`n=== Firewall do Windows ==="
Get-NetFirewallProfile -ErrorAction SilentlyContinue |
    ForEach-Object { Write-Host "$($_.Name): $(if ($_.Enabled) {'ativo'} else {'desativado'})" }

Write-Host "`n=== Escala de tela ==="
Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue |
    ForEach-Object { Write-Host "$($_.Name): $($_.CurrentHorizontalResolution)x$($_.CurrentVerticalResolution)" }

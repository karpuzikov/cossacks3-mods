# Cossacks 3 Startup Fix
# 1. Removes the DWM8And16BitMitigation compatibility setting from config.exe and cossacks.exe.
# 2. Patches 2 bytes in each so they no longer test every display mode at startup.
# -Restore undoes both. -NoPatch applies only step 1.
param(
    [string]$GamePath,
    [switch]$Restore,
    [switch]$NoPatch
)
$ErrorActionPreference = 'Stop'
$exeNames = 'config.exe', 'cossacks.exe'
$layers = 'Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers'
$flag = 'DWM8And16BitMitigation'

function Find-Game {
    $steam = (Get-ItemProperty 'HKCU:\Software\Valve\Steam' -ErrorAction SilentlyContinue).SteamPath
    if (-not $steam) { return }
    $libs = @($steam)
    $vdf = Join-Path $steam 'steamapps\libraryfolders.vdf'
    if (Test-Path $vdf) {
        $libs += Select-String -Path $vdf -Pattern '"path"\s+"([^"]+)"' |
            ForEach-Object { $_.Matches[0].Groups[1].Value.Replace('\\', '\') }
    }
    foreach ($lib in $libs) {
        $dir = Join-Path $lib 'steamapps\common\Cossacks 3'
        if (Test-Path (Join-Path $dir 'cossacks.exe')) { return [IO.Path]::GetFullPath($dir) }
    }
}

# push 6 / lea eax,[ebp-x] / push eax / call ChangeDisplaySettingsA / test eax,eax / jne
# "push 6" (6A 06) becomes "jmp +0x14" (EB 14), which skips the test and keeps the mode.
function Find-Site([byte[]]$bytes) {
    $text = [Text.Encoding]::GetEncoding(28591).GetString($bytes)
    $pattern = '(?s)(?:\x6A\x06|\xEB\x14)\x8D\x85.\xFF\xFF\xFF\x50\xE8....\x85\xC0\x0F\x85....'
    $found = [regex]::Matches($text, $pattern)
    if ($found.Count -ne 1) { return -1 }
    return $found[0].Index
}

if (-not $GamePath) { $GamePath = Find-Game }
if (-not $GamePath -or -not (Test-Path (Join-Path $GamePath 'cossacks.exe'))) {
    throw 'Cossacks 3 not found. Run again with -GamePath "C:\...\Cossacks 3".'
}
$GamePath = (Resolve-Path $GamePath).Path.TrimEnd('\')
if (Get-Process config, cossacks -ErrorAction SilentlyContinue) {
    throw 'Close the game and the config tool first.'
}
Write-Host "Game folder: $GamePath"
$backup = Join-Path $GamePath 'startup_fix_backup'
$compatFile = Join-Path $backup 'compat.txt'
$key = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($layers)

foreach ($name in $exeNames) {
    $exe = Join-Path $GamePath $name
    $saved = Join-Path $backup "$name.orig"
    $value = [string]$key.GetValue($exe)

    if ($Restore) {
        $bytes = [IO.File]::ReadAllBytes($exe)
        $at = Find-Site $bytes
        if ($at -ge 0 -and $bytes[$at] -eq 0xEB) {
            $bytes[$at] = 0x6A; $bytes[$at + 1] = 0x06
            [IO.File]::WriteAllBytes($exe, $bytes)
            Write-Host "$name : patch removed"
        } else { Write-Host "$name : not patched" }
        if ((Test-Path $compatFile) -and (Get-Content $compatFile) -contains $name) {
            if (($value -split ' ') -notcontains $flag) {
                $new = if ($value) { "$value $flag" } else { $flag }
                $key.SetValue($exe, $new)
                Write-Host "$name : compatibility setting restored"
            }
        }
        continue
    }

    # step 1: compatibility setting
    $parts = @($value -split ' ' | Where-Object { $_ })
    if ($parts -contains $flag) {
        New-Item -ItemType Directory -Force $backup | Out-Null
        if (-not (Test-Path $compatFile) -or (Get-Content $compatFile) -notcontains $name) {
            Add-Content $compatFile $name
        }
        $left = @($parts | Where-Object { $_ -ne $flag })
        if ($left.Count -eq 0 -or ($left.Count -eq 1 -and $left[0] -eq '~')) { $key.DeleteValue($exe) }
        else { $key.SetValue($exe, ($left -join ' ')) }
        Write-Host "$name : compatibility setting removed"
    } else { Write-Host "$name : compatibility setting not present" }

    # step 2: patch
    if ($NoPatch) { continue }
    $bytes = [IO.File]::ReadAllBytes($exe)
    $at = Find-Site $bytes
    if ($at -lt 0) { Write-Host "$name : unknown game version, NOT patched"; continue }
    if ($bytes[$at] -eq 0xEB) { Write-Host "$name : already patched"; continue }
    New-Item -ItemType Directory -Force $backup | Out-Null
    Copy-Item $exe $saved -Force
    $bytes[$at] = 0xEB; $bytes[$at + 1] = 0x14
    [IO.File]::WriteAllBytes($exe, $bytes)
    Write-Host "$name : patched (backup in startup_fix_backup)"
}
$key.Close()
Write-Host 'Done.'

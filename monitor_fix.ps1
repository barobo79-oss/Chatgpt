# ============================================================
#  보조 모니터(USB 그래픽 어댑터) 자동 복구 스크립트 v2
#  * 수행 내용 (모두 되돌릴 수 있는 안전한 조치):
#    1) 디스플레이 "확장 모드" 강제 전환 (DisplaySwitch)
#    2) PnP 장치 재검색 (pnputil /scan-devices)
#    3) 비활성/오류 상태의 USB 그래픽 장치 재활성화
#    4) DisplayLink 서비스 재시작
#    5) 조치 전/후 활성 모니터 수 비교
#  * 파일 삭제/레지스트리 변경/보안 설정 변경은 하지 않습니다.
#  * 실행 방법: 같은 폴더의 run_fix.bat 더블클릭 (관리자 권한 자동 요청)
# ============================================================

# ---- 관리자 권한 자동 상승 ----
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if(-not $isAdmin){
  Write-Host "관리자 권한이 필요하여 권한 상승 창을 띄웁니다. '예'를 눌러주세요..."
  $psExe = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
  $elevated = $false
  try {
    Start-Process -FilePath $psExe -Verb RunAs -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File', ('"{0}"' -f $MyInvocation.MyCommand.Path)) -ErrorAction Stop
    $elevated = $true
  } catch {
    Write-Host "권한 상승이 거부되었습니다. 관리자 권한 없이 가능한 조치만 시도합니다."
    Start-Sleep -Seconds 2
  }
  if($elevated){ exit }
}

$ErrorActionPreference = 'SilentlyContinue'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$log = New-Object System.Collections.ArrayList
function Add-Line($t){ [void]$log.Add([string]$t); Write-Host $t }
function Section($t){ Add-Line ""; Add-Line ("===== " + $t + " =====") }

# 활성(실제 화면 출력 중) 모니터 수. -1 = 조회 실패
function Get-MonitorCount {
  try {
    $ids = @(Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorID -ErrorAction Stop | Where-Object { $_.Active })
    return $ids.Count
  } catch { return -1 }
}

$vidPattern = 'VID_(17E9|1D5C|0711|090C|345C)'
$namePattern = 'DisplayLink|USB.*Display|USB.*Graphic|USB.*Monitor|USB.*VGA|USB.*HDMI'

Add-Line ("복구 시작 : " + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
Add-Line ("관리자 권한 : " + $isAdmin)
$build = 0
try { $build = [int](Get-CimInstance Win32_OperatingSystem -ErrorAction Stop).BuildNumber } catch {}
Add-Line ("OS 빌드 : " + $build)
$before = Get-MonitorCount
$beforeTxt = '확인 불가'
if($before -ge 0){ $beforeTxt = [string]$before }
Add-Line ("조치 전 활성 모니터 수 : " + $beforeTxt)

Section "1. 디스플레이 확장 모드 전환"
# 'PC 화면만' 모드로 잠겨 있으면 보조 모니터가 켜지지 않음 → 확장 모드로 전환
# Windows 11 22H2(빌드 22621) 이상은 /extend 문자 스위치를 무시하므로 숫자 인수 3 을 사용
try {
  $dsArg = '/extend'
  if($build -ge 22621){ $dsArg = '3' }
  Start-Process -FilePath "$env:WINDIR\System32\DisplaySwitch.exe" -ArgumentList $dsArg -WindowStyle Hidden -ErrorAction Stop
  Add-Line ("→ 확장(Extend) 모드 전환 요청 완료 (인수 " + $dsArg + ")")
  Add-Line "  ※ 원래 화면 모드로 되돌리려면 Win + P 를 눌러 원하는 모드를 선택하세요"
} catch { Add-Line "→ DisplaySwitch 실행 실패" }
Start-Sleep -Seconds 3

Section "2. PnP 장치 재검색"
# pnputil /scan-devices 는 Windows 10 2004(빌드 19041) 이상에서만 지원
if($build -ge 19041){
  try {
    & "$env:WINDIR\System32\pnputil.exe" /scan-devices *> $null
    Add-Line ("→ pnputil /scan-devices 실행 완료 (종료 코드 " + $LASTEXITCODE + ")")
  } catch { Add-Line "→ pnputil 실행 실패" }
} else {
  Add-Line "→ 이 Windows 버전은 자동 재검색 미지원."
  Add-Line "  장치 관리자에서 [동작 > 하드웨어 변경 사항 검색]을 직접 실행하세요."
}
Start-Sleep -Seconds 3

Section "3. USB 그래픽 장치 재활성화"
Add-Line "※ 이 단계에서 화면이 몇 초간 깜빡이거나 잠시 꺼질 수 있습니다."
$acted = $false
try {
  $devs = Get-PnpDevice -PresentOnly -ErrorAction Stop | Where-Object {
    $_.InstanceId -match $vidPattern -or $_.FriendlyName -match $namePattern
  }
  if(-not $devs){ Add-Line "→ 현재 연결된 USB 그래픽 장치가 없음 (아래 '다음 단계' 참고)" }
  foreach($d in $devs){
    $prob = $null
    try { $prob = (Get-PnpDeviceProperty -InstanceId $d.InstanceId -KeyName 'DEVPKEY_Device_ProblemCode' -ErrorAction Stop).Data } catch {}
    Add-Line ("- 발견 : " + $d.FriendlyName + "  (상태=" + $d.Status + ", 문제코드=" + $prob + ")")
    if($d.Status -eq 'OK'){ Add-Line "    → 이미 정상 상태, 조치 불필요"; continue }
    if(-not $isAdmin){ Add-Line "    → 관리자 권한이 없어 재활성화 생략"; continue }
    $acted = $true
    try {
      if($prob -eq 22){
        # 코드 22 = 사용자가(또는 프로그램이) 비활성화한 장치 → 활성화만
        Enable-PnpDevice -InstanceId $d.InstanceId -Confirm:$false -ErrorAction Stop
      } else {
        # 그 외 오류 → 장치 재시작 (장치관리자의 비활성화 후 재활성화와 동일)
        Disable-PnpDevice -InstanceId $d.InstanceId -Confirm:$false -ErrorAction Stop
        Start-Sleep -Seconds 2
        Enable-PnpDevice -InstanceId $d.InstanceId -Confirm:$false -ErrorAction Stop
      }
    } catch {
      # 활성화 실패 → 잠시 후 한 번 더 재시도
      Start-Sleep -Seconds 3
      try { Enable-PnpDevice -InstanceId $d.InstanceId -Confirm:$false -ErrorAction Stop } catch {}
    }
    # 성공 메시지를 미리 출력하지 않고, 실제 결과를 다시 조회해서 보고
    Start-Sleep -Seconds 2
    $chk = $null
    try { $chk = Get-PnpDevice -InstanceId $d.InstanceId -ErrorAction Stop } catch {}
    if($chk -and $chk.Status -eq 'OK'){
      Add-Line "    → 장치 재활성화 성공 (상태=OK)"
    } elseif($chk){
      Add-Line ("    → 조치 후에도 장치가 정상이 아님 (상태=" + $chk.Status + ")")
      Add-Line "      run_fix.bat 을 다시 실행하거나, PC 재부팅 후 한 번 더 실행해 보세요."
      Add-Line "      (장치 관리자에서 해당 장치 우클릭 > [디바이스 사용]으로 직접 켤 수도 있음)"
    } else {
      Add-Line "    → 조치 후 장치 상태 확인 실패 (장치 관리자에서 상태를 확인하세요)"
    }
  }
} catch { Add-Line "→ 장치 재활성화 중 오류" }
if($acted){ Start-Sleep -Seconds 5 }

Section "4. DisplayLink 서비스 재시작"
try {
  $svcs = Get-Service | Where-Object { $_.Name -match 'DisplayLink' -or $_.DisplayName -match 'DisplayLink' }
  if(-not $svcs){ Add-Line "→ DisplayLink 서비스 없음 (드라이버 미설치이거나 다른 칩셋)" }
  foreach($s in $svcs){
    if(-not $isAdmin){ Add-Line ("→ " + $s.DisplayName + " : 관리자 권한이 없어 재시작 생략"); continue }
    try {
      Restart-Service -Name $s.Name -Force -ErrorAction Stop
      $s.Refresh()
      Add-Line ("→ " + $s.DisplayName + " 재시작 (상태=" + $s.Status + ")")
    } catch { Add-Line ("→ " + $s.DisplayName + " 재시작 실패 - PC 재부팅을 권장합니다") }
  }
} catch { Add-Line "→ 서비스 재시작 중 오류" }
Start-Sleep -Seconds 3

Section "결과 확인"
$after = Get-MonitorCount
$afterTxt = '확인 불가'
if($after -ge 0){ $afterTxt = [string]$after }
Add-Line ("조치 전 활성 모니터 수 : " + $beforeTxt + "  →  조치 후 : " + $afterTxt)
if($after -ge 2){
  Add-Line "→ 성공! 보조 모니터가 활성 상태로 감지되었습니다."
} elseif($after -eq -1){
  Add-Line "→ 모니터 수를 확인하지 못했습니다. 보조 모니터에 화면이 나오는지 직접 확인해 주세요."
} else {
  Add-Line "→ 아직 보조 모니터가 감지되지 않습니다. 다음 단계를 순서대로 시도하세요:"
  Add-Line ""
  Add-Line "  [다음 단계 체크리스트]"
  Add-Line "  1) USB 케이블을 뽑았다가 '본체 뒷면'의 다른 USB 3.0 포트(파란색)에 다시 연결"
  Add-Line "  2) USB 허브를 거치지 말고 본체에 직접 연결"
  Add-Line "  3) 어댑터가 DisplayLink 계열이면 최신 드라이버 설치 후 재부팅:"
  Add-Line "     https://www.synaptics.com/products/displaylink-graphics/downloads"
  Add-Line "  4) Win + Ctrl + Shift + B (그래픽 드라이버 리셋 단축키) 눌러보기"
  Add-Line "  5) 그래도 안 되면 어댑터를 다른 PC에 꽂아 동작 확인 (하드웨어 고장 판별)"
  Add-Line ""
  Add-Line "  ※ 진단이 더 필요하면 run_diag.bat 을 실행해 리포트를 붙여넣어 주세요."
}

# ---- 로그 저장 (스크립트 폴더 + 바탕화면 모두 시도) ----
# UAC 를 다른 관리자 계정으로 승인한 경우 '바탕화면'이 그 계정의 바탕화면으로
# 잡히므로, 항상 찾을 수 있는 스크립트 폴더에 먼저 저장한다.
$scriptDir = Split-Path -Parent $PSCommandPath
$desktop = [Environment]::GetFolderPath('Desktop')
$savedAny = $false
Add-Line ""
foreach($dir in @($scriptDir, $desktop) | Select-Object -Unique){
  if(-not $dir){ continue }
  $path = Join-Path $dir 'monitor_fix_log.txt'
  try {
    ($log -join "`r`n") | Out-File -FilePath $path -Encoding UTF8 -ErrorAction Stop
    Add-Line ("로그 저장됨 : " + $path)
    $savedAny = $true
  } catch {}
}
if(-not $savedAny){ Add-Line "로그 파일 저장 실패 (클립보드 복사만 시도합니다)" }
try { ($log -join "`r`n") | Set-Clipboard -ErrorAction Stop } catch {}

Add-Line ""
Read-Host "종료하려면 Enter 키를 누르세요"

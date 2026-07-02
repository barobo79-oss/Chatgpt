# ============================================================
#  보조 모니터(USB 그래픽 어댑터) 자동 복구 스크립트 v1
#  * 수행 내용 (모두 되돌릴 수 있는 안전한 조치):
#    1) 디스플레이 "확장 모드" 강제 전환 (DisplaySwitch /extend)
#    2) PnP 장치 재검색 (pnputil /scan-devices)
#    3) 비활성/오류 상태의 USB 그래픽 장치 재활성화
#    4) DisplayLink 서비스 재시작
#    5) 조치 전/후 모니터 감지 수 비교
#  * 파일 삭제/레지스트리 변경/보안 설정 변경은 하지 않습니다.
#  * 실행 방법: 같은 폴더의 run_fix.bat 더블클릭 (관리자 권한 자동 요청)
# ============================================================

# ---- 관리자 권한 자동 상승 ----
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if(-not $isAdmin){
  Write-Host "관리자 권한이 필요하여 권한 상승 창을 띄웁니다. '예'를 눌러주세요..."
  $elevated = $false
  try {
    Start-Process powershell -Verb RunAs -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File', ('"{0}"' -f $MyInvocation.MyCommand.Path)) -ErrorAction Stop
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

function Get-MonitorCount {
  try {
    $ids = Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorID -ErrorAction Stop
    return ($ids | Measure-Object).Count
  } catch { return -1 }
}

$vidPattern = 'VID_(17E9|1D5C|0711|090C|345C)'
$namePattern = 'DisplayLink|USB.*Display|USB.*Graphic|USB.*Monitor|USB.*VGA|USB.*HDMI'

Add-Line ("복구 시작 : " + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
Add-Line ("관리자 권한 : " + $isAdmin)
$before = Get-MonitorCount
Add-Line ("조치 전 감지된 모니터 수 : " + $before)

Section "1. 디스플레이 확장 모드 전환"
# 'PC 화면만' 모드로 잠겨 있으면 보조 모니터가 켜지지 않음 → 확장 모드로 전환
try {
  Start-Process -FilePath "$env:WINDIR\System32\DisplaySwitch.exe" -ArgumentList '/extend' -WindowStyle Hidden
  Add-Line "→ 확장(Extend) 모드 전환 요청 완료"
} catch { Add-Line "→ DisplaySwitch 실행 실패" }
Start-Sleep -Seconds 3

Section "2. PnP 장치 재검색"
try {
  $out = & "$env:WINDIR\System32\pnputil.exe" /scan-devices 2>&1
  Add-Line ("→ pnputil /scan-devices 실행 : " + (($out | Select-Object -Last 1)))
} catch { Add-Line "→ pnputil 실행 실패" }
Start-Sleep -Seconds 3

Section "3. USB 그래픽 장치 재활성화"
$acted = $false
try {
  $devs = Get-PnpDevice -PresentOnly | Where-Object {
    $_.InstanceId -match $vidPattern -or $_.FriendlyName -match $namePattern
  }
  if(-not $devs){ Add-Line "→ 현재 연결된 USB 그래픽 장치가 없음 (아래 '다음 단계' 참고)" }
  foreach($d in $devs){
    $prob = $null
    try { $prob = (Get-PnpDeviceProperty -InstanceId $d.InstanceId -KeyName 'DEVPKEY_Device_ProblemCode').Data } catch {}
    Add-Line ("- 발견 : " + $d.FriendlyName + "  (상태=" + $d.Status + ", 문제코드=" + $prob + ")")
    if($d.Status -eq 'OK'){ Add-Line "    → 이미 정상 상태, 조치 불필요"; continue }
    if(-not $isAdmin){ Add-Line "    → 관리자 권한이 없어 재활성화 생략"; continue }
    $acted = $true
    if($prob -eq 22){
      # 코드 22 = 사용자가(또는 프로그램이) 비활성화한 장치 → 활성화만
      Enable-PnpDevice -InstanceId $d.InstanceId -Confirm:$false
      Add-Line "    → 비활성화된 장치를 다시 활성화함"
    } else {
      # 그 외 오류 → 장치 재시작 (비활성화 후 재활성화 = 장치관리자에서 하는 것과 동일)
      Disable-PnpDevice -InstanceId $d.InstanceId -Confirm:$false
      Start-Sleep -Seconds 2
      Enable-PnpDevice -InstanceId $d.InstanceId -Confirm:$false
      Add-Line "    → 장치를 재시작함 (비활성화 후 재활성화)"
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
    Restart-Service -Name $s.Name -Force
    $s.Refresh()
    Add-Line ("→ " + $s.DisplayName + " 재시작 (상태=" + $s.Status + ")")
  }
} catch { Add-Line "→ 서비스 재시작 중 오류" }
Start-Sleep -Seconds 3

Section "결과 확인"
$after = Get-MonitorCount
Add-Line ("조치 전 모니터 수 : " + $before + "  →  조치 후 모니터 수 : " + $after)
if($after -gt $before -and $after -ge 2){
  Add-Line "→ 성공! 보조 모니터가 감지되었습니다."
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

# ---- 로그 저장 ----
$desktop = [Environment]::GetFolderPath('Desktop')
$path = Join-Path $desktop 'monitor_fix_log.txt'
try {
  ($log -join "`r`n") | Out-File -FilePath $path -Encoding UTF8
  Add-Line ""
  Add-Line ("로그 저장됨 : " + $path)
} catch {}
try { ($log -join "`r`n") | Set-Clipboard } catch {}

Add-Line ""
Read-Host "종료하려면 Enter 키를 누르세요"

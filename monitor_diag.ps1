# ============================================================
#  보조 모니터(USB 그래픽 어댑터) 진단 리포트 v2  -  읽기 전용(READ-ONLY)
#  * 이 스크립트는 상태를 "읽기만" 합니다.
#  * 아무것도 변경/삭제하지 않으며, 관리자 권한도 필요 없습니다.
#  * 실행 방법: 같은 폴더의 run_diag.bat 을 더블클릭 (경로 입력 불필요)
# ============================================================

$ErrorActionPreference = 'SilentlyContinue'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$report = New-Object System.Collections.ArrayList
function Add-Line($t){ [void]$report.Add([string]$t); Write-Host $t }
function Section($t){ Add-Line ""; Add-Line ("===== " + $t + " =====") }

Add-Line ("진단 시각    : " + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
Add-Line ("스크립트 위치 : " + $PSCommandPath)

Section "1. 시스템 정보"
try {
  $os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
  Add-Line ("OS       : " + $os.Caption + "  (빌드 " + $os.BuildNumber + ")")
  Add-Line ("컴퓨터명  : " + $env:COMPUTERNAME)
} catch { Add-Line "시스템 정보 조회 실패" }

# USB 그래픽 칩셋 제조사 VID 목록
$vids = @{ '17E9'='DisplayLink'; '1D5C'='Fresco Logic'; '0711'='MCT/Trigger'; '090C'='Silicon Motion'; '345C'='Silicon Motion(신형)' }
$vidPattern = 'VID_(17E9|1D5C|0711|090C|345C)'
$namePattern = 'DisplayLink|USB.*Display|USB.*Graphic|USB.*Monitor|USB.*VGA|USB.*HDMI'

Section "2. USB 그래픽 어댑터 검색 (연결 이력 포함)"
$found = $false
try {
  # -PresentOnly 를 쓰지 않음: 과거에 연결됐던(지금은 안 보이는) 장치도 찾기 위함
  $devs = Get-PnpDevice -ErrorAction Stop | Where-Object {
    $_.InstanceId -match $vidPattern -or $_.FriendlyName -match $namePattern
  }
  foreach($d in $devs){
    $found = $true
    $vid = '?'
    if($d.InstanceId -match 'VID_([0-9A-Fa-f]{4})'){ $vid = $matches[1].ToUpper() }
    $chip = '알수없음'
    if($vids.ContainsKey($vid)){ $chip = $vids[$vid] }
    $prob = $null
    try { $prob = (Get-PnpDeviceProperty -InstanceId $d.InstanceId -KeyName 'DEVPKEY_Device_ProblemCode' -ErrorAction Stop).Data } catch {}
    $state = [string]$d.Status
    if($state -eq 'Unknown'){ $state = 'Unknown (현재 미연결 - 과거 연결 이력)' }
    Add-Line ("- " + $d.FriendlyName)
    Add-Line ("    칩셋추정 : $chip (VID_$vid)  /  클래스 : " + $d.Class)
    Add-Line ("    상태     : " + $state + "   /   문제코드 : " + $prob)
  }
} catch { Add-Line "어댑터 조회 중 오류 (조회 실패 - 장치가 없다는 뜻이 아님)" }
if(-not $found){
  Add-Line "→ USB 그래픽 어댑터가 목록에 없음 (연결 이력조차 없음)."
  Add-Line "  가능성 : (1) USB 케이블/포트 접촉 불량  (2) 어댑터 자체 고장"
  Add-Line "           (3) 다른 포트에 꽂아야 함 (USB 3.0, 본체 뒷면 권장)"
}

Section "3. 문제 상태인 장치 전체"
try {
  $bad = @(Get-PnpDevice -PresentOnly -ErrorAction Stop | Where-Object { $_.Status -ne 'OK' })
  if($bad.Count -gt 0){
    foreach($b in ($bad | Select-Object -First 15)){
      $prob2 = $null
      try { $prob2 = (Get-PnpDeviceProperty -InstanceId $b.InstanceId -KeyName 'DEVPKEY_Device_ProblemCode' -ErrorAction Stop).Data } catch {}
      Add-Line ("- [" + $b.Status + " / 코드 " + $prob2 + "] (" + $b.Class + ") " + $b.FriendlyName)
    }
    if($bad.Count -gt 15){ Add-Line ("  ... 외 " + ($bad.Count - 15) + "개") }
  } else { Add-Line "문제 상태 장치 없음 (모든 장치 정상)" }
} catch { Add-Line "장치 상태 조회 실패" }

Section "4. 현재 연결된 모니터 / 그래픽 어댑터"
$monCount = -1   # -1 = 조회 실패
try {
  $ids = @(Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorID -ErrorAction Stop)
  $active = @($ids | Where-Object { $_.Active })
  $monCount = $active.Count
  Add-Line ("감지된 모니터 수 : " + $ids.Count + "  (활성 " + $active.Count + ")")
  foreach($m in $ids){
    try {
      # UserFriendlyName 은 문자코드(UInt16) 배열. 이름 없는 패널은 전부 0 이므로 필터 후 개수 확인
      $chars = @($m.UserFriendlyName | Where-Object { $_ -gt 0 })
      if($chars.Count -gt 0){
        $mn = (-join [char[]]$chars).Trim()
        if($mn){ Add-Line ("  - " + $mn) }
      }
    } catch {}
  }
} catch { Add-Line "모니터 수 조회 실패" }
try {
  Get-CimInstance Win32_VideoController -ErrorAction Stop | ForEach-Object {
    Add-Line ("그래픽 어댑터 : " + $_.Name + "  (상태=" + $_.Status + ")")
  }
} catch { Add-Line "그래픽 어댑터 조회 실패" }

Section "5. DisplayLink 등 USB 그래픽 드라이버/소프트웨어 설치 여부"
$dl = $false
try {
  Get-Service | Where-Object { $_.Name -match 'DisplayLink|FrescoLogic|MCT|SMI' -or $_.DisplayName -match 'DisplayLink|Fresco|USB Display' } |
    ForEach-Object { $dl = $true; Add-Line ("서비스 : " + $_.DisplayName + "  (상태=" + $_.Status + ")") }
} catch {}
try {
  $keys = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
          'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
  Get-ItemProperty $keys | Where-Object { $_.DisplayName -match 'DisplayLink|Fresco|MCT|USB Display|Trigger' } |
    ForEach-Object { $dl = $true; Add-Line ("설치됨 : " + $_.DisplayName + "  (버전=" + $_.DisplayVersion + ")") }
} catch {}
if(-not $dl){
  Add-Line "→ USB 그래픽 드라이버(DisplayLink 등) 미설치."
  Add-Line "  어댑터가 DisplayLink 계열이면 드라이버 설치 필요:"
  Add-Line "  https://www.synaptics.com/products/displaylink-graphics/downloads"
}

Section "6. 최근 설치된 Windows 업데이트 (문제 발생 시점 대조용)"
try {
  Get-HotFix -ErrorAction Stop | Sort-Object InstalledOn -Descending | Select-Object -First 6 | ForEach-Object {
    $d = '?'
    if($_.InstalledOn){ $d = $_.InstalledOn.ToString('yyyy-MM-dd') }
    Add-Line ("- " + $_.HotFixID + "  (" + $d + ")  " + $_.Description)
  }
} catch { Add-Line "업데이트 기록 조회 실패" }

Section "7. 최근 장치/드라이버 관련 시스템 이벤트 (최근 7일)"
try {
  $since = (Get-Date).AddDays(-7)
  $ev = Get-WinEvent -FilterHashtable @{ LogName='System'; StartTime=$since; Level=@(1,2,3) } -MaxEvents 300 -ErrorAction Stop |
        Where-Object { $_.ProviderName -match 'Kernel-PnP|UserPnp|PnP|DriverFrameworks|Display' } |
        Select-Object -First 15
  if($ev){
    foreach($e in $ev){
      $first = (($e.Message -split "`n")[0]).Trim()
      Add-Line ("- " + $e.TimeCreated.ToString('MM-dd HH:mm') + " [" + $e.ProviderName + "] " + $first)
    }
  } else { Add-Line "관련 이벤트 없음" }
} catch { Add-Line "이벤트 로그 조회 실패(일부 로그는 관리자 권한 필요)" }

Section "8. 설치된 보안 프로그램"
try {
  Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct -ErrorAction Stop |
    ForEach-Object { Add-Line ("백신 : " + $_.displayName) }
} catch { Add-Line "백신 목록(SecurityCenter2) 조회 불가" }

Section "리포트 저장"
# 바탕화면이 OneDrive 로 이동된 PC 에서도 실제 바탕화면 경로를 정확히 찾음
$desktop = [Environment]::GetFolderPath('Desktop')
$scriptDir = Split-Path -Parent $PSCommandPath
$saved = $false
foreach($dir in @($desktop, $scriptDir)){
  if($saved -or -not $dir){ continue }
  $path = Join-Path $dir 'monitor_diag_report.txt'
  try {
    ($report -join "`r`n") | Out-File -FilePath $path -Encoding UTF8 -ErrorAction Stop
    Add-Line ("→ 리포트 저장됨 : " + $path)
    $saved = $true
  } catch {}
}
if(-not $saved){ Add-Line "파일 저장 실패" }
try {
  ($report -join "`r`n") | Set-Clipboard -ErrorAction Stop
  Add-Line "→ 리포트가 클립보드에도 복사됨 (대화창에 Ctrl+V 로 붙여넣으세요)"
} catch {}

Add-Line ""
Add-Line "완료. 위 내용(또는 저장된 monitor_diag_report.txt)을 붙여넣어 주세요."
if($monCount -le 1){
  Add-Line ""
  Add-Line "[참고] 활성 모니터가 1대 이하로 감지되는 상태라면, 같은 폴더의 run_fix.bat 을"
  Add-Line "       더블클릭하면 자동 복구(장치 재검색/재활성화/확장 모드 전환)를 시도합니다."
}

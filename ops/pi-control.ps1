param([ValidateSet('GUI','Status','Authorize','Password','DnsTest','DnsEnable','DnsUpdate','DnsRestore','SSH','Camera')][string]$Action='GUI',[string]$Address)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'pi-target.ps1')
if ($Action -ne 'GUI') {
    try {
        if ($Action -in @('DnsRestore','DnsEnable','DnsUpdate')) {
            $autoState=Join-Path $env:LOCALAPPDATA 'PiControl/dns-watch.json'
            if((Test-Path $autoState) -and (Get-Content $autoState -Raw|ConvertFrom-Json).Enabled){& (Join-Path $PSScriptRoot 'dns-watch.ps1') -Action Disable}
        }
        if ($Action -eq 'DnsRestore') { & (Join-Path $PSScriptRoot 'dns-windows.ps1') -Action Restore; exit }
        $pi=Get-PiConnection -Address $Address
        $sshArgs=$pi.SshOptions
        switch ($Action) {
            'Authorize' { & (Join-Path $PSScriptRoot 'pi.ps1') -Action Authorize -Address $pi.Address }
            'Password' { & (Join-Path $PSScriptRoot 'adguard.ps1') -Action CopyPassword -Address $pi.Address }
            'DnsTest' { & (Join-Path $PSScriptRoot 'dns-windows.ps1') -Action Test -Address $pi.Address }
            'DnsEnable' {
                $mode=if(Test-Path (Join-Path $env:LOCALAPPDATA 'PiHoleTrial/wifi-dns-before.json')){'Update'}else{'Enable'}
                & (Join-Path $PSScriptRoot 'dns-windows.ps1') -Action $mode -Address $pi.Address
            }
            'DnsUpdate' { & (Join-Path $PSScriptRoot 'dns-windows.ps1') -Action Update -Address $pi.Address }
            'SSH' { & ssh @sshArgs -t rasp-tt }
            'Camera' {
                Write-Host 'Camera tunnel: open http://127.0.0.1:18767 ; keep this window open.'
                Start-Process 'http://127.0.0.1:18767'
                & ssh @sshArgs -o ExitOnForwardFailure=yes -N -L '127.0.0.1:18767:127.0.0.1:18766' rasp-tt
            }
            'Status' {
                Write-Host ('Verified Pi LAN IP: '+$pi.Address)
                & ssh @sshArgs rasp-tt 'systemctl is-active piwifi-web piwifi-observer piwifi-guard.timer adguardhome cloudflared; systemctl --user is-active edgevision-camera; /usr/bin/nmcli -g GENERAL.CONNECTION,IP4.ADDRESS device show wlan0'
            }
        }
    } catch { Write-Host $_.Exception.Message -ForegroundColor Red; exit 1 }
    exit
}
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[Windows.Forms.Application]::EnableVisualStyles()
$form=New-Object Windows.Forms.Form
$form.Text='Pi Control'; $form.Size=New-Object Drawing.Size(800,730); $form.MinimumSize=$form.Size; $form.StartPosition='CenterScreen'
$form.Font=New-Object Drawing.Font('Segoe UI',10)
$form.BackColor=[Drawing.Color]::FromArgb(246,247,249)
$panel=New-Object Windows.Forms.FlowLayoutPanel; $panel.Dock='Fill';$panel.AutoScroll=$true;$panel.Padding=New-Object Windows.Forms.Padding(24);$panel.FlowDirection='TopDown';$panel.WrapContents=$false;$form.Controls.Add($panel)
function Add-Label($text,$height=35) { $label=New-Object Windows.Forms.Label;$label.Text=$text;$label.Size=New-Object Drawing.Size(710,$height);$panel.Controls.Add($label);return $label }
$title=Add-Label 'PI CONTROL  |  Quản trị Raspberry Pi' 45;$title.Font=New-Object Drawing.Font('Segoe UI',18,[Drawing.FontStyle]::Bold)
$null=Add-Label 'Một nơi mở ứng dụng, quản lý DNS và thực hiện thao tác qua SSH.' 32
$status=Add-Label 'IP được tìm qua raspberrypi.local rồi xác minh bằng khóa SSH đã lưu.' 52
$entry=New-Object Windows.Forms.TextBox;$entry.Width=700;$panel.Controls.Add($entry)
$null=Add-Label 'IP thủ công nếu cần. Để trống để tự tìm; không quét toàn mạng.' 30
$watchStatus=Add-Label 'DNS tự động: đang đọc…' 55
$buttons=New-Object Windows.Forms.FlowLayoutPanel;$buttons.Size=New-Object Drawing.Size(710,480);$buttons.WrapContents=$true;$panel.Controls.Add($buttons)
$script:connection=$null
function Resolve-SelectedPi {
    $script:connection=Get-PiConnection -Address $entry.Text.Trim()
    $status.Text='Pi đã xác minh: '+$script:connection.Address+' | '+(Get-Date -Format 'HH:mm:ss')
    return $script:connection
}
function Launch-Task($name,$elevated=$false) {
    $params=@('-NoProfile','-NoExit','-File',('"'+$PSCommandPath+'"'),'-Action',$name)
    if($entry.Text.Trim()) {
        $parsed=$null;if(-not [Net.IPAddress]::TryParse($entry.Text.Trim(),[ref]$parsed)){throw 'IP không hợp lệ'}
        $params+=@('-Address',$parsed.ToString())
    }
    $opts=@{FilePath='powershell.exe';ArgumentList=$params}
    if($elevated){$opts.Verb='RunAs'}
    try { Start-Process @opts | Out-Null } catch { Show-Error $_.Exception.Message }
}
function Add-Button($label,$handler,$data=$null) {
    $b=New-Object Windows.Forms.Button;$b.Text=$label;$b.Size=New-Object Drawing.Size(225,58);$b.Margin=New-Object Windows.Forms.Padding(3,5,5,5);$b.FlatStyle='Flat';$b.BackColor=[Drawing.Color]::White
    $b.Tag=$data;$b.Add_Click($handler);$buttons.Controls.Add($b)
}
function Show-Error($e){[Windows.Forms.MessageBox]::Show([string]$e,'Pi Control')|Out-Null}
Add-Button 'Tìm Pi và đọc IP' {try{$null=Resolve-SelectedPi}catch{Show-Error $_.Exception.Message}}
Add-Button 'Sao chép IP DNS' {try{$c=Resolve-SelectedPi;Set-Clipboard $c.Address;$status.Text='Đã sao chép '+$c.Address}catch{Show-Error $_.Exception.Message}}
Add-Button 'Dashboard qua tên miền' {Start-Process 'https://rasp4.thinhme.tech/#apps'}
# Entries use the same catalog deployed to Pi.
$catalog=Get-Content -LiteralPath (Join-Path (Split-Path $PSScriptRoot) 'piwifi-manager/apps.json') -Raw -Encoding UTF8 | ConvertFrom-Json
foreach($item in $catalog) {
    if($item.loopback){continue}
    $handler={try{$c=Resolve-SelectedPi;$appItem=$this.Tag;Start-Process ('http://'+$c.Address+':'+$appItem.port+$appItem.path)}catch{Show-Error $_.Exception.Message}}
    Add-Button ('Mở '+$item.name) $handler $item
}
Add-Button 'Camera qua SSH tunnel' {Launch-Task 'Camera'}
Add-Button 'Kiểm tra toàn hệ thống' {Launch-Task 'Status'}
Add-Button 'Cấp quyền sudo tạm' {Launch-Task 'Authorize'}
Add-Button 'Chép mật khẩu AdGuard Home' {Launch-Task 'Password'}
Add-Button 'Kiểm tra DNS' {Launch-Task 'DnsTest'}
Add-Button 'Bật DNS AdGuard Home' {Launch-Task 'DnsEnable' $true}
Add-Button 'Cập nhật DNS theo IP Pi' {Launch-Task 'DnsUpdate' $true}
Add-Button 'Khôi phục DNS cũ' {Launch-Task 'DnsRestore' $true}
Add-Button 'Mở SSH' {Launch-Task 'SSH'}
function Launch-Watcher($action){
    try{
        $args=@('-NoProfile','-File',('"'+(Join-Path $PSScriptRoot 'dns-watch.ps1')+'"'),'-Action',$action)
        Start-Process -FilePath powershell.exe -ArgumentList $args -Verb RunAs -WindowStyle Hidden|Out-Null
    }catch{Show-Error $_.Exception.Message}
}
Add-Button 'Bật tự động DNS' {Launch-Watcher 'Install'}
Add-Button 'Tắt tự động DNS' {Launch-Watcher 'Disable'}
Add-Button 'Xem trạng thái DNS tự động' {Start-Process powershell.exe -ArgumentList @('-NoProfile','-NoExit','-File',('"'+(Join-Path $PSScriptRoot 'dns-watch.ps1')+'"'),'-Action','Status')|Out-Null}
function Refresh-WatcherStatus {
    try{
        $path=Join-Path $env:LOCALAPPDATA 'PiControl/dns-watch.json'
        if(!(Test-Path $path)){$watchStatus.Text='DNS tự động: chưa bật. Bấm Bật tự động DNS để theo dõi khi đổi mạng.';return}
        $s=Get-Content $path -Raw|ConvertFrom-Json
        $labels=@{Starting='Đang khởi động';Apply='Đã cập nhật DNS';Healthy='Đang dùng AdGuard';Fallback='Đã về DHCP, tạm ngừng lọc';Waiting='Đang tìm Pi, DNS chưa đổi';ExternalChange='Tạm dừng vì DNS được đổi bên ngoài';Paused='Đã tạm dừng';Disabled='Đã tắt';Error='Cần kiểm tra'}
        $watchStatus.Text='DNS tự động: '+$labels[$s.Status]+' | Pi: '+$s.PiAddress
        if($s.Enabled){
            $task=Get-ScheduledTask -TaskName ('PiControl-DNS-'+[Security.Principal.WindowsIdentity]::GetCurrent().User.Value) -ErrorAction SilentlyContinue
            if(!$task -or $task.State -ne 'Running'){$watchStatus.Text='DNS tự động chưa chạy. Bấm Bật tự động DNS để khởi động lại.'}
        }
    }catch{$watchStatus.Text='Chưa đọc được trạng thái DNS tự động.'}
}
$watchTimer=New-Object Windows.Forms.Timer;$watchTimer.Interval=10000;$watchTimer.Add_Tick({Refresh-WatcherStatus});$watchTimer.Start()
$form.Add_FormClosed({$watchTimer.Stop();$watchTimer.Dispose()})
Refresh-WatcherStatus
$null=Add-Label 'Tự động DNS chạy nền cả khi đóng cửa sổ. Nếu mạng chặn mDNS: lấy IP từ Dashboard, nhập ở trên rồi Tìm Pi; tác vụ nền sẽ dùng IP đã xác minh. iPhone vẫn cần sửa DNS thủ công.' 60
$null=Add-Label 'Mật khẩu sudo chỉ nhập trong terminal. Công cụ không lưu mật khẩu và không tự cấp quyền Administrator.' 45
$form.Add_Shown({try{$null=Resolve-SelectedPi}catch{$status.Text=$_.Exception.Message}})
if($env:PI_CONTROL_CHECK_UI -eq '1'){
    if($buttons.Controls.Count -ne 17){throw ('Unexpected button count '+$buttons.Controls.Count)}
    $form.Show();[Windows.Forms.Application]::DoEvents();$form.PerformLayout()
    $bitmap=New-Object Drawing.Bitmap($form.Width,$form.Height)
    $form.DrawToBitmap($bitmap,(New-Object Drawing.Rectangle(0,0,$form.Width,$form.Height)))
    $bitmap.Save((Join-Path $env:TEMP 'pi-control-preview.png'),[Drawing.Imaging.ImageFormat]::Png)
    $bitmap.Dispose();$form.Dispose();Write-Output 'Pi Control: 17 actions and form construction PASS';exit
}
$form.ShowDialog()|Out-Null

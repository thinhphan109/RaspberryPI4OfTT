# Shared connection discovery. Never disables host-key verification or scans a subnet.
function Get-PiMdnsAddress {
    # Legacy-unicast mDNS query; SSH still verifies every returned candidate.
    if(-not ('PiControl.Mdns' -as [type])){
        Add-Type -TypeDefinition @'
using System;
using System.Net;
using System.Net.Sockets;
using System.Text;
namespace PiControl {
 public static class Mdns {
  static ushort U(byte[] b,int p){return (ushort)((b[p]<<8)|b[p+1]);}
  static string Name(byte[] b,ref int p,int depth=0){
   if(depth>12)throw new Exception("DNS pointer loop");
   var s=new StringBuilder();
   while(true){int n=b[p++];if(n==0)break;
    if((n&192)==192){int q=((n&63)<<8)|b[p++];s.Append(Name(b,ref q,depth+1));break;}
    if(n>63)throw new Exception("DNS label");s.Append(Encoding.ASCII.GetString(b,p,n)).Append('.');p+=n;
   }return s.ToString();
  }
  public static string Find(){
   using(var u=new UdpClient(AddressFamily.InterNetwork)){
    u.Client.ReceiveTimeout=1200;
    byte[] q={0,0,0,0,0,1,0,0,0,0,0,0,11,114,97,115,112,98,101,114,114,121,112,105,5,108,111,99,97,108,0,0,1,128,1};
    u.Send(q,q.Length,new IPEndPoint(IPAddress.Parse("224.0.0.251"),5353));
    var until=DateTime.UtcNow.AddMilliseconds(1400);
    while(DateTime.UtcNow<until){
     try{var ep=new IPEndPoint(IPAddress.Any,0);var b=u.Receive(ref ep);if(b.Length<12||(b[2]&128)==0)continue;
      int p=12;int questions=U(b,4);int records=U(b,6)+U(b,8)+U(b,10);
      for(int i=0;i<questions;i++){Name(b,ref p);p+=4;}
      for(int i=0;i<records;i++){string name=Name(b,ref p);int type=U(b,p),size=U(b,p+8);p+=10;
       if(type==1&&size==4&&name.Equals("raspberrypi.local.",StringComparison.OrdinalIgnoreCase))return new IPAddress(new byte[]{b[p],b[p+1],b[p+2],b[p+3]}).ToString();p+=size;
      }
     }catch(SocketException){break;}catch(Exception){}
    }return null;
   }
  }
 }
}
'@
    }
    return [PiControl.Mdns]::Find()
}
function Get-PiConnection {
    param([string]$Address)
    $cache = Join-Path $env:LOCALAPPDATA 'PiControl/connection.json'
    $candidates = @()
    if ($Address) {
        $parsed = $null
        if (-not [Net.IPAddress]::TryParse($Address,[ref]$parsed) -or $parsed.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork) { throw 'Enter a valid IPv4 address.' }
        $candidates += $Address
    } else {
        $candidates += 'raspberrypi.local'
        if (Test-Path -LiteralPath $cache) {
            try { $saved = Get-Content -LiteralPath $cache -Raw | ConvertFrom-Json; $parsed = $null; if ([Net.IPAddress]::TryParse([string]$saved.Address,[ref]$parsed)) { $candidates += [string]$saved.Address } } catch { }
        }
        # Historical LAN address is only a candidate, verified against the Pi host key.
        $candidates += '192.168.0.106'
    }
    if(!$Address){try{$mdns=Get-PiMdnsAddress;if($mdns){$candidates=@($mdns)+$candidates}}catch{}}
    foreach ($hostAddress in ($candidates | Select-Object -Unique)) {
        $args = @('-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=4','-o','ConnectionAttempts=1','-o',"HostName=$hostAddress",'-o','HostKeyAlias=raspberrypi.local')
        $raw = & ssh @args rasp-tt 'hostname; /usr/bin/nmcli -g IP4.ADDRESS device show wlan0' 2>$null
        if ($LASTEXITCODE -ne 0) { continue }
        if ($raw.Count -lt 2 -or $raw[0].Trim() -ne 'raspberrypi') { continue }
        $lan = ([string]$raw[1]).Split('/')[0].Trim(); $parsed = $null
        if (-not [Net.IPAddress]::TryParse($lan,[ref]$parsed)) { continue }
        $dir = Split-Path $cache
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
        $cachedAddress=$null
        if(Test-Path -LiteralPath $cache){try{$cachedAddress=(Get-Content -LiteralPath $cache -Raw|ConvertFrom-Json).Address}catch{}}
        if($cachedAddress -ne $lan){@{Address=$lan; VerifiedAt=(Get-Date).ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath $cache -Encoding UTF8}
        return [pscustomobject]@{Address=$lan;HostAddress=$hostAddress;SshOptions=$args}
    }
    throw 'Cannot reach the verified Pi. Open rasp4.thinhme.tech, copy its LAN IP, and enter it in Pi Control. Connect to the same LAN, or use fallback hotspot 192.168.50.1.'
}

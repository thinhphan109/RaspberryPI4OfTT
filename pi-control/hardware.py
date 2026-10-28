"""Read-only GPIO discovery. No pin changes or line requests are made."""
import re
import shutil
import subprocess
import time
from pathlib import Path

BCM = [None,None,2,None,3,None,4,14,None,15,17,18,27,None,22,23,None,24,10,None,9,25,11,8,None,7,0,1,5,None,6,12,13,None,19,16,26,20,None,21]
GROUPS = {'I2C':{2,3}, 'HAT':{0,1}, 'UART':{14,15}, 'SPI':{7,8,9,10,11,16,19,20,21}, 'PWM':{12,13,18,19}, 'Clock':{4,5,6}}
FUNCTIONS = {0:'HAT ID_SD',1:'HAT ID_SC',2:'I2C SDA1',3:'I2C SCL1',4:'GPCLK / 1-Wire khi cấu hình',7:'SPI0 CE1',8:'SPI0 CE0',9:'SPI0 MISO',10:'SPI0 MOSI',11:'SPI0 SCLK',12:'PWM',13:'PWM',14:'UART TX',15:'UART RX',16:'SPI1 CE2',18:'PWM / PCM CLK',19:'PWM / SPI1 MISO',20:'SPI1 MOSI / PCM DIN',21:'SPI1 SCLK / PCM DOUT'}
PINOUT_MAP = []
for physical,bcm in enumerate(BCM,1):
    name = ('3V3' if physical in (1,17) else '5V' if physical in (2,4) else 'GND') if bcm is None else 'GPIO '+str(bcm)
    groups = [g for g,values in GROUPS.items() if bcm in values] if bcm is not None else ['Nguồn']
    PINOUT_MAP.append(dict(physical=physical,bcm=bcm,name=name,groups=groups or ['GPIO'],function=FUNCTIONS.get(bcm,'GPIO đa năng') if bcm is not None else 'Nguồn / đất — không lập trình',writable=False))

def parse_pinctrl(raw):
    rows = {}
    for line in raw.splitlines():
        m = re.match(r'\s*(\d+):\s+(\S+)\s+(pu|pd|pn)\s*\|\s*(hi|lo)',line)
        if m and 0 <= int(m[1]) <= 27:
            rows[int(m[1])] = dict(func={'ip':'INPUT','op':'OUTPUT'}.get(m[2],m[2].upper()),level=int(m[4]=='hi'),pull={'pu':'UP','pd':'DOWN','pn':'NONE'}[m[3]])
    return rows

def status():
    result=dict(timestamp=int(time.time()),supported=False,control_enabled=False,reason='GPIO chỉ đọc; điều khiển chưa được kích hoạt',pins=[])
    try:
        result['model']=Path('/proc/device-tree/model').read_text().rstrip('\0')
    except OSError:
        result['model']='Không xác định'
    tool=shutil.which('pinctrl')
    rows={}
    if tool:
        try:
            p=subprocess.run([tool,'get','0-27'],capture_output=True,text=True,timeout=2)
            rows=parse_pinctrl(p.stdout) if p.returncode==0 else {}
            result['supported']=len(rows)==28
            if not result['supported']:result['reason']='Chưa đọc đủ GPIO từ pinctrl'
        except (OSError,subprocess.TimeoutExpired):result['reason']='Không đọc được GPIO trong thời hạn'
    else:result['reason']='Không có pinctrl; sơ đồ tra cứu vẫn sử dụng được'
    result['pins']=[dict(pin,**rows.get(pin['bcm'],dict(func=None,level=None,pull=None))) for pin in PINOUT_MAP]
    return result

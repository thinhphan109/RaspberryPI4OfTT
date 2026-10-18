from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from pathlib import Path

out=Path('G:/RaspberryPI4OfTT/docs')
out.mkdir(exist_ok=True)
d=Document()
s=d.sections[0]
s.page_width=Inches(8.27); s.page_height=Inches(11.69)
s.top_margin=s.bottom_margin=Inches(.7)
s.left_margin=s.right_margin=Inches(.8)
for name in ['Normal','Title','Heading 1','Heading 2','List Bullet','List Number']:
    st=d.styles[name]; st.font.name='Calibri'; st.font.color.rgb=RGBColor(0,0,0)
    st.font.size=Pt(11 if name not in ['Title','Heading 1','Heading 2'] else {'Title':24,'Heading 1':16,'Heading 2':12}[name])
    st.paragraph_format.space_after=Pt(7)
d.styles['Normal'].paragraph_format.line_spacing=1.12
for st in [d.styles['Title'], d.styles['Normal']]:
    pr=st.element.get_or_add_pPr()
    for border in list(pr.findall(qn('w:pBdr'))): pr.remove(border)
    borders=OxmlElement('w:pBdr')
    for edge in ['top','left','bottom','right','between']:
        node=OxmlElement('w:'+edge); node.set(qn('w:val'),'nil'); borders.append(node)
    pr.append(borders)
def p(t,style=None): return d.add_paragraph(t,style)
def h(t): d.add_heading(t,1)
def bullet(t): p(t,'List Bullet')
def code(t):
    para=p(t)
    para.paragraph_format.space_before=Pt(5)
    for r in para.runs: r.font.name='Consolas'; r.font.size=Pt(9)
def link(label,url):
    para=d.add_paragraph()
    rel=para.part.relate_to(url,'http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink',is_external=True)
    el=OxmlElement('w:hyperlink'); el.set(qn('r:id'),rel)
    r=OxmlElement('w:r'); pr=OxmlElement('w:rPr'); c=OxmlElement('w:color'); c.set(qn('w:val'),'174A70'); pr.append(c); r.append(pr)
    t=OxmlElement('w:t'); t.text=label; r.append(t); el.append(r); para._p.append(el)

d.add_heading('Hướng dẫn sử dụng Pi hole',0)
p('Cơ chế hoạt động và cách dùng trên Windows và iPhone')
p('Pi-hole là bộ lọc tên miền. Thiết bị nào dùng Pi-hole làm DNS thì các truy vấn DNS của thiết bị đó được kiểm tra để chặn tên miền quảng cáo và theo dõi. Với cấu hình Wi-Fi đã thử, Windows dùng Pi-hole; các thiết bị chưa đổi DNS tiếp tục hoạt động như trước.')
h('1 Cơ chế hoạt động')
p('Khi nhập tên website, chẳng hạn example.com, máy cần biết địa chỉ IP của website đó. DNS giống một danh bạ, giúp đổi tên miền thành địa chỉ IP. Trước đây Windows hỏi DNS do router cung cấp; sau khi cấu hình, Windows hỏi Raspberry Pi.')
code('Windows hoặc iPhone\n        | Hỏi địa chỉ của một tên miền\n        v\nPi-hole trên Raspberry Pi\n  Có trong danh sách chặn  -> Trả kết quả chặn\n  Không bị chặn           -> Hỏi DNS bên ngoài và trả IP')
p('Sau khi có địa chỉ IP, thiết bị tải nội dung trực tiếp qua router. Video, hình ảnh và file tải xuống không phải đi xuyên qua Raspberry Pi trong mô hình DNS này.')
bullet('Tên miền trang báo được cho phép: bài báo tải bình thường.')
bullet('Tên miền quảng cáo nằm trong danh sách chặn: phần quảng cáo không tải được.')
bullet('Nếu quảng cáo và nội dung dùng chung tên miền, Pi-hole khó chặn riêng quảng cáo. Vì vậy không thể trông đợi chặn đáng tin cậy quảng cáo YouTube.')
h('2 Cấu hình qua Wi Fi đã thử')
table=d.add_table(rows=1, cols=2); table.style='Light Shading Accent 1'
for c,t in zip(table.rows[0].cells,['Thành phần','Vai trò']): c.text=t
for a,b in [('Router','Cung cấp Wi-Fi và kết nối Internet'),('Raspberry Pi 192.168.0.106','Chạy Pi-hole cùng các dự án khác'),('Máy Windows','Dùng DNS 192.168.0.106 để được lọc'),('Thiết bị chưa đổi DNS','Tiếp tục hoạt động như trước')]:
    cells=table.add_row().cells; cells[0].text=a; cells[1].text=b
p('Không cần truy cập trang quản trị router và không cần kết nối vào hotspot của Pi. Chỉ thay đổi DNS trên những thiết bị muốn dùng bộ lọc.')

d.add_page_break()
h('3 Sử dụng hằng ngày trên Windows')
p('Mở trình duyệt và ứng dụng như bình thường. Pi-hole chạy nền trên Raspberry Pi; không cần giữ trang quản trị mở.')
link('Mở Pi-hole Admin trong mạng Wi-Fi','http://192.168.0.106:18853/admin/')
p('Trang quản trị dùng để xem thống kê, quản lý danh sách chặn, thêm tên miền được phép và tạm dừng chặn khi cần. Cấu hình hiện tại tắt ghi lịch sử truy vấn lâu dài xuống thẻ nhớ; lịch sử trong RAM không tồn tại qua lần khởi động lại dịch vụ hoặc Pi.')
p('Để lấy mật khẩu quản trị vào clipboard, mở PowerShell tại G:\\RaspberryPI4OfTT rồi chạy:')
code('.\\ops\\pihole.ps1 -Action CopyPassword')
p('Sau đó dán mật khẩu vào trang đăng nhập. Không cần gõ hoặc gửi mật khẩu vào cuộc trò chuyện.')
d.add_heading('Khi website hoạt động lỗi',2)
p('Thử tạm dừng chặn trong thời gian ngắn, tải lại website rồi bật lại. Nếu xác định được tên miền cần thiết bị chặn nhầm, thêm tên miền đó vào danh sách cho phép. Một số nội dung đã lưu trong bộ nhớ đệm có thể chưa thay đổi ngay.')
d.add_heading('Khi Pi tắt hoặc không còn truy cập được',2)
p('Nếu Pi tắt, mất Wi-Fi hoặc đổi IP, Windows có thể không phân giải được tên miền. Mở PowerShell bằng Run as administrator và chạy lệnh khôi phục DNS cũ:')
code("& 'G:\\RaspberryPI4OfTT\\ops\\pihole-windows.ps1' -Action Restore")
p('Nếu muốn bật lại cấu hình DNS Wi-Fi đã thử, chạy trong PowerShell Administrator:')
code("& 'G:\\RaspberryPI4OfTT\\ops\\pihole-windows.ps1' -Action Enable")
d.add_heading('Phân biệt DNS và địa chỉ trang quản trị',2)
bullet('DNS: chỉ nhập địa chỉ IP 192.168.0.106. Không nhập http:// hoặc số cổng.')
bullet('Trang quản trị: mở http://192.168.0.106:18853/admin/ trong trình duyệt.')
bullet('Không thêm DNS công cộng như 8.8.8.8 hoặc 1.1.1.1 làm DNS phụ trong lúc thử, vì thiết bị có thể dùng chúng và bỏ qua bộ lọc.')
bullet('VPN hoặc Secure DNS của trình duyệt có thể sử dụng DNS riêng và bỏ qua Pi-hole.')
h('Ghi chú về địa chỉ Tailscale mới')
p('Pi đã có thêm địa chỉ Tailscale 100.66.23.14 và Pi-hole đã được cấu hình nhận DNS qua địa chỉ này. Đó là IP của mạng riêng Tailscale, không phải IP public. Hai thiết bị cần kết nối Tailscale và được cấp quyền để liên lạc qua địa chỉ đó.')
p('Việc đăng nhập Windows và đặt DNS chung cho Tailscale chưa được xác nhận hoàn tất. Các bước DNS Wi-Fi trong tài liệu vẫn dùng 192.168.0.106; không tự thay bằng IP Tailscale khi thiết bị chưa kết nối được Tailscale.')

d.add_page_break()
h('4 Cách dùng trên iPhone và iPad')
p('Hướng dẫn này dùng DNS trực tiếp qua Wi-Fi. iPhone hoặc iPad phải cùng mạng Wi-Fi với Pi và liên lạc được với địa chỉ 192.168.0.106.')
for t in ['Mở Cài đặt → Wi-Fi.','Nhấn biểu tượng thông tin ⓘ cạnh mạng đang kết nối.','Chọn Định cấu hình DNS hoặc Configure DNS.','Chọn Thủ công hoặc Manual.','Xóa các máy chủ DNS cũ trong danh sách.','Chọn Thêm máy chủ hoặc Add Server, nhập 192.168.0.106.','Nhấn Lưu hoặc Save.']: p(t,'List Number')
p('Chỉ nhập IP. Không nhập http:// hay cổng 18853 vì đó là cổng dành cho trang quản trị. Không thêm DNS công cộng làm máy chủ phụ trong lúc thử.')
d.add_heading('Nếu dùng iCloud Private Relay',2)
p('Private Relay có thể khiến truy vấn DNS đi theo đường khác. Khi thử Pi-hole, có thể tắt Giới hạn theo dõi địa chỉ IP hoặc Limit IP Address Tracking cho mạng Wi-Fi đó. Thao tác này cũng tắt Private Relay trên mạng ấy. VPN hoặc cấu hình DNS riêng cũng có thể ảnh hưởng.')
d.add_heading('Phạm vi và cách khôi phục',2)
bullet('DNS thủ công này chỉ áp dụng cho mạng Wi-Fi vừa chỉnh, không áp dụng cho 4G hoặc 5G.')
bullet('Để trở lại bình thường: vào Định cấu hình DNS → Tự động → Lưu.')
bullet('IP Wi-Fi của Pi có thể thay đổi khi chuyển mạng. Khi đó phải cập nhật cấu hình hoặc hoàn tất cách truy cập qua Tailscale.')
bullet('iPhone trong LAN vẫn dùng DNS được, nhưng trang quản trị có thể từ chối vì IP iPhone chưa nằm trong danh sách truy cập LAN được phép. Cấu hình mới cho phép truy cập quản trị qua Tailscale khi đã kết nối hợp lệ.')
p('Muốn dùng Pi-hole từ mạng Wi-Fi khác hoặc 4G/5G qua Tailscale, cần hoàn tất cấu hình DNS Tailscale và bật Tailscale trên iPhone. Không chỉ đổi DNS Wi-Fi rồi mong cấu hình có hiệu lực trên mạng di động.')
h('Tài liệu tham khảo')
link('Pi-hole — cấu hình thiết bị sau khi cài đặt','https://docs.pi-hole.net/main/post-install/')
link('Apple — quản lý cài đặt Wi-Fi trên iPhone','https://support.apple.com/en-am/guide/iphone/iphw5gjwl8k2/27/ios/27')
link('Apple — quản lý iCloud Private Relay','https://support.apple.com/en-ie/102022')
p('Thông tin cấu hình được tổng hợp ngày 15/10/2026. Không bao gồm mật khẩu hoặc khóa truy cập.')
d.core_properties.title='Hướng dẫn sử dụng Pi hole'
d.core_properties.author=''
d.save(out/'Huong-dan-Pi-hole.docx')
print(out/'Huong-dan-Pi-hole.docx')

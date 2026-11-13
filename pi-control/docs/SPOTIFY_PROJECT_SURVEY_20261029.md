# Khảo sát Spotify cho Pi Control — 29/10/2026

Trạng thái sau khảo sát: xem [Media r8](MEDIA_R8.md) để biết bản điều khiển app đã deploy và kết quả thử SpotiAds riêng. Các mục “chưa triển khai” bên dưới mô tả thời điểm khảo sát ban đầu.

Phạm vi: Raspberry Pi 4, Debian ARM64, Spotify Free, Chromium Web Player và
Dashboard hiện có. Đã đọc README, mã nguồn chọn lọc, manifest extension, metadata
commit/release và tài liệu chính thức. Chưa cài, benchmark hoặc thay đổi Pi.
Khả năng chạy và hiệu quả quảng cáo dưới đây cần được phân biệt rõ.

## Kết luận cho hệ thống hiện tại

Ưu tiên tiếp tục Web Player. SpotX-Bash, Spicetify/Adblockify và spotify-adblock
Rust đều cần Spotify Desktop thích hợp; chúng không phải module có thể gắn vào
Dashboard hiện tại. Kho APT Spotify vẫn chỉ công bố `amd64 i386`, không có
Linux ARM64. ARM64 của macOS không tương đương Linux ARM64.
[Metadata chính thức Spotify](https://repository.spotify.com/dists/stable/Release).

Ba hướng đáng thử là: kiểm tra bộ lọc trình duyệt đang có; tắt tiếng quảng cáo
ở cấp tab khi cần; cầu nối trạng thái/điều khiển giữa browser và Media agent.
Spotube là phương án thử độc lập nếu chấp nhận nguồn âm thanh khác Spotify.
Player native dùng librespot dành cho phương án tài khoản Premium sau này.

## Các dự án đã đối chiếu

| Dự án | Cơ chế / điều kiện | Đánh giá với Pi hiện tại |
|---|---|---|
| [SpotX-Bash](https://github.com/SpotX-Official/SpotX-Bash) | Patch Spotify Desktop. `linux_prepare()` đặt `archVar="x86_64"`; sửa binary và `xpui.spa`. | Không cài trực tiếp cho Web Player ARM64. Lớp dịch CPU cần thử riêng, chưa có bằng chứng giúp tăng tốc Pi. |
| [Spicetify + Adblockify](https://github.com/rxri/spicetify-extensions/tree/main/adblock) | Spicetify chỉnh client chính thức; Adblockify gọi Platform/AdManagers/Cosmos của môi trường Spicetify. | CLI chạy được không tạo ra client Spotify ARM64. Không copy extension vào Dashboard/Chromium rồi mong tự chạy. |
| [spotify-adblock — Rust](https://github.com/abba23/spotify-adblock) | `LD_PRELOAD` thư viện native, hook `cef_urlrequest_create` trong client Linux. Không hỗ trợ Snap; Flatpak phụ thuộc thư viện. | Cần binary Spotify và ABI/kiến trúc phù hợp. Không phải adblock chung cho mọi ứng dụng viết bằng Chromium. |
| [spotify-web-ads-remover / SpotiAds](https://github.com/tomer8007/spotify-web-ads-remover) | Manifest V3, dành cho Web Player; chặn bằng can thiệp state/request, khác với chỉ mute. | Sát nền tảng nhất trong nhóm thử chặn thật. Cần thử profile riêng; đọc/chỉnh state nội bộ, có xử lý token/header trong mã nguồn. |
| [Blockify](https://github.com/dhanur2/spotify-ad-blocker-extension-blockify) | Extension MV3, nhiều website; source public là snapshot để review. | Không ưu tiên: quyền rộng, có nội dung ngoài Spotify; repo không bảo đảm khớp byte với bản trên store. Giấy phép source-available cần kiểm tra trước khi tái sử dụng. |
| [SpotiShush](https://github.com/guihkx/spotishush) | MV3; phát hiện quảng cáo, mute/unmute tab bằng API extension. | Cơ chế đáng áp dụng. Chỉ làm im quảng cáo, vẫn phải chờ. Bộ nhận diện DOM cần kiểm tra theo Spotify hiện tại. |
| [WebNowPlaying](https://github.com/keifufu/WebNowPlaying) | MV3 + adapter WebSocket loopback; thông tin bài, play/pause, next, seek, volume tuỳ player. | Hữu ích tham khảo cho cầu nối Dashboard. Còn phụ thuộc nội bộ React/PlayerAPI; không phải API Spotify ổn định. |
| [Spotube](https://github.com/team-spotube/spotube) | Metadata và audio-source theo plugin. Stable v5.1.2 có gói Linux aarch64. | Thử riêng được về kiến trúc. Khi metadata Spotify được ghép với audio YouTube/nguồn khác, đó là đổi nguồn phát, không phải bỏ quảng cáo của luồng Spotify. |
| [Spotifast](https://github.com/crmne/spotifast) | Client Rust native, có Linux ARM64; bản được kiểm tra v0.14.2. | README yêu cầu Premium để phát. Free tìm/duyệt được không có nghĩa Free phát được. |
| [librespot](https://github.com/librespot-org/librespot) / [spotifyd](https://github.com/Spotifyd/spotifyd) | Audio backend/daemon Spotify Connect. | Có ích khi cần headless nhẹ, nhưng upstream yêu cầu Premium. Không thay Web Player Free hiện tại. |
| [Music Assistant](https://www.music-assistant.io/music-providers/spotify/) | Thư viện đa nguồn, hàng đợi và điều khiển player. | Spotify provider yêu cầu Premium. Có thể học cách tách provider/queue, chưa đáng cài cả stack chỉ cho Spotify Free. |
| [SpotifyPlus](https://github.com/thlucas1/homeassistantcomponent_spotifyplus) | Home Assistant integration, dịch vụ Web API; có nhánh hỗ trợ Free bằng elevated credentials. | Không phải engine phát Free độc lập. Tăng phụ thuộc HA/xác thực; không phù hợp mục tiêu hiện tại là không trích cookie/token. |
| [spotify-no-ads](https://github.com/geranton93/spotify-no-ads) | Extension Spicetify mới, tuyên bố xử lý ad delivery và có công cụ xác minh. | Chỉ là ứng viên Desktop; vẫn gặp điểm chặn client trên Pi. Chưa xác minh tuyên bố hiệu quả. |
| [SpotOn](https://github.com/SenpaiHunters/SpotOn) | Chỉnh UX Web Player. Repo thông báo deprecated và archived từ 05/01/2026. | Không chọn làm nền tảng mới. |

## Những điểm đọc mã nguồn có ích cho Dashboard

### 1. Bộ lọc hiện tại cần được xác minh trước khi thêm extension

Source bootstrap hiện đặt uBO Lite `defaultFiltering: optimal`. Không nên kết
luận máy đang chạy Basic chỉ dựa vào tài liệu cũ hoặc cờ `password-store=basic`:
cờ đó thuộc kho mật khẩu của browser, không phải chế độ chặn quảng cáo.

Cần xem mode và quyền host có hiệu lực trên Pi. Theo tài liệu uBOL, Basic
không có cosmetic filtering/scriptlet; Optimal/Complete phụ thuộc quyền đọc và
thay đổi dữ liệu trên website. Policy cấu hình không tự chứng minh các quyền
đã được cấp. Đổi mode cũng chưa chứng minh chặn được quảng cáo Spotify.
[Troubleshooting](https://github.com/uBlockOrigin/uBOL-home/wiki/Troubleshooting),
[managed settings](https://github.com/uBlockOrigin/uBOL-home/wiki/Managed-settings).

Không xếp chồng uBOL và một blocker khác rồi đánh giá chung. Tác giả uBOL khuyên
thử cô lập khi có xung đột. SpotiShush là muter, nhưng vẫn cần một nơi sở hữu
trạng thái mute để tránh tự bật lại âm thanh của thành phần khác.
[FAQ](https://github.com/uBlockOrigin/uBOL-home/wiki/Frequently-asked-questions-%28FAQ%29).

### 2. Mute tab có thể giải quyết giới hạn của mute thẻ audio

`spotify_player.ad_filter()` hiện tìm `audio`/`video` rồi mute phần tử đó. Nếu
không có phần tử phù hợp, hàm trả false. Các phép thử r7 từng đọc được trạng
thái phát và PipeWire đang chạy dù không có khả năng chỉnh volume DOM; không
được suy ra checkbox hiện tại luôn tắt tiếng quảng cáo thành công.

SpotiShush gọi `tabs.update(..., {muted: ...})` và có bảo vệ tab do người dùng
tự mute. Vì vậy có thể học cơ chế này mà không cần lấy token Spotify. Tuy
nhiên detector của nó so `data-testadtype` với `ad-type-none`: nếu thuộc tính
không còn tồn tại, cách so này có thể nhận nhầm. Đây là suy luận từ code,
chưa phải lỗi đã tái hiện trên Pi.
[Background source](https://github.com/guihkx/spotishush/blob/64963db9da14d1e980e0f26c045340bf7c36b46a/src/background.js),
[detector](https://github.com/guihkx/spotishush/blob/64963db9da14d1e980e0f26c045340bf7c36b46a/src/spotishush.js).

Nếu triển khai, chỉ mute với tín hiệu quảng cáo rõ; thuộc tính vắng là không
xác định. Khôi phục đúng trạng thái do mình thay đổi, giữ manual mute, sleep
và Bluetooth hold. Mute quảng cáo không loại bỏ thời gian chờ quảng cáo.

### 3. Bridge có thể cải thiện điều khiển, chưa giải quyết tốc độ tìm kiếm

WebNowPlaying có giao thức player added/updated/removed và kết quả lệnh qua
WebSocket `127.0.0.1`. Spotify adapter dùng MediaSession kết hợp PlayerAPI nội
bộ. Đây là mẫu tham khảo để cập nhật Dashboard theo sự kiện, giảm việc phải
hỏi browser để biết thay đổi bài hoặc pause.
[Socket](https://github.com/keifufu/WebNowPlaying/blob/764878b6c2be76ebeb9b24a06d7c5da1845b6472/src/extension/sw/socket.ts),
[Spotify adapter](https://github.com/keifufu/WebNowPlaying/blob/764878b6c2be76ebeb9b24a06d7c5da1845b6472/src/extension/content/injected/sites/Spotify.ts).

Không cài nguyên extension rồi coi như tích hợp xong: adapter Spotify phụ
thuộc cấu trúc React/private registry, manifest chạy trên nhiều website và
HEAD được kiểm tra vẫn từ tháng 07/2025. Cần adapter riêng, whitelist dữ liệu,
giới hạn profile Media/website và giữ CDP hiện tại làm fallback. Bridge chỉ
giúp đường điều khiển/trạng thái; tìm nhạc vẫn là bài toán riêng.

### 4. Phải phân biệt các đường “Spotify Free”

SpotiAds thực sự chỉnh state quảng cáo, không chỉ mute. Mã nguồn giữ các biến
accessToken/clientToken/authorizationHeader để xử lý request; vì vậy khác
thiết kế hiện tại không đọc token. Chưa audit toàn bộ hoặc chứng minh an toàn
của bản store. Nếu chọn thử thì tách profile và đo riêng tính đúng của bài,
liên tục của playback và khả năng phục hồi khi extension lỗi.
[README](https://github.com/tomer8007/spotify-web-ads-remover),
[state handler](https://github.com/tomer8007/spotify-web-ads-remover/blob/fd6b71475ddb3f89607902c174652fd14d226055/injected/ads_removal.js).

Spotube v5.1.2 có artefact ARM64 và audio-source plugins; dependency có MPRIS,
gợi ý đường điều khiển native từ Dashboard. Cần kiểm tra MPRIS thực tế, khả
năng tìm/đăng nhập plugin và chọn đúng bản thu. Chưa kết luận nhẹ hoặc nhanh
hơn Chromium khi chưa đo trên Pi. `master` đang thay đổi kiến trúc; không trộn
hướng dẫn build master với release v5.1.2.
[Release](https://github.com/team-spotube/spotube/releases/tag/v5.1.2),
[dependency stable](https://github.com/team-spotube/spotube/blob/v5.1.2/pubspec.yaml).

Spotify SDK chính thức để phát trong web app yêu cầu Premium. Web API ở
development mode hiện yêu cầu chủ ứng dụng có Premium. Vì thế không đề xuất
“clone Spotify đầy đủ bằng API” như một nâng cấp chắc chắn dùng được với tài
khoản Free và không cần thêm điều kiện.
[Playback SDK](https://developer.spotify.com/documentation/web-playback-sdk/howtos/web-app-player),
[Web API quota](https://developer.spotify.com/documentation/web-api/concepts/quota-modes).

## Chốt hướng theo yêu cầu tiếp theo — chưa triển khai

Ưu tiên thử **SpotiAds với Spotify Web Player hiện tại**, trên profile thử
riêng, để kiểm chứng loại bỏ quảng cáo thật trước khi đổi backend. Không coi
tắt tiếng trong lúc chờ là đạt mục tiêu chặn. Chỉ ghép vào luồng chính khi bài
tiếp theo phát đúng, queue không kẹt và mức CPU/RAM trên Pi chấp nhận được.
Cấu hình uBOL được kiểm tra và thử riêng để phân biệt nguồn gây lỗi.

Đường điều khiển ứng dụng native là khả thi: mở rộng Media agent hiện có với
adapter MPRIS/D-Bus cho app hỗ trợ giao thức đó; app có API riêng thì dùng API.
Play/pause, next/previous, seek, volume và metadata đều có trong đặc tả MPRIS,
nhưng phải theo capability mà từng app công bố. Đây là đề xuất kiến trúc,
chưa phải adapter đã cài.
[MPRIS Player](https://specifications.freedesktop.org/mpris/latest/Player_Interface.html).

Phát hiện bổ sung quan trọng: **Spotify Soloist** là client headless chính
thức, hỗ trợ Pi ARMv7/AArch64, PipeWire và API WebSocket/`soloist ctl` cho lệnh,
queue và sự kiện. README yêu cầu Premium ở bước thiết lập; sau khi chạy, Free
và Premium có thể kết nối. Vì vậy phải phân biệt thiếu Spotify Desktop GUI
ARM64 với sự tồn tại của client headless này. Soloist không phải giải pháp
adblock, còn yêu cầu API key cá nhân và cập nhật build hết hạn sau 90 ngày.
[Soloist](https://github.com/spotify/soloist),
[tài liệu chính thức](https://developer.spotify.com/documentation/soloist).

Box64 có cấu hình cho Spotify x86_64, nên Desktop qua lớp dịch CPU là một
đường thử có cơ sở, không phải bất khả thi tuyệt đối. Tuy nhiên cấu hình còn
có tuỳ chọn bỏ sandbox và chưa có benchmark Pi 4 cho hệ thống này; chưa chọn
làm backend vận hành chính. Không thay nguồn âm thanh sang YouTube chỉ để
gọi đó là Spotify đã chặn quảng cáo.
[Box64 config](https://github.com/ptitSeb/box64/blob/main/system/box64.box64rc).

## Các nhánh phát triển đã khảo sát — chưa triển khai

1. **P0: đối chiếu hiện trạng.** Kiểm tra uBOL version/mode/quyền host thực tế,
   số lần detector quảng cáo hoạt động và hàm mute có thành công. Hiển thị
   riêng “đang lọc”, “đã nhận diện”, “đang tắt tiếng” và “chưa xác định”.
2. **P1: tab-level ad mute trong profile Media.** Lấy ý tưởng SpotiShush, không
   phụ thuộc audio DOM. Một nơi quản lý mute; không làm mất manual mute hoặc
   Bluetooth/sleep hold. Không ép seek/rate hay tự reload bài khi nhận diện mơ hồ.
3. **P2: bridge trạng thái/điều khiển.** Extension nhỏ cho Spotify/YouTube và
   Media agent hiện tại, giao tiếp loopback, không public cổng qua Tunnel.
   Whitelist metadata và lệnh; không gửi cookie/token/form đăng nhập. Giữ giao
   diện mobile/desktop cùng API và receipt xác nhận theo trạng thái thực tế.
4. **P3: thử một ứng viên chặn thật.** So sánh cấu hình uBOL đã xác minh với
   SpotiAds ở profile thử riêng; không bật hai blocker đồng thời. Dừng thử khi
   phát sai bài, kẹt queue hoặc không phục hồi được sau quảng cáo.
5. **Nhánh thay thế:** Spotube ARM64 nếu chấp nhận nguồn nhạc khác; Spotifyd/
   Spotifast nếu chuyển sang Premium. Không thêm cả HA/Music Assistant chỉ để
   thay một màn hình Spotify khi điều kiện tài khoản vẫn chưa đáp ứng.

Tiêu chí thử: xác nhận đúng bài bằng tiến độ và luồng audio, có quảng cáo thật
mới đánh giá blocker, mute/unmute không nhầm, next/sleep/Bluetooth không hồi
âm thanh ngoài ý muốn. Đo riêng nhận lệnh HTTP, thời điểm bắt đầu phát và mức
CPU/RAM của toàn bộ browser/agent. Chưa có số đo mới hoặc bằng chứng chặn 100%.

## Hồ sơ nguồn

Metadata công khai và các SHA đã kiểm tra được lưu local tại
`ops/reports/spotify-research-20261029/repos.json`. Không tải hoặc chạy installer,
không cài extension, không đọc dữ liệu tài khoản trên Pi. Các quyết định ở đây
là đề xuất triển khai tiếp, không phải trạng thái đã cài.

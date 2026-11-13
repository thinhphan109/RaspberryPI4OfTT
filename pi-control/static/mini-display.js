(() => {
    'use strict';
    const $ = id => document.getElementById(id);
    const view = $('mini-display');
    if (!view) return;
    const screen = $('mini-screen');
    const ctx = screen.getContext('2d');
    const clip = $('mini-clip');
    const frame = new Image(320, 240);
    frame.alt = 'Trang Tổng quan do Pi dựng';
    frame.hidden = true;
    screen.after(frame);
    let service = null, serviceRequest, serviceAt = 0, changingSource = false, message = '';
    const pages = {
        summary: 'Tổng quan', network: 'IP & Wi-Fi', rescue: 'Cứu hộ mạng', health: 'Sức khỏe Pi',
        music: 'Đang phát nhạc', audio: 'Âm thanh & hẹn giờ', clock: 'Đồng hồ & ảnh động',
        boot: 'Khởi động & tắt máy', bambu: 'Bambu A1'
    };
    const ids = Object.keys(pages);
    const key = 'pi-control.mini-display.v1';
    const defaults = () => ({version: 2, order: [...ids], enabled: ids.filter(id => id !== 'bambu'),
        defaultPage: 'summary', auto: true, motion: true});
    function load() {
        const base = defaults();
        try {
            const saved = JSON.parse(localStorage.getItem(key));
            if (![1, 2].includes(saved?.version) || !Array.isArray(saved.order) || !Array.isArray(saved.enabled)) return base;
            const legacy = saved.version === 1;
            const order = [...new Set([...(legacy ? ['summary'] : []), ...saved.order.filter(id => ids.includes(id)), ...ids])];
            const enabled = order.filter(id => id !== 'bambu' && (saved.enabled.includes(id) || (legacy && id === 'summary')));
            if (!enabled.length) return base;
            const defaultPage = legacy && saved.defaultPage === 'network' ? 'summary' : saved.defaultPage;
            return {...base, order, enabled, defaultPage: enabled.includes(defaultPage) ? defaultPage : enabled[0],
                auto: saved.auto !== false, motion: saved.motion !== false};
        } catch { return base; }
    }
    let config = load(), selected = null, timer, animationTimer, pending;
    let metrics = JSON.parse($('initial-metrics').textContent);
    let network = JSON.parse($('initial-network').textContent);
    let media = null, audio = null, fetchedAt = 0, dataMissing = false;
    const accessible = () => view.classList.contains('active') && !document.hidden;
    const mode = () => $('mini-mode').value;
    const mono = 'JetBrains Mono, monospace';
    const font = 'Noto Sans, sans-serif';
    const reduced = matchMedia('(prefers-reduced-motion: reduce)');
    const clock = new Intl.DateTimeFormat('vi-VN', {hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Ho_Chi_Minh'});
    const calendar = new Intl.DateTimeFormat('vi-VN', {weekday: 'long', day: '2-digit', month: '2-digit',
        year: 'numeric', timeZone: 'Asia/Ho_Chi_Minh'});
    const shortDate = new Intl.DateTimeFormat('vi-VN', {day: '2-digit', month: '2-digit',
        year: 'numeric', timeZone: 'Asia/Ho_Chi_Minh'});
    const number = (value, suffix = '') => Number.isFinite(value) ? Math.round(value) + suffix : '—';
    function uptimeLabel(seconds) {
        if (!Number.isFinite(seconds) || seconds < 0) return '—';
        const hours = Math.floor(seconds / 3600);
        return hours >= 24 ? Math.floor(hours / 24) + ' ngày ' + hours % 24 + ' giờ' :
            hours + ' giờ ' + Math.floor(seconds / 60) % 60 + ' phút';
    }
    const remaining = value => Number.isFinite(value) ? Math.floor(value / 60) + ':' + String(Math.floor(value % 60)).padStart(2, '0') : '—';
    const accent = '#a5e1c7', muted = '#b5c4d1', white = '#f5f7fa', amber = '#ffcf88';
    const rescueStates = {
        'connection-pending': 'Đang chờ Wi-Fi', 'radio-disabled': 'Wi-Fi đang tắt',
        'device-busy-or-unavailable': 'Thiết bị mạng chưa sẵn sàng', error: 'Bật hotspot thất bại'
    };
    const assets = new URL('.', document.currentScript.src);
    const assetVersion = new URL(document.currentScript.src).search;
    const sprites = new Map();
    function image(name) {
        if (!sprites.has(name)) {
            const asset = new Image();
            asset.onload = () => { if (accessible()) draw(); };
            const url = new URL(name, assets);
            url.search = assetVersion;
            sprites.set(name, asset);
            asset.src = url.href;
        }
        return sprites.get(name);
    }
    function cat(id, x, y, size, breathe = false) {
        const sprite = image('mini-cat/' + id + '.png');
        if (!sprite.complete || !sprite.naturalWidth) return;
        const offset = breathe && config.motion && !reduced.matches ? Math.sin(Date.now() / 500) * 2 : 0;
        ctx.imageSmoothingEnabled = true;
        ctx.drawImage(sprite, x, y + offset, size, size);
    }
    function text(value, x, y, size, color = white, family = font, maxWidth = 204) {
        ctx.fillStyle = color;
        ctx.font = '600 ' + size + 'px ' + family;
        let line = String(value ?? '—');
        if (ctx.measureText(line).width > maxWidth) {
            const letters = Array.from(line);
            do { letters.pop(); } while (letters.length && ctx.measureText(letters.join('') + '…').width > maxWidth);
            line = letters.join('') + '…';
        }
        ctx.fillText(line, x, y);
    }
    function bar(value, x, y, width, color = accent) {
        ctx.fillStyle = '#2a3742';
        ctx.fillRect(x, y, width, 4);
        if (Number.isFinite(value)) {
            ctx.fillStyle = color;
            ctx.fillRect(x, y, width * Math.max(0, Math.min(value, 1)), 4);
        }
    }
    const background = document.createElement('canvas');
    background.width = screen.width;
    background.height = screen.height;
    const paint = background.getContext('2d');
    paint.fillStyle = '#141119';
    paint.fillRect(0, 0, background.width, background.height);
    paint.globalCompositeOperation = 'lighter';
    for (const [x, y, radius, color] of [
        [20, 20, 216, '#340d14'], [318, 111, 182, '#0d1930'], [141, 244, 166, '#1b1606']
    ]) {
        const light = paint.createRadialGradient(x, y, 0, x, y, radius);
        light.addColorStop(0, color);
        light.addColorStop(1, 'transparent');
        paint.fillStyle = light;
        paint.fillRect(0, 0, background.width, background.height);
    }
    paint.fillStyle = '#030303';
    for (let x = 0; x < background.width; x += 24) paint.fillRect(x, 0, 1, background.height);
    for (let y = 0; y < background.height; y += 24) paint.fillRect(0, y, background.width, 1);

    function backdrop() {
        ctx.drawImage(background, 0, 0);
    }
    function divider(y) {
        ctx.fillStyle = '#35444f';
        ctx.fillRect(16, y, 288, 1);
    }
    function header(title, color = accent) {
        const now = new Date();
        text(clock.format(now), 16, 25, 14, white, mono, 50);
        text(title, 71, 25, 12, color, font, 145);
        text(shortDate.format(now), 225, 25, 12, muted, mono, 79);
        divider(35);
    }
    function side(id, breathe = false) {
        cat(id, 211, 50, 107, breathe);
    }
    function details(items) {
        divider(197);
        items.forEach(([title, value], index) => {
            const width = 288 / items.length;
            const x = 16 + width * index;
            text(title, x, 213, 11, muted, font, width - 8);
            text(value, x, 230, 13, white, mono, width - 8);
        });
    }
    function headline(value, x, y, size, width, color = white) {
        const words = String(value).split(/\s+/);
        let first = words.shift();
        ctx.font = '600 ' + size + 'px ' + font;
        while (words.length && ctx.measureText(first + ' ' + words[0]).width <= width) first += ' ' + words.shift();
        text(first, x, y, size, color, font, width);
        if (words.length) text(words.join(' '), x, y + size + 5, size, color, font, width);
    }
    function rate(value) {
        if (!Number.isFinite(value)) return '—';
        return value >= 1048576 ? (value / 1048576).toFixed(1) + ' MiB/s' : (value / 1024).toFixed(1) + ' KiB/s';
    }
    function overview() {
        const ip = network?.ip?.split('/')[0] || 'Chưa có IP';
        const ssid = network?.active_ssid || network?.active || 'Chưa có Wi-Fi';
        const cpu = number(metrics.cpu, '%');
        const ram = number(metrics.ram?.percent, '%');
        const temp = number(metrics.temperature, '°C');
        const disk = metrics.disks?.find(item => item.mount === '/srv/pi-control') ||
            metrics.disks?.find(item => item.mount === '/');
        const gib = value => Number.isFinite(value) ? (value / 1073741824).toFixed(1) + ' GiB' : '—';
        const free = gib(disk?.free) + ' / ' + gib(disk?.total);
        const wifi = network?.ip && metrics.network?.find(item => item.name === 'wlan0');
        const rx = rate(wifi?.rx_rate);
        const tx = rate(wifi?.tx_rate);
        const hot = metrics.temperature >= 80;
        const warning = metrics.stale ? 'Dữ liệu cũ' : metrics.power?.undervoltage ? 'Nguồn yếu' :
            hot ? 'Nhiệt độ cao' : metrics.power?.throttled ? 'Đang giảm xung' : null;
        header(warning || 'Tổng quan', warning ? amber : accent);
        cat('network', 220, 39, 87);
        text('Nhiệt độ SoC', 16, 60, 13, muted);
        text(temp, 13, 111, 46, hot ? amber : white, mono, 187);
        bar(Number.isFinite(metrics.temperature) ? metrics.temperature / 85 : null, 16, 116, 178, hot ? amber : accent);
        text(ip, 16, 149, 18, white, mono, 183);
        text(ssid, 16, 167, 10, muted, font, 181);
        text('Đã chạy ' + uptimeLabel(metrics.uptime), 16, 188, 11, muted, font, 183);
        [['CPU', metrics.cpu, cpu], ['RAM', metrics.ram?.percent, ram]].forEach(([title, value, display], index) => {
            const y = 132 + index * 38;
            text(title, 220, y, 11, muted);
            text(display, 252, y + 1, 16, white, mono, 53);
            bar(Number.isFinite(value) ? value / 100 : null, 220, y + 10, 83);
        });
        const volume = disk?.mount === '/srv/pi-control' ? 'Ổ dữ liệu' : 'Ổ hệ thống';
        details([[disk?.mount === '/srv/pi-control' ? 'Ổ trống' : 'Hệ thống trống', gib(disk?.free)], ['↓ Nhận', rx], ['↑ Gửi', tx]]);
        return [ip + ' · ' + ssid, 'CPU ' + cpu + ' · RAM ' + ram + ' · ' + temp,
            volume + ' còn trống ' + free, 'Nhận ' + rx + ' · Gửi ' + tx].join(' | ');
    }
    function preview() {
        const state = mode();
        const simulated = {
            pending: 'rescue', hotspot: 'rescue', offline: 'rescue', playing: 'music',
            power: 'health', hot: 'health', disk: 'storage', boot: 'boot', shutdown: 'boot'
        };
        if (simulated[state]) return simulated[state];
        if (selected) return selected;
        if (config.auto) {
            if (config.enabled.includes('rescue') && (rescueStates[metrics.guard?.state] ||
                (network && (!network.ip || network.active === 'Pi-Fallback')))) return 'rescue';
            if (config.enabled.includes('health') && (metrics.power?.status === 'danger' || metrics.temperature >= 80)) return 'health';
            if (config.enabled.includes('music') && media?.has_video && media.paused === false && !media.ad && !media.standby) return 'music';
        }
        return config.defaultPage;
    }
    function draw() {
        if (!accessible()) return;
        const id = preview(), state = mode();
        const simulated = state !== 'live';
        const liveDisplay = !simulated && !selected && service?.ready;
        const showClip = liveDisplay && service.active === 'clip' && service.clip;
        const showFrame = liveDisplay && !showClip && id === 'summary' && service.frame;
        $('mini-ambient').hidden = Boolean(showClip || !config.motion || state === 'hotspot' ||
            (!simulated && id === 'rescue' && network?.active === 'Pi-Fallback'));
        clip.hidden = !showClip;
        frame.hidden = !showFrame;
        screen.hidden = Boolean(showClip || showFrame);
        if ((!showClip || reduced.matches || !config.motion) && !clip.paused) clip.pause();
        if (showClip) {
            const url = '/api/mini-display/clip.mp4?v=' + encodeURIComponent(service.clip.revision);
            if (clip.getAttribute('src') !== url) clip.src = url;
            if (clip.paused && !reduced.matches && config.motion && !clip.dataset.started) {
                clip.dataset.started = 'true';
                clip.play().catch(() => {});
            }
            $('mini-source').textContent = 'Phát lặp';
            $('mini-reading').textContent = '';
        } else {
            delete clip.dataset.started;
        }
        if (showFrame) {
            const url = '/api/mini-display/frame.png?v=' + encodeURIComponent(service.frame);
            if (frame.getAttribute('src') !== url) frame.src = url;
        }
        const animate = !screen.hidden && config.motion && !reduced.matches && id === 'clock';
        if (animate && !animationTimer) animationTimer = setInterval(draw, 250);
        if (!animate && animationTimer) {
            clearInterval(animationTimer);
            animationTimer = null;
        }
        if (showClip) return;
        if (showFrame) {
            $('mini-source').textContent = 'Khung từ Pi';
            const description = [
                network?.ip?.split('/')[0],
                'Nhiệt độ ' + number(metrics.temperature, '°C'),
                'CPU ' + number(metrics.cpu, '%'),
                'RAM ' + number(metrics.ram?.percent, '%'),
                'Đã chạy ' + uptimeLabel(metrics.uptime)
            ].filter(Boolean).join(' · ');
            if ($('mini-reading').textContent !== description) $('mini-reading').textContent = description;
            return;
        }
        const warning = id === 'rescue' || id === 'storage' || state === 'power' || state === 'hot' ||
            (id === 'health' && (metrics.power?.status === 'danger' || metrics.temperature >= 80));
        backdrop();
        const tone = warning ? amber : accent;
        if (id !== 'summary') header(id === 'storage' ? 'Dung lượng lưu trữ' : pages[id], tone);
        let reading;
        if (id === 'summary') {
            reading = overview();
        } else if (id === 'network') {
            const ip = network?.ip?.split('/')[0] || 'Chưa có IP';
            const ssid = network?.active_ssid || network?.active || 'Chưa đọc được Wi-Fi';
            const signal = network?.ip ? network.signal : null;
            const wifi = metrics.network?.find(item => item.name === 'wlan0');
            side(id);
            text('Địa chỉ IP', 16, 64, 13, muted);
            text(ip, 15, 105, 20, white, mono, 186);
            text(ssid, 16, 136, 11, muted, font, 184);
            text('Sóng Wi-Fi', 16, 168, 12, muted);
            bar(Number.isFinite(signal) ? signal / 100 : null, 16, 179, 182);
            text(number(signal, '%'), 236, 169, 22, tone, mono, 68);
            details([['Kết nối', network?.ip ? 'Có IP' : 'Chờ IP'], ['↓ Nhận', rate(wifi?.rx_rate)], ['↑ Gửi', rate(wifi?.tx_rate)]]);
            reading = ssid + ' · ' + ip;
        } else if (id === 'rescue') {
            const ap = state === 'hotspot' || (!simulated && network?.active === 'Pi-Fallback');
            const ip = state === 'hotspot' ? '192.168.50.1' :
                ['pending', 'offline'].includes(state) ? null : network?.ip?.split('/')[0];
            if (ap && ip) {
                text('Wi-Fi dự phòng', 16, 63, 13, amber);
                text(network?.hotspot?.ssid || 'RaspPI4OfTT', 16, 90, 17, white, font, 164);
                text(ip + ':18765', 16, 115, 13, white, mono, 164);
                const qr = image('mini-fallback-qr.svg');
                if (ip === '192.168.50.1' && qr.complete && qr.naturalWidth) {
                    ctx.imageSmoothingEnabled = false;
                    ctx.drawImage(qr, 192, 56, 111, 111);
                }
                cat(id, 64, 120, 73);
                divider(197);
                text(ip === '192.168.50.1' ? 'Kết nối Wi-Fi rồi quét QR' : 'Kết nối Wi-Fi rồi mở địa chỉ trên',
                    16, 224, 14, white, font, 288);
                reading = ip === '192.168.50.1' ? 'Vào Wi-Fi dự phòng trước khi quét mã mở Dashboard.' :
                    'Vào Wi-Fi dự phòng rồi mở địa chỉ trên màn.';
            } else {
                const status = state === 'offline' ? 'Mất kết nối mạng' : state === 'pending' ? rescueStates['connection-pending'] :
                    rescueStates[metrics.guard?.state] || (network?.ip ? 'Wi-Fi đang hoạt động' : 'Chưa nhận địa chỉ IP');
                side(id);
                headline(status, 16, 96, 23, 180, tone);
                text('Địa chỉ IP', 16, 153, 12, muted);
                text(ip || 'Chưa nhận IP', 16, 178, 16, white, mono, 184);
                details([['Wi-Fi', state === 'pending' ? 'Đang dò mạng' :
                    state === 'offline' ? 'Ngoại tuyến' : network?.active_ssid || '—'], ['Chế độ', 'Cứu hộ']]);
                reading = status;
            }
        } else if (id === 'health') {
            const degrees = state === 'power' ? 47 : state === 'hot' ? 84 : metrics.temperature;
            const temperature = number(degrees, '°C');
            const cpu = number(state === 'power' ? 18 : metrics.cpu, '%');
            const ram = number(state === 'power' ? 26 : metrics.ram?.percent, '%');
            side(id);
            text('Nhiệt độ SoC', 16, 64, 13, muted);
            text(temperature, 13, 120, 48, tone, mono, 184);
            bar(Number.isFinite(degrees) ? degrees / 85 : null, 16, 132, 182, tone);
            const power = state === 'hot' ? 'Nhiệt độ cao' : state === 'power' || metrics.power?.undervoltage ? 'Nguồn yếu' :
                metrics.power?.throttled ? 'Đang giảm xung' :
                    metrics.power?.status === 'warning' ? 'Từng có cảnh báo nguồn/nhiệt' :
                        metrics.power?.status === 'healthy' ? 'Nguồn ổn định' : 'Chưa đọc được nguồn';
            text(power, 16, 174, 13, warning ? tone : muted, font, 183);
            const uptime = state === 'power' ? 7320 : metrics.uptime;
            const uptimeText = uptimeLabel(uptime).replace(' ngày', 'n').replace(' giờ', 'g').replace(' phút', 'p');
            details([['CPU', cpu], ['RAM', ram], ['Đã chạy', uptimeText]]);
            reading = temperature + ' · CPU ' + cpu + ' · RAM ' + ram + ' · ' + power;
        } else if (id === 'storage') {
            side('bambu');
            text('Đã dùng dung lượng', 16, 64, 13, muted);
            text('94%', 14, 119, 48, amber, mono, 184);
            bar(0.94, 16, 132, 182, amber);
            text('Ổ lưu trữ gần đầy', 16, 174, 14, amber, font, 183);
            details([['Phân vùng', 'Ổ dữ liệu'], ['Còn trống', '4.0 GiB'], ['Tổng', '66.4 GiB']]);
            reading = 'Mô phỏng ổ dữ liệu đã dùng 94%, còn trống 4.0 GiB.';
        } else if (id === 'music') {
            const song = state === 'playing' ? {title: 'Nhạc để tập trung', provider: 'youtube', position: 65, duration: 210} : media;
            const provider = song?.provider === 'spotify' ? 'Spotify' : song?.provider === 'youtube' ? 'YouTube' : 'Media';
            const known = song?.position_known !== false && Number.isFinite(song?.position) && song?.duration > 0;
            side(id);
            text(provider, 16, 64, 13, accent);
            headline(song?.title || 'Chưa có bài đang phát', 16, 96, 21, 183);
            if (song?.artist) text(song.artist, 16, 151, 13, muted, font, 182);
            bar(known ? song.position / song.duration : null, 16, 176, 182);
            details([['Đã phát', known ? remaining(song.position) : '—'], ['Thời lượng', known ? remaining(song.duration) : '—'],
                ['Trạng thái', !song?.title ? 'Đang chờ' : song.paused ? 'Tạm dừng' : 'Đang phát']]);
            reading = song?.title || 'Chưa có bài đang phát';
        } else if (id === 'audio') {
            const output = audio?.devices?.find(item => item.kind === 'output' && item.name === audio.defaults?.output);
            const sleep = media?.preferences?.sleep;
            side(id);
            text('Âm lượng loa', 16, 64, 13, muted);
            text(output?.muted ? 'Tắt tiếng' : number(output?.volume, '%'), 14, 119, output?.muted ? 28 : 45, tone, mono, 184);
            bar(Number.isFinite(output?.volume) ? (output.muted ? 0 : output.volume / 100) : null, 16, 132, 182);
            text(output?.label || 'Chưa đọc được đầu ra', 16, 171, 14, muted, font, 184);
            const note = sleep?.active ? 'Dừng nhạc sau ' + remaining(sleep.remaining) : 'Chưa hẹn giờ ngủ';
            details([['Hẹn giờ ngủ', sleep?.active ? remaining(sleep.remaining) : 'Chưa hẹn']]);
            reading = (output?.label || 'Chưa đọc được đầu ra') + ' · ' + note;
        } else if (id === 'clock') {
            const now = new Date();
            side(id, true);
            text(clock.format(now), 12, 121, 50, white, mono, 187);
            text(calendar.format(now), 16, 162, 14, muted, font, 185);
            details([['Múi giờ', 'Việt Nam · UTC+7']]);
            reading = 'Đồng hồ giờ Việt Nam';
        } else if (id === 'boot') {
            const title = state === 'shutdown' ? 'Đang tắt…' : 'Đang khởi động';
            side(id);
            headline(state === 'live' ? 'Chọn tình huống' : title, 16, 99, 24, 185);
            text(state === 'shutdown' ? 'Chờ hệ thống dừng' : state === 'boot' ? 'Đang chờ kết nối mạng' : 'Khởi động hoặc tắt máy',
                16, 176, 13, muted, font, 183);
            details([['Thiết bị', 'Raspberry Pi 4'], ['Chế độ', 'Mô phỏng']]);
            reading = state === 'live' ? 'Trang này chỉ mô phỏng trong trình duyệt.' : title;
        } else {
            side(id);
            headline('Chưa kết nối máy in', 16, 100, 24, 186);
            details([['Tiến độ', '—'], ['Còn lại', '—'], ['Lớp in', '—']]);
            reading = 'Cần tích hợp dữ liệu máy in.';
        }
        $('mini-source').textContent = simulated ? 'Mô phỏng' :
            id === 'boot' || id === 'bambu' || id === 'clock' ? 'Xem trước' :
                metrics.stale ? 'Dữ liệu cũ' : dataMissing ? 'Thiếu dữ liệu' : 'Dữ liệu Pi';
        if ($('mini-reading').textContent !== reading) $('mini-reading').textContent = reading;
    }
    function save() {
        try {
            localStorage.setItem(key, JSON.stringify(config));
            $('mini-storage').textContent = 'Đã lưu trên trình duyệt này.';
        } catch { $('mini-storage').textContent = 'Trình duyệt không lưu được. Tải cấu hình để giữ lựa chọn.'; }
    }
    function refreshControls(focus) {
        const list = $('mini-pages');
        list.replaceChildren();
        for (const [index, id] of config.order.entries()) {
            const row = document.createElement('li');
            row.dataset.selected = String(selected === id);
            const check = document.createElement('input');
            check.type = 'checkbox';
            check.checked = config.enabled.includes(id);
            check.disabled = id === 'bambu' || (check.checked && config.enabled.length === 1);
            check.setAttribute('aria-label', 'Bật trang ' + pages[id]);
            check.dataset.control = id + '-enable';
            check.onchange = () => {
                config.enabled = config.order.filter(page => page === id ? check.checked : config.enabled.includes(page));
                if (!config.enabled.includes(config.defaultPage)) config.defaultPage = config.enabled[0];
                save(); refreshControls(check.dataset.control); schedule();
            };
            const label = document.createElement('button');
            label.type = 'button';
            label.className = 'btn btn-ghost mini-page-name';
            label.textContent = pages[id];
            label.dataset.control = id + '-page';
            label.setAttribute('aria-pressed', String(selected === id));
            if (id === 'bambu') {
                const note = document.createElement('small');
                note.textContent = 'Cần tích hợp';
                label.append(note);
            }
            label.onclick = () => {
                selected = selected === id ? null : id;
                $('mini-mode').value = 'live';
                refreshControls(label.dataset.control);
                schedule();
            };
            row.append(check, label);
            for (const step of [-1, 1]) {
                const move = document.createElement('button');
                const direction = step < 0 ? 'lên' : 'xuống';
                move.type = 'button';
                move.className = 'btn btn-ghost mini-move';
                move.dataset.control = id + direction;
                move.setAttribute('aria-label', 'Đưa ' + pages[id] + ' ' + direction);
                move.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="' +
                    (step < 0 ? 'M6 14l6-6 6 6' : 'M6 10l6 6 6-6') + '"/></svg>';
                move.disabled = index + step < 0 || index + step >= config.order.length;
                move.onclick = () => {
                    const other = index + step;
                    [config.order[index], config.order[other]] = [config.order[other], config.order[index]];
                    config.enabled = config.order.filter(page => config.enabled.includes(page));
                    save(); refreshControls(move.dataset.control);
                };
                row.append(move);
            }
            list.append(row);
        }
        $('mini-default').replaceChildren(...config.enabled.map(id => new Option(pages[id], id)));
        $('mini-default').value = config.defaultPage;
        $('mini-auto').checked = config.auto;
        $('mini-motion').checked = config.motion;
        if (focus) {
            const control = [...list.querySelectorAll('[data-control]')].find(node => node.dataset.control === focus);
            (control?.disabled ? control.closest('li').querySelector('.mini-page-name') : control)?.focus();
        }
        if (accessible()) draw();
    }
    async function read(path, signal) {
        const response = await fetch('/api/' + path, {cache: 'no-store', signal});
        if (!response.ok || response.redirected) throw new Error('Không đọc được dữ liệu Pi');
        const result = await response.json();
        if (!result.ok) throw new Error('Dịch vụ chưa sẵn sàng');
        return result.data;
    }
    function syncService() {
        const ready = service?.ready && !changingSource;
        $('mini-use-summary').disabled = !ready;
        $('mini-use-clip').disabled = !ready || !service.clip;
        $('mini-upload-submit').disabled = !ready || service.busy;
        $('mini-use-summary').setAttribute('aria-pressed', String(service?.source !== 'clip'));
        $('mini-use-clip').setAttribute('aria-pressed', String(service?.source === 'clip'));
        const note = $('mini-service-note');
        const error = message || (!service?.busy && service?.error);
        note.classList.toggle('mini-service-note-error', Boolean(error));
        note.textContent = error || (changingSource ? 'Đang gửi yêu cầu…' : service?.busy ? 'Pi đang xử lý tệp…' : service?.clip
            ? service.clip.name + ' · ' + service.clip.duration + ' giây'
            : service?.ready ? 'Tải một tệp để bật chế độ phát lặp.' : 'Service màn hình chưa sẵn sàng.');
        if (accessible()) draw();
    }
    async function refreshService() {
        if (!accessible() || changingSource || serviceRequest || Date.now() - serviceAt < 3000) return;
        const controller = new AbortController();
        serviceRequest = controller;
        serviceAt = Date.now();
        try {
            const data = await read('mini-display', AbortSignal.any([controller.signal, AbortSignal.timeout(6000)]));
            if (serviceRequest === controller) {
                if (service?.clip?.revision !== data.clip?.revision) delete clip.dataset.started;
                service = data;
                syncService();
            }
        } catch {
            if (serviceRequest === controller) {
                service = null;
                syncService();
            }
        } finally {
            if (serviceRequest === controller) serviceRequest = null;
        }
    }
    async function updateService(path, body, json = false) {
        if (changingSource) return;
        changingSource = true;
        message = '';
        serviceRequest?.abort();
        serviceRequest = null;
        syncService();
        try {
            const headers = {'X-CSRF-Token': $('ops-csrf').value};
            if (json) headers['Content-Type'] = 'application/json';
            const response = await fetch('/api/mini-display' + path, {
                method: 'POST', headers, body, signal: AbortSignal.timeout(45000)
            });
            if (response.redirected) throw Error('Phiên đăng nhập đã hết hạn.');
            const result = await response.json();
            if (!response.ok || !result.ok) throw Error(result.error || 'Không cập nhật được nội dung.');
            service = result.data;
            selected = null;
            $('mini-mode').value = 'live';
            if (json && service.source === 'summary') {
                if (!config.enabled.includes('summary')) config.enabled.unshift('summary');
                config.defaultPage = 'summary';
                save();
            }
            refreshControls();
            return true;
        } catch (error) {
            message = error instanceof SyntaxError ? 'Pi không trả về kết quả. Kiểm tra kết nối rồi thử lại.' : error.message;
            return false;
        } finally {
            changingSource = false;
            serviceAt = 0;
            syncService();
            refreshService();
        }
    }
    $('mini-use-summary').onclick = () => updateService('', JSON.stringify({source: 'summary'}), true);
    $('mini-use-clip').onclick = () => updateService('', JSON.stringify({source: 'clip'}), true);
    $('mini-upload').onsubmit = async event => {
        event.preventDefault();
        const file = $('mini-upload-file').files[0];
        if (!file) return;
        if (file.size > 16 * 1024 * 1024) {
            message = 'Tệp vượt quá 16 MiB.';
            syncService();
            return;
        }
        const body = new FormData();
        body.append('clip', file);
        if (await updateService('/upload', body)) event.target.reset();
    };
    async function refreshData() {
        if (!accessible() || mode() !== 'live' || pending || Date.now() - fetchedAt < 10000) return;
        const controller = new AbortController();
        pending = controller;
        fetchedAt = Date.now();
        const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(12000)]);
        const wantMedia = ['music', 'audio'].includes(selected || config.defaultPage) ||
            (!selected && config.auto && config.enabled.includes('music'));
        const wantAudio = (selected || config.defaultPage) === 'audio';
        const results = await Promise.allSettled([
            read('status', signal), wantMedia ? read('media', signal) : null, wantAudio ? read('audio', signal) : null
        ]);
        if (pending !== controller) return;
        pending = null;
        const value = index => results[index].status === 'fulfilled' ? results[index].value : null;
        network = value(0);
        media = value(1);
        audio = value(2);
        dataMissing = results.some(result => result.status === 'rejected');
        if (accessible()) draw();
    }
    function schedule() {
        clearInterval(timer);
        clearInterval(animationTimer);
        animationTimer = null;
        pending?.abort();
        pending = null;
        fetchedAt = 0;
        serviceRequest?.abort();
        serviceRequest = null;
        serviceAt = 0;
        if (!accessible()) {
            clip.pause();
            delete clip.dataset.started;
            return;
        }
        draw();
        refreshData();
        refreshService();
        timer = setInterval(() => {
            if (!animationTimer && ['summary', 'clock'].includes(preview())) draw();
            refreshData();
            refreshService();
        }, 1000);
    }
    $('mini-mode').onchange = () => { selected = null; refreshControls(); schedule(); };
    $('mini-default').onchange = event => { config.defaultPage = event.target.value; selected = null; save(); refreshControls(); schedule(); };
    $('mini-auto').onchange = event => { config.auto = event.target.checked; selected = null; save(); refreshControls(); schedule(); };
    $('mini-motion').onchange = event => { config.motion = event.target.checked; save(); schedule(); };
    $('mini-reset').onclick = () => { config = defaults(); selected = null; save(); refreshControls(); schedule(); };
    $('mini-export').onclick = () => {
        const url = URL.createObjectURL(new Blob([JSON.stringify(config, null, 2)], {type: 'application/json'}));
        const link = document.createElement('a');
        link.href = url;
        link.download = 'pi-control-mini-display.json';
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    };
    window.addEventListener('pi:metrics', event => { metrics = event.detail; if (accessible()) draw(); });
    window.addEventListener('pi:view', schedule);
    document.addEventListener('visibilitychange', schedule);
    reduced.addEventListener('change', schedule);
    document.fonts.ready.then(() => { if (accessible()) draw(); });
    refreshControls();
    schedule();
})();

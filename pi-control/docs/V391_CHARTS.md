# Dashboard 3.9.1 — chart colors and labelled axes

Deployed18October2026:release20261018T122853-266190; root-only recovery snapshot
/var/lib/piwifi-deploy/20261018T122853-266190, latest5retained. Production network
and resource axes/colors verified in dark and light at390px; documentwidth375px,
no horizontal overflow. Original dark theme and viewport restored after QA.

User requested readable, distinct chart series and numeric X/Y axes. Network RX
is blue/solid; TX is orange/dashed, with matching legend and last-sample markers.
Y shows numeric speeds with automatic B/s,KiB/s,MiB/s units and a rounded scale.
X uses actual sample timestamps over the last290seconds, not array positions.
Null/invalid values and gaps over25seconds break network lines.

Resource history uses blueCPU,purpleRAM,orangeTemperature with distinct strokes.
Left axis0–100CPU/RAM%, right0–100°C, shared numeric range explicitly labelled.
Time labels include seconds below1hour and dates for multi-day ranges. Missing
values and cadence gaps break paths. Single valid samples have visible dots.

SVG viewBox matches actual CSS width, fixed240pxheight; labels remain10px on
phones, with3Xticks on narrow screens and5on desktop. ResizeObserver redraws
existing RAM data without new polling/network requests. New charts.js must stay
in installer/deployallowlist and load before hardware.js/operations.js.

Node checks cover scale, timestamp spacing, null/outage gaps, invalid values and
phone plot geometry. Existing polling lifecycle passed. Production chart colors,
axes and responsive light/dark checks recorded for this release. No DNS/Wi-Fi/
media policy changes; normal managed deployment restarts RAM observer history.

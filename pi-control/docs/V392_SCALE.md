# Dashboard 3.9.2 — responsive proportions

User requested appropriate screen scaling and a more deliberate, maintainable UI.
Replaced the previous studio responsive blocks with one set of breakpoints and
shared sidebar/content/card/gap tokens. No CSS zoom or whole-page transform.
The app reserves sidebar space and centers max1600pxcontent in the remaining
area; tablet/phone navigation remains horizontal. Media stacks below1280px,
metrics use2columns below1280px, and narrow phones below360px use1metric column.

Body14px; supporting component text12px (metric notes11px on phones; decorative
eyebrow/brand subtitle10px). Playback targets44–46px. Headings26–36px, proportional
padding/gaps via clamp. Small-height landscape releases the sticky header.
Charts use220–300pxheight and SVG coordinates derived from actual dimensions,
with12pxlabels and fewer time ticks when needed. ResizeObserver tracks both
width and height, redraws existing RAM data, and does not add polling.

Production QA:49view/viewport measurements,7tabs each at360,390,768,1024,1366,
1920,2560px; no document horizontal overflow. Media1column at360–1024 and2at
1366+,content capped1600 at1920/2560. Network chart220px at360–768,225at1024,
300at1366+. Light390px nooverflow/12pxchartlabels verified. Default viewport
and dark theme restored. This is browser emulation, not physical device testing.

Node chart tests cover pixel coordinates at240–2560width and220–300height,
timestamp spacing, gap handling; polling lifecycle passed. Normal deploy health
checks passed. Finalrelease/snapshot20261018T123427-267458(root-only recovery,
latest5retained). Screenshots:ops/dashboard-392-laptop.png,ops/dashboard-392-phone.png.
Measurement artifact:ops/dashboard-392-layout-audit.json.

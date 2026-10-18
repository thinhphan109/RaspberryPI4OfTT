# Dashboard 3.9 — Pi Control studio

User requested a new design using frontend-design. Replaces the visual direction
of3.2.1 with warm ivory/forest light and charcoal/sage dark modes. `studio.css`
loads after the existing dashboard component base and owns the current visual
tokens, navigation, cards, forms, buttons, tables, metrics and Media composition.
Keep it in the deploy allowlist and installer. Fonts/logo stay bundled, no CDN.

Brand is Pi Control with the existing Raspberry mark. Sidebar icons distinguish
Media/apps. Workspace bar is a static label, not a synthetic connectivity signal.
Media art and metadata form a compact grid; playback buttons and next item are
grouped together; sleep and settings have distinct surfaces. Long video titles
clamp visually but the full text remains accessible in the heading.

At390px the player uses an84pxthumbnail and a separate metadata column; touch
playback buttons are46pxhigh. Sidebar becomes horizontal navigation. Existing
light/dark persistence, reduced-motion behavior, IDs, forms, CSRF, APIs, view-aware
polling and Media policies remain. Only template/CSS/deploy packaging changed.

Verified on18October: production desktop Media/overview, both color modes and
all7tabs at emulated390px. Document widths375–390px at390pxviewport (no document
horizontal overflow); GPIO retains its existing internal board layout. Polling
lifecycle test passed; deployment AST/sudoers/login health checks passed. Services
web/observer/guard/adguardhome/cloudflared/media active. No physical iPhone test.

Final release20261018T122030-263893; root-only recovery snapshot
/var/lib/piwifi-deploy/20261018T122030-263893, latest5retained.

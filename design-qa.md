# Design QA

## Comparison target

- Source visual truth: `C:\Users\lg140\AppData\Local\Temp\codex-clipboard-f6eac5fb-ab15-484c-b5d5-f95ea9491f4e.png`.
- Source pixels: 868 × 502.
- Implementation: `http://localhost:5173`.
- Desktop evidence: `tmp/product-design/home-split-desktop.png`.
- Desktop pixels and CSS viewport: 1600 × 728 captured within a 1600 × 1000 viewport, device scale factor 1.
- Mobile evidence: `tmp/product-design/home-split-mobile.png`.
- Mobile pixels and CSS viewport: 390 × 1117 captured within a 390 × 844 viewport, device scale factor 1.
- State: public landing page in Simplified Chinese.

## Full-view comparison evidence

- Combined reference and implementation: `tmp/product-design/home-split-comparison.png`.
- The reference and desktop implementation were normalized into equal-width panels in one 1200 × 407 comparison image.
- Focused-region comparison was not needed because the requested relationship—the copy and image occupying distinct columns—is clearly visible in the full hero comparison.

## Findings

- Fonts and typography: passed. Existing product type styles remain legible and the heading wraps cleanly without overlapping the image.
- Spacing and layout rhythm: passed. At 1600 px the copy and photograph occupy independent left and right grid tracks with a 92 px gap. At 390 px they become stacked blocks with 30 px separation.
- Colors and visual tokens: passed. The pale clinical background, green text, button colors, radius, and shadow remain consistent with the existing design system.
- Image quality and asset fidelity: passed. The supplied clinical-session raster remains undistorted at a 4:3 ratio with its own 24 px rounded container.
- Copy and content: passed. Existing localized copy and both primary actions are unchanged.
- Responsive behavior: passed. Horizontal overflow is 0 px at both 1600 px and 390 px.
- Runtime and interactions: passed. Both primary actions navigate to `/patient/invite` and `/doctor/login`; no page or console errors were recorded.

## Comparison history

### Pass 1

- [P1] The previous implementation placed the hero copy over the photograph inside one immersive background frame, contradicting the new reference.

### Fix

- Replaced the immersive frame with a two-column grid and a standalone photograph container.
- Removed the decorative full-frame image treatment.
- Added a mobile single-column fallback while preserving all actions and copy.

### Pass 2

- Post-fix evidence: `tmp/product-design/home-split-comparison.png`, `tmp/product-design/home-split-desktop.png`, and `tmp/product-design/home-split-mobile.png`.
- No actionable P0, P1, or P2 findings remain.

## Follow-up polish

- The reference uses shorter copy and a more compact hero, but retaining the product's current clinical messaging is an intentional content constraint rather than a layout defect.

## Final result

passed

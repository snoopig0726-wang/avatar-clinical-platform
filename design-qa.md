# Design QA

## Comparison target

- Source visual truth: `D:\xwechat_files\wxid_phfkoz2s1svp11_64f7\temp\RWTemp\2026-07\ee745c3c4cab68f85d5bf9b597f7de0c\f91df14237a7741e5c0ae0d678e5a118.png`
- Source pixels: 1848 × 1200.
- Implementation: `http://localhost:5173`
- Browser: Microsoft Edge through Playwright.
- Desktop viewport: 1600 × 1000 CSS pixels, device scale factor 1.
- Mobile viewport: 390 × 844 CSS pixels, device scale factor 1.
- State: public landing page, empty patient invitation form, and empty clinician login form.
- API usage: none. No form was submitted and no image-generation request was made.

## Rendered evidence

| Surface | Desktop screenshot | Pixel dimensions | Mobile screenshot | Pixel dimensions |
| --- | --- | --- | --- | --- |
| Landing | `tmp/product-design/home-background-desktop.png` | 1600 × 2443 | `tmp/product-design/home-background-mobile.png` | 390 × 4138 |
| Patient invitation | `tmp/product-design/patient-background-desktop.png` | 1600 × 1000 | `tmp/product-design/patient-background-mobile.png` | 390 × 1002 |
| Clinician login | `tmp/product-design/doctor-background-desktop.png` | 1600 × 1000 | `tmp/product-design/doctor-background-mobile.png` | 390 × 953 |

The full-page landing capture was cropped to its first 1600 × 1000 pixels for normalized comparison. The two access pages already match the comparison viewport.

## Full-view comparison evidence

Each file contains the matching prototype region and implementation in one 2072 × 715 image:

- `tmp/product-design/home-background-comparison.png`
- `tmp/product-design/patient-background-comparison.png`
- `tmp/product-design/doctor-background-comparison.png`

Focused comparisons were not required because the hero, image crop, overlaid copy, form, and safety panel are all legible at the normalized full-view scale.

## Findings

- Fonts and typography: passed. Existing product typography and hierarchy remain intact; overlaid text uses sufficient weight and text shadow on photographic areas.
- Spacing and layout rhythm: passed. The landing hero now reads as one integrated visual frame; access-page headings and safety lists retain balanced spacing over the background imagery.
- Colors and visual tokens: passed. Pale-mint and clinical-green overlays match the established product palette while preserving contrast.
- Image quality and asset fidelity: passed. The supplied raster assets remain sharp, undistorted, and intentionally cropped. No placeholder or code-drawn replacement is used.
- Copy and content: passed. Existing localized content and operational labels are unchanged.
- Responsive behavior: passed. All three routes have zero horizontal overflow at 1600 px and 390 px. The landing image remains a subtle background on mobile; access-page forms remain first at phone width.
- Runtime and interaction: passed. All routes returned HTTP 200 with no console or page errors. Public navigation and required form fields were verified without submitting forms.

## Comparison history

### Pass 1

- [P1] The landing image appeared as an independent image card instead of a background integrated with the hero copy.
- [P2] Access-page safety points sat directly on the photograph and did not reproduce the prototype’s grouped dark information panel.

### Fixes

- Converted the landing hero into a single isolated background frame with the supplied image covering the frame and a left-to-right readability gradient beneath the copy.
- Added a semi-transparent, blurred safety panel over patient and clinician background images and refined the photographic overlay.
- Added responsive gradient and crop rules so mobile copy remains readable without introducing overflow.

### Pass 2

- Post-fix comparison evidence: the three `*-background-comparison.png` files listed above.
- No actionable P0, P1, or P2 findings remain.

## Follow-up polish

- [P3] If a future iteration aims for tighter prototype fidelity, the landing hero can be shortened slightly and the copy size reduced at intermediate tablet widths.

## Final result

passed

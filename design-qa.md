# Design QA

## Reference target

- Visual target: `C:\Users\lg140\AppData\Local\Temp\avatar-design-final-landing-desktop.png`
- State: patient-facing landing page, fully loaded
- Browser: Microsoft Edge through Playwright
- CSS viewport: 1600 × 1000
- Captured image: 1600 × 2050 (full page)
- Design intent carried across the product: warm clinical green palette, large and calm typography, patient-first language, soft cards, restrained borders, clear primary actions, and explicit professional-support boundaries.

## Implementation captures

Desktop captures used a 1600 × 1000 CSS viewport:

| Surface | State | Screenshot | Pixel size |
| --- | --- | --- | --- |
| Landing | fully loaded | `C:\Users\lg140\AppData\Local\Temp\avatar-design-final-landing-desktop.png` | 1600 × 2050 |
| Patient invite | empty invitation form | `C:\Users\lg140\AppData\Local\Temp\avatar-design-final-patient-invite-desktop.png` | 1600 × 1000 |
| Doctor login | empty login form | `C:\Users\lg140\AppData\Local\Temp\avatar-design-final-doctor-login-desktop.png` | 1600 × 1000 |
| Doctor application | empty application form | `C:\Users\lg140\AppData\Local\Temp\avatar-design-final-doctor-apply-desktop.png` | 1600 × 1057 |
| Administrator login | empty login form | `C:\Users\lg140\AppData\Local\Temp\avatar-design-final-admin-login-desktop.png` | 1600 × 1000 |
| Doctor workspace | authenticated demo doctor with cases | `C:\Users\lg140\AppData\Local\Temp\avatar-design-final-doctor-workspace-desktop.png` | 1600 × 1295 |
| Doctor case | active demo case with session and versions | `C:\Users\lg140\AppData\Local\Temp\avatar-design-final-doctor-case-desktop.png` | 1600 × 2049 |
| Doctor interview | Q8 and visual direction form | `C:\Users\lg140\AppData\Local\Temp\avatar-design-final-doctor-interview-desktop.png` | 1600 × 1847 |
| Administrator dashboard | authenticated overview tab | `C:\Users\lg140\AppData\Local\Temp\avatar-design-final-admin-dashboard-desktop.png` | 1600 × 1136 |

Mobile captures used a 390 × 844 CSS viewport at the Edge mobile project device scale:

| Surface | State | Screenshot | Captured pixels |
| --- | --- | --- | --- |
| Landing | fully loaded | `C:\Users\lg140\AppData\Local\Temp\avatar-design-final-landing-mobile.png` | 1073 × 10953 |
| Patient invite | empty invitation form | `C:\Users\lg140\AppData\Local\Temp\avatar-design-final-patient-invite-mobile.png` | 1073 × 2453 |
| Doctor workspace | authenticated demo doctor with cases | `C:\Users\lg140\AppData\Local\Temp\avatar-design-final-doctor-workspace-mobile.png` | 1073 × 6105 |
| Doctor case | active demo case | `C:\Users\lg140\AppData\Local\Temp\avatar-design-final-doctor-case-mobile.png` | 1073 × 10406 |
| Doctor interview | Q8 and visual direction form | `C:\Users\lg140\AppData\Local\Temp\avatar-design-final-doctor-interview-mobile.png` | 1073 × 7692 |
| Administrator dashboard | authenticated overview tab | `C:\Users\lg140\AppData\Local\Temp\avatar-design-final-admin-dashboard-mobile.png` | 1073 × 5206 |

## Combined comparison inputs

Each comparison places the 1600 × 1000 landing target crop on the left and the matching 1600 × 1000 implementation crop on the right:

- Patient access: `C:\Users\lg140\AppData\Local\Temp\avatar-design-comparison-access.png`
- Doctor workspace: `C:\Users\lg140\AppData\Local\Temp\avatar-design-comparison-workspace.png`
- Doctor case: `C:\Users\lg140\AppData\Local\Temp\avatar-design-comparison-case.png`
- Administrator dashboard: `C:\Users\lg140\AppData\Local\Temp\avatar-design-comparison-admin.png`

## QA history

### Pass 1 — typography, content, hierarchy

- Increased the global body and control scale and removed remaining 9–12 px operational text from primary reading surfaces.
- Rewrote patient, doctor, and administrator copy around patient understanding, professional support, treatment follow-up, safety, and authorization.
- Replaced provider/model-facing labels in normal UI with task-oriented language.
- Matched the landing target’s green, pale-mint, white, border, radius, and elevation treatment across access, workspace, case, interview, and administration screens.

### Pass 2 — responsive and interaction review

- Found that the access-page story panel appeared before the patient’s form on mobile. Hid the desktop-only story panel at phone widths and added a compact brand header so the core action appears immediately.
- Found a collapsed workspace boundary label overlapping mobile content. Removed that label in the collapsed state and added space for the menu trigger.
- Verified desktop and mobile public navigation, patient invitation entry, doctor authentication, protected-route rejection, case navigation, guided interview navigation, administrator authentication, and horizontal overflow.
- Verified focusable form controls, semantic labels, usable tap targets, reduced-motion support, and readable wrapping at 390 px.

## Final findings

- Typography: passed. Primary text is 16–20 px, page headings are 38–46 px on desktop, and supporting metadata no longer drops below practical reading size.
- Layout and spacing: passed. Desktop grids remain balanced; mobile screens stack without horizontal overflow or collapsed-card overlap.
- Colors and surfaces: passed. The landing page palette and soft clinical surface treatment are consistent across all reviewed routes.
- Copy and content: passed. Patient-facing routes lead with reassurance, professional accompaniment, and treatment relevance; staff routes use actionable clinical language without exposing unnecessary provider details.
- Icons and controls: passed. Existing icon-library assets remain aligned and consistent; primary controls and navigation paths work.
- Accessibility: passed for the implemented scope. Labels, keyboard-reachable controls, contrast, tap targets, text wrapping, and reduced-motion behavior were reviewed.
- Image quality: passed for the implemented scope. Existing generated/avatar imagery is preserved without stretching or low-resolution replacement.

## Final result

passed

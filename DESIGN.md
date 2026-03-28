# Design System Strategy: The Curated Shelter

## 1. Overview & Creative North Star
**Creative North Star: The Empathetic Architect**

This design system moves beyond the "administrative database" aesthetic to create a space that feels both surgically efficient and deeply humane. For a Pet Adoption Management System, staff members are often balancing high-stress logistical tasks with emotional work. The UI must act as a calming, authoritative partner. 

We break the "template" look through **Tonal Editorialism**. Instead of rigid grids separated by heavy lines, we use intentional asymmetry and expansive breathing room. High-contrast typography scales (the elegant 'Manrope' for headings against the functional 'Inter' for data) create a sense of hierarchy that mimics a high-end architectural magazine rather than a spreadsheet. The experience is defined by layered surfaces that suggest depth and focus, ensuring that even the most complex data entry feels like a premium, guided experience.

---

## 2. Colors & Surface Philosophy

The palette is rooted in professional stability (`primary: #41608c`) and clinical cleanliness (`background: #f7fafc`).

### The "No-Line" Rule
To achieve a signature look, **prohibit the use of 1px solid borders for sectioning.** Boundaries are defined strictly through background color shifts.
*   **Structure:** A dashboard sidebar should use `surface_container_low` against a `surface` main content area. 
*   **Separation:** Distinct data groups in a form are separated by a jump in tonal value (e.g., from `surface` to `surface_container`) rather than a divider line.

### Surface Hierarchy & Nesting
Treat the UI as a series of physical layers.
*   **Level 0 (Base):** `surface` (#f7fafc) – The canvas.
*   **Level 1 (Sections):** `surface_container_low` (#eff4f7) – Large structural areas.
*   **Level 2 (Cards/Widgets):** `surface_container_lowest` (#ffffff) – This creates a "lifted" effect for active working components.
*   **Level 3 (Popovers/Floating):** `surface_bright` with backdrop-blur – For high-priority temporary tasks.

### The "Glass & Gradient" Rule
To prevent the UI from feeling "flat," main Action Buttons or Hero Headers should utilize a subtle linear gradient transitioning from `primary` (#41608c) to `primary_dim` (#35547f). For floating navigation or modal headers, apply **Glassmorphism**: use `surface_container_lowest` at 80% opacity with a `12px` backdrop-blur to allow the soft blue hues of the system to bleed through.

---

## 3. Typography: The Editorial Scale

We pair two sans-serifs to balance personality with utility.

*   **Display & Headlines (Manrope):** These are our "Editorial" voices. `display-lg` (3.5rem) should be used for empty-state welcome screens or high-level shelter stats. The wide aperture of Manrope conveys transparency and trust.
*   **Titles & Body (Inter):** The workhorse. `title-md` (1.125rem) is the standard for form labels and table headers. `body-md` (0.875rem) is optimized for high-density data reading.
*   **Functional Labels:** `label-sm` (0.6875rem) using `on_surface_variant` (#586064) is reserved for metadata (e.g., "Animal ID" or "Entry Date").

---

## 4. Elevation & Depth

Hierarchy is achieved through **Tonal Layering** and light physics, not structural boxes.

*   **The Layering Principle:** Place a `surface_container_lowest` card on top of a `surface_container_low` background. This creates a soft, natural lift that is easier on the eyes than high-contrast borders.
*   **Ambient Shadows:** For floating elements (Modals/Dropdowns), use a shadow color of `primary_dim` at 6% opacity with a blur of `24px` and a `12px` Y-offset. This mimics natural light filtered through a window, reinforcing the "clean/airy" goal.
*   **The "Ghost Border" Fallback:** If a border is required for accessibility in input fields, use `outline_variant` (#aab3b7) at **20% opacity**. Never use a 100% opaque border.

---

## 5. Components

### Data Tables (The Core Experience)
*   **Constraint:** Forbid horizontal and vertical divider lines.
*   **Styling:** Use `surface_container_lowest` for the table container. Header row should be `surface_container_high` with `title-sm` typography. 
*   **Interaction:** On hover, a row should transition to `surface_container_low`. Use `primary` as a thin 4px vertical "accent bar" on the far left of a selected row.

### Buttons
*   **Primary:** Background gradient (`primary` to `primary_dim`), `on_primary` text, `xl` roundedness (0.75rem). 
*   **Secondary:** `surface_container_high` background with `on_primary_container` text. No border.

### Forms & Input Fields
*   **Layout:** Use a two-column asymmetric layout where labels sit to the left of the input, right-aligned, using `title-sm`. 
*   **Inputs:** `surface_container_lowest` background, `0.25rem` (DEFAULT) roundedness. Use `primary` for the active focus state glow (3px spread at 10% opacity).

### Pet Status Chips
*   **Selection Chips:** Use `secondary_container` with `on_secondary_container` text. Roundedness should be `full` to distinguish them from structural elements.

### Additional Component: The "Animal Timeline"
For medical records and adoption history, use a vertical "thread" where events are marked by `primary_fixed` circles. The vertical line should be a subtle `outline_variant` at 15% opacity.

---

## 6. Do's and Don'ts

### Do
*   **DO** use whitespace as a functional tool. A 3.5rem (`16`) gap between major dashboard sections is standard.
*   **DO** use `error` (#a83836) sparingly. Reserve it for critical alerts (e.g., "Medical Hold") to maintain the calming blue atmosphere.
*   **DO** ensure all interactive elements have a minimum target size of 44px, despite the "refined" look.

### Don't
*   **DON'T** use pure black (#000000) for text. Always use `on_surface` (#2b3437) for a softer, more professional contrast.
*   **DON'T** use "Drop Shadows" on cards. Stick to tonal shifts (Surface Nesting) unless the element is physically moving over the content (like a Modal).
*   **DON'T** crowd the data tables. If a table has more than 8 columns, implement a "detail drawer" using `surface_container_highest` rather than squishing columns.
---
name: Cliff Edwards - Homelab Portfolio
description: A self-deployed engineering portfolio and homelab showcase built from scratch by a self-taught DevOps engineer
colors:
  blueprint-blue: "#0058e6"
  blueprint-blue-deep: "#0044b3"
  blueprint-blue-wash: "#cce0ff"
  blueprint-blue-haze: "#f0f4ff"
  charcoal: "#333333"
  steel-mid: "#555555"
  steel-muted: "#888888"
  hairline: "#eeeeee"
  input-rule: "#cccccc"
  page-wash: "#f4f6f9"
  card-surface: "#ffffff"
typography:
  body:
    fontFamily: "Segoe UI, Roboto, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.7
  label:
    fontFamily: "Segoe UI, Roboto, sans-serif"
    fontSize: "0.9rem"
    fontWeight: 600
    lineHeight: 1.4
  meta:
    fontFamily: "Segoe UI, Roboto, sans-serif"
    fontSize: "0.85rem"
    fontWeight: 400
    lineHeight: 1.4
rounded:
  card: "12px"
  input: "8px"
  small: "4px"
spacing:
  sm: "0.75rem"
  md: "1rem"
  lg: "2rem"
  xl: "4rem"
components:
  button-primary:
    backgroundColor: "{colors.blueprint-blue}"
    textColor: "#ffffff"
    rounded: "{rounded.input}"
    padding: "0.75rem 1.5rem"
  button-primary-hover:
    backgroundColor: "{colors.blueprint-blue-deep}"
    textColor: "#ffffff"
    rounded: "{rounded.input}"
    padding: "0.75rem 1.5rem"
  nav-bar:
    backgroundColor: "{colors.blueprint-blue}"
    textColor: "#ffffff"
    rounded: "{rounded.card}"
    padding: "{spacing.md}"
---

# Design System: Cliff Edwards - Homelab Portfolio

## 1. Overview

**Creative North Star: "The Engineer's Notebook"**

This is an interface that earns its presence the same way its content does: through work, not decoration. The visual language is functional documentation - what an engineer builds when they want something that works beautifully rather than something that merely looks polished. No gradient heroes, no glowing metric widgets, no animated counter theatrics. What exists, exists because it serves the content.

Against the gravity of the generic developer portfolio - dark hero backgrounds, glassmorphic cards, color-washed everything - this system chooses light, direct, and readable. Blueprint Blue appears where it commands attention (navigation, primary actions, callout structure). Neutral surfaces carry the reading experience. The interface makes one argument, quietly: the content of this site is the work, and the work speaks for itself.

The design is not minimal because it is timid. It is minimal because the engineering behind it is the story. Every pixel decision defers to the words and the data, not the chrome.

**Key Characteristics:**

- Light-mode base with structured typographic hierarchy
- Single accent color used sparingly and structurally
- Consistent generous radius on containers (12px), tighter on interactive elements (8px)
- Ambient shadow only - no layered elevation drama
- Scroll-driven interactions where they reveal information, never where they decorate

## 2. Colors: The Blueprint Palette

A single-accent, light-base palette. Blueprint Blue is the only saturated hue in the system; neutrals carry everything else. The page-wash background has a barely-perceptible blue tint (not pure white) that grounds white cards without creating flat-on-flat contrast.

### Primary

- **Blueprint Blue** (#0058e6): navigation, primary buttons, link states, and structural callout accents. Appears on ≤15% of any surface.
- **Blueprint Blue Deep** (#0044b3): hover and pressed states on primary interactive elements. Never used as a standalone surface color.

### Neutral

- **Page Wash** (#f4f6f9): page background. The slight blue tint prevents a white-card-on-white-page problem.
- **Card Surface** (#ffffff): container and card backgrounds.
- **Blueprint Blue Haze** (#f0f4ff): callout and note backgrounds. Communicates distinction through tint alone - no border required.
- **Blueprint Blue Wash** (#cce0ff): passive tints, future chip or tag backgrounds.
- **Charcoal** (#333333): primary text. Warm-dark, never pure black.
- **Steel Mid** (#555555): secondary text, supporting copy, form labels.
- **Steel Muted** (#888888): meta content - timestamps, captions, muted labels.
- **Hairline** (#eeeeee): section dividers, blog post separators.
- **Input Rule** (#cccccc): input field borders at rest.

### Named Rules

**The One Accent Rule.** Blueprint Blue appears on ≤15% of any surface. Used in more than one structural role per screen, it dilutes to decoration. Restraint is the point.

**The No-Pure-Black Rule.** No element uses raw `#000` or `#fff`. Text anchors at Charcoal (#333333). Backgrounds anchor at Page Wash (#f4f6f9) or Card Surface (#ffffff) as named tokens only. Every surface has a tint.

## 3. Typography

**Body Font:** Segoe UI, Roboto, sans-serif (system stack)

No separate display font. The system relies on weight and size contrast within the same sans-serif family. The content density of an engineering document, not a landing page. The voice carries the personality - the type gets out of the way.

### Hierarchy

- **Headline** (bold, ~1.75rem, line-height 1.3): page-level h1. Centered. Used once per page.
- **Title** (bold, ~1.25rem, line-height 1.4): section headings (h2). Left-aligned. Provides structural rhythm across long pages.
- **Body** (regular, 1rem, line-height 1.7): primary reading text. Line height is generous for the dense, narrative-heavy copy on this site. Cap line length at 65–75ch.
- **Label** (semibold, 0.9rem, line-height 1.4): form labels, UI captions.
- **Meta** (regular, 0.85rem, line-height 1.4): timestamps, muted annotations.

### Named Rules

**The Hierarchy-Through-Contrast Rule.** Adjacent type levels must differ by weight AND size. Weight contrast alone (bold vs. regular at the same size) is too flat for narrative-heavy pages.

## 4. Elevation

The system is ambient-shadow by default. Cards float off the page-wash background via a single diffuse shadow (`0 0 20px rgba(0,0,0,0.05)`). There are no layered elevations, no hard-dropped shadows, no z-stack theatrics. Depth is communicated by background tint contrast (page-wash vs. card-surface), not by shadow intensity.

**The Flat-By-Default Rule.** Shadows exist only on resting card surfaces. Interactive elements convey state through color shift, not shadow change. Do not add shadows to hover or active states - that is decoration, not feedback.

### Shadow Vocabulary

- **Card Ambient** (`0 0 20px rgba(0,0,0,0.05)`): used on all container surfaces. Diffuse, barely perceptible at small sizes, creates the perception of lift on large screens.

## 5. Components

### Buttons

Direct and confident, no styling flourishes.

- **Shape:** Gently rounded (8px radius)
- **Primary:** Blueprint Blue (#0058e6) background, white text, 0.75rem vertical / 1.5rem horizontal padding
- **Hover:** Blueprint Blue Deep (#0044b3), 0.3s ease transition on background-color
- **No secondary or ghost variant defined.** Introduce only when a genuine second action tier exists in the UI.

### Navigation

Anchored at the top of each container. Horizontal flex row, centered, wraps on small screens.

- **Shape:** 12px radius (matches card container)
- **Background:** Blueprint Blue (#0058e6)
- **Text:** White, bold, 1rem
- **Hover:** Blueprint Blue Wash (#cce0ff) text color, 0.3s transition
- **Mobile:** wraps to multi-row, reduces font size to 0.9rem and padding to 0.75rem

### Cards / Containers

The primary surface unit. All page content lives inside a container.

- **Corner Style:** Generously rounded (12px)
- **Background:** Card Surface (#ffffff)
- **Shadow:** Card Ambient (see Elevation)
- **Border:** None
- **Internal Padding:** 2rem (reduces to 1rem on mobile)
- **Max Width:** 500px standard, 900px wide variant (About Me, Blog, Resume)

### Inputs / Fields

Utilitarian and undecorated.

- **Style:** 1px solid border (Input Rule, #cccccc), 8px radius, full width, 0.75rem padding
- **Focus:** Add `outline: 2px solid rgba(0,88,230,0.4)` at 2px offset - not currently defined in CSS; required before production.
- **Error:** Currently raw CSS `red` - must be formalized as `#dc2626` before deployment.

### Note / Callout

A distinct surface for important contextual information.

- **Background:** Blueprint Blue Haze (#f0f4ff)
- **Border:** Currently `border-left: 4px solid #0058e6` - flagged for removal. The background tint alone communicates distinction; the left-side stripe is redundant and borrows a dated convention. If a border is desired for containment, use a full 1px border in Blueprint Blue Wash (#cce0ff) on all four sides.
- **Text:** Body size, Charcoal (#333333)
- **Link within note:** Blueprint Blue, underlined

### Tooltip

The only interactive reveal pattern currently in the system.

- **Trigger:** `.has-tooltip` span with dashed underline in Blueprint Blue, `cursor: default`
- **Surface:** Charcoal (#333333) background, white text, 6px radius, 0.6rem/0.9rem padding, 260px max-width
- **Placement:** Above the trigger, centered, 0.25s opacity fade
- **Mobile gap:** Touch devices cannot hover. Tooltips on mobile are currently inaccessible - flagged for `/impeccable harden`.

### Blog Post

Horizontal content unit for the blog index page.

- **Separation:** 1px bottom border in Hairline (#eeeeee); last item has no border
- **Timestamp:** Meta weight and Steel Muted (#888888) color, displayed as block
- **Heading:** Title level (h2) with standard spacing above

## 6. Do's and Don'ts

### Do:

- **Do** use Blueprint Blue Haze (#f0f4ff) alone to distinguish callout blocks. The tint does the full job.
- **Do** maintain the 12px / 8px radius split: 12px on containers, 8px on interactive primitives. Consistency here creates quiet visual order.
- **Do** keep body line-height at 1.7 for the long-form narrative content on this site. Dense copy needs generous leading.
- **Do** add explicit `:focus-visible` styles to every interactive element before public deployment (WCAG AA requirement).
- **Do** add `prefers-reduced-motion` guards to every transition and animation. The scroll fade-in on About Me needs this.
- **Do** implement `prefers-color-scheme: dark` token overrides before AWS launch - dark mode is a stated accessibility requirement.
- **Do** let Blueprint Blue appear in one or two structural roles per page only. If it's on the nav, keep it off decorative body elements.

### Don't:

- **Don't** use a left-side colored stripe border as a callout accent. It is a dated print convention that emphasizes the edge instead of the content. Use background tint instead.
- **Don't** use raw CSS color names (`red`, `blue`, `white`) as production values. Every color must be a named token.
- **Don't** build this to look like a generic AI-generated developer portfolio: no dark hero gradients, no glowing card borders, no animated counter stats.
- **Don't** use jarring high-contrast color combinations - no neon on dark, no highlighter yellow pairings. Any accent added to the system must coexist with Blueprint Blue without screaming.
- **Don't** add shadows to hover or active states. Color shift is the feedback signal; shadows are for resting surfaces.
- **Don't** use `#000` or `#fff` as raw values. Always reference Charcoal or Card Surface by token name.
- **Don't** introduce a second accent color without a clear semantic role distinct from Blueprint Blue. One accent, used sparingly.
- **Don't** add motion for decoration. The scroll fade-in on About Me exists to reveal sections progressively - that is purposeful. Hover sparkles, loading spinners on static content, and entrance animations on non-narrative elements are not.

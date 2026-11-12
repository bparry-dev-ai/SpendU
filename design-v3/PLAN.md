# SpendU Nova: The Cyber-Glass Tactile UI/UX Architecture Plan

> **Core Philosophy:** A bold synthesis of **Cyberpunk energy**, **Glassmorphic depth**, **Neumorphic tactility**, **Emotional design**, and **Frictionless gestures**—curated to make personal finance feel less like an anxious spreadsheet and more like an empowering, futuristic flight deck.

---

## 1. The Design System: "Cyber-Glass Tactile" (SpendU Nova)

Rather than treating aesthetic trends as superficial decoration, SpendU Nova assigns each design philosophy to a specific functional role:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        SPENDU NOVA MULTI-PARADIGM MATRIX                              │
├───────────────────────┬───────────────────────────────┬────────────────────────────────┤
│ Philosophy            │ Role in SpendU                │ Concrete UX Implementation     │
├───────────────────────┼───────────────────────────────┼────────────────────────────────┤
│ 🔮 Glassmorphism      │ Visual Hierarchy & Atmosphere │ Translucent frosted panels     │
│                       │                               │ (backdrop-filter: blur(24px)), │
│                       │                               │ 1px specular light borders,    │
│                       │                               │ floating ambient mesh glow     │
├───────────────────────┼───────────────────────────────┼────────────────────────────────┤
│ ⚡ Cyberpunk           │ High-Contrast Precision &     │ Deep void canvas (#060814),    │
│                       │ Telemetry                     │ laser emerald (#00f59b), cyber │
│                       │                               │ cyan (#00e5ff), monospace data │
│                       │                               │ (JetBrains Mono), pulse pips   │
├───────────────────────┼───────────────────────────────┼────────────────────────────────┤
│ 🔘 Neumorphism        │ Physical Tactility & Depth    │ Extruded 3D numpad keys with   │
│                       │                               │ inset depression on press;     │
│                       │                               │ recessed energy progress bars  │
├───────────────────────┼───────────────────────────────┼────────────────────────────────┤
│ 🧘 Emotional Design   │ Psychological Reassurance     │ Peace-of-mind status banner,   │
│                       │ & Anxiety Elimination         │ celebratory dopamine ripples   │
│                       │                               │ on bill completion, positive   │
│                       │                               │ safe-to-spend framing          │
├───────────────────────┼───────────────────────────────┼────────────────────────────────┤
│ 🌊 Motion &           │ Physical Realism & Story      │ Framer Motion damped harmonic  │
│   Scrollytelling      │                               │ springs (stiffness 340,        │
│                       │                               │ damping 28); chronological     │
│                       │                               │ spending narrative with burn   │
├───────────────────────┼───────────────────────────────┼────────────────────────────────┤
│ 🖐️ Buttonless UI      │ Frictionless Ergonomics       │ Velocity drag-to-dismiss,      │
│                       │                               │ desktop keyboard typing        │
│                       │                               │ (0-9, Enter, Esc), one-tap     │
│                       │                               │ inline pill confirmations      │
└───────────────────────┴───────────────────────────────┴────────────────────────────────┘
```

---

## 2. Design Tokens: Palette, Light & Dark Contrast

### Cyber Obsidian (Dark Mode)
* **Canvas Void:** `#060814` (Deep Galactic Obsidian)
* **Glass Cards:** `rgba(15, 23, 42, 0.65)` with `backdrop-filter: blur(24px) saturate(180%)`
* **Specular Borders:** `1px solid rgba(255, 255, 255, 0.12)` with light-catching top highlight
* **Laser Emerald (Safe to Spend):** `#00f59b` with subtle ambient bloom
* **Cyber Cyan (Pacing & Target):** `#00e5ff`
* **Electric Violet (Categories & Brand):** `#8b5cf6`
* **Neon Coral (Urgent Bills & Due Dates):** `#ff3366`
* **Monospace Typography:** `JetBrains Mono, tabular-nums`

### Solarpunk Glass (Light Mode)
* **Canvas:** `#f8fafc` (Ultra-clean titanium white)
* **Glass Cards:** `rgba(255, 255, 255, 0.82)` with `backdrop-filter: blur(20px)` and subtle ambient shadows
* **Specular Borders:** `1px solid rgba(203, 213, 225, 0.8)`
* **Text Headings:** `#0f172a` (High-contrast slate black, 100% WCAG AAA compliant)
* **Emerald Accent:** `#059669` (Deep, crisp emerald)
* **Cyan/Indigo Accent:** `#4f46e5`

---

## 3. Screen-by-Screen Interaction Specification

### A. Unified Retro-Cyberpunk Graphic Header (All Pages)
1. **Persistent Static Synthwave Horizon Header:**
   * A clean, static vector art header framing every view with retro-cyberpunk atmosphere while eliminating distracting animation and jargon.
   * **Sliced Digital Sun:** Classic 80s/synthwave segmented sun in radiant sunset gradient (`#ff007f` to `#ffb703`).
   * **Perspective Wireframe Grid:** Radiating neon gridlines converging on a center vanishing point with laser horizon beam.
   * **Low-Poly Polygonal Mountains:** Wireframe silhouettes with neon cyan/violet glowing ridges.
   * **Dynamic Page Branding:** Prominently displays `SPENDU / <PAGE>` (`HOME`, `ACTIVITY`, `OBLIGATIONS`, `PLANNER`) with contextual subtitle (`Good morning, Brandon`, `Last 7 Days Outflows`, etc.).
   * **Clean Utility Readouts (No Jargon):** Real-world time and date (`Wed, Nov 11, 2026 • 9:41 AM`) replacing unnecessary coordinates and jargon.

### B. Home Dashboard: "The Financial Cockpit"
1. **Weekly Safe-to-Spend Hero (Clean & Uncluttered):**
   * Big, bold weekly allowance (`$320.00 / week`).
   * **Pacing Indicator:** High-contrast `Optimal Pace` pill beacon.
   * **Emotional Peace-of-Mind Index:** Empathetic reassurance card:
     * *Pacing Optimal:* "✨ Mindset: Clear & Protected • You have $320.00 clear for guilt-free spending through Sunday."
     * *Pacing Tight:* "⚡ Pacing: Steady • $42 daily pace recommended to preserve cushion."
2. **Recessed Energy Track:**
   * Inset Neumorphic channel (`box-shadow: inset 0 2px 5px rgba(0,0,0,0.6)`) housing a radiant gradient fill showing month-to-date pacing.
3. **Category Weekly Breakdown:**
   * Frosted glass pills showing Groceries ($135/wk), Dining ($45/wk), and Fuel ($30/wk), synchronized live with the Planner.
4. **Upcoming Bills Horizon (Horizontal Carousel):**
   * High-contrast glass tiles for obligations due in the next 7 days.
   * One-tap glowing confirmation button that triggers a celebratory ripple.

### C. Activity Page: "Temporal Scrollytelling & Multi-Filters"
1. **Default Window:** Automatically loads **Last 7 Days** of transactions.
2. **Scrollytelling Feed:** Transactions are grouped into chronological story chapters:
   * *Today's Flow* (with daily burn counter)
   * *Yesterday*
   * *Earlier This Week*
3. **Multi-Dimensional Filter Hub:**
   * Instant filtering across Card, Date Range, Category, and Transaction Type.
   * Dynamic live result pill (`Showing 6 transactions • Total: $234.19`).
4. **Buttonless Row Expansion:**
   * Tap anywhere on a transaction card to smoothly expand note details, category change, or deletion—no cluttered action menus.

### D. Unified Recurring Hub: "The Obligations Ledger"
1. **Consolidated View:** All fixed bills and recurring subscriptions represented in a single unified dashboard.
2. **Live Obligation Tracker:**
   * Total monthly obligations (`$399.00 due`).
   * Paid status badge (`3 of 7 items paid so far ($239.50 settled)`).
3. **One-Tap Paid/Unpaid Toggle:**
   * Neumorphic tactile pill button. Tapping marks the bill paid, plays an affirmative micro-haptic vibration (`navigator.vibrate([12, 20])`), and fades the card into a smoked-glass settled state.
4. **Item Management:**
   * Tap "+ Add Item" to spawn a glass modal for bills or subscriptions.
   * Delete button with confirmation safeguard.

### E. The Planner: "Future-Oriented Resource Engine"
1. **Exact Income Input:** Direct numeric entry (`$5,200.00`) replacing clumsy slider bars.
2. **Unassigned Buffer Live Calculator:**
   * Automatically subtracts all category plans and displays the remaining unassigned reserve (`$450.00 left to assign`).
3. **Budget Share Distribution Bar:**
   * Multi-segmented glowing energy bar visualizing what percentage of total take-home pay each category consumes.
4. **Custom Categories & Live Sync:**
   * Add custom spending categories with personalized names and budgets.
   * Changes dynamically recalculate the weekly Safe-to-Spend allowances on the Home screen.

### F. Quick Add Bottom Sheet: "The Tactile Hyper-Pad"
1. **Framer Motion Damped Spring Engine:**
   * Velocity-tracked drag-to-dismiss gesture handle (drag down past 120px or fling to close; release halfway to bounce back).
2. **Dual-Mode Ergonomics:**
   * **Desktop Mode:** Auto-focuses the amount input; full physical keyboard capture (`0-9`, `.`, `Backspace`, `Enter` to commit, `Esc` to close).
   * **Mobile / Touch Mode:** Displays 3D Neumorphic extruded numpad buttons with physical depression on press (`box-shadow: inset ...`) and micro-haptics.
3. **One-Tap Merchant Suggestions:**
   * Smart chips (`Target`, `Starbucks`, `Amazon`, `Shell Oil`) auto-fill category and card with a single tap.

---

## 4. Implementation Path (Safe, Non-Destructive)

SpendU production files remain 100% untouched. All development and testing run inside the dedicated `design-v3/` sandbox and artifact viewer until the user is ready to merge onto a feature branch.

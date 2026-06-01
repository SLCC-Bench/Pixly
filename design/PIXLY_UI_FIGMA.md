# Pixly main window — Figma reference

Use this spec in **Figma** (or Figma Make) to mirror the in-app UI. Frame size: **1120 × 680** landscape (min 960 × 600).

## Color tokens

| Token | Hex | Usage |
|--------|-----|--------|
| bg/canvas | `#09090b` | Window background |
| bg/surface | `#131316` | Cards |
| bg/elevated | `#1a1a1f` | Inputs, chips |
| border/subtle | `#2a2a32` | Card borders |
| text/primary | `#f4f4f5` | Headings |
| text/secondary | `#a1a1aa` | Labels |
| text/muted | `#71717a` | Hints |
| accent | `#3b82f6` | Primary CTA |
| accent/hover | `#60a5fa` | Primary hover |
| danger | `#ef4444` | Stop |
| success | `#22c55e` | Idle status |
| warning | `#f59e0b` | Recording status |

## Typography

- **Display**: SF Pro / Inter 24px semibold — “Pixly”
- **Subtitle**: 13px regular — “Screen to GIF”
- **Section**: 13px semibold, letter-spacing 0.02em
- **Body**: 13px regular
- **Caption**: 11px medium, uppercase chip labels
- **Mono**: SF Mono 11px — timeline times

## Layout (landscape)

1. **Header** (~52px): logo block left, status pill right — full width  
2. **Body** (horizontal split):  
   - **Left (~65%)**: Preview card — large 16:10 preview + transport bar  
   - **Right (~35%, ~340px)**: Capture · Record & export · Quality + Audio (side by side)  
3. **Footer** (~32px): keyboard shortcuts, full width

## Components

- **Card**: 12px radius, 1px border `#2a2a32`, padding 16px  
- **Primary button**: filled accent, 40px height, 10px radius  
- **Secondary**: outline, 36px height  
- **Region chip**: elevated bg, caption + value two lines  
- **Status pill**: 20px radius, semantic fill  

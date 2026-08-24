# Dedao book page Style Guide

## 1. Color Palette

### Primary Colors
- **Brand Orange**: `#ff6b00` (Used for buttons, highlights, active states)
- **Primary Text**: `#333333` (Main content text)
- **Secondary Text**: `#666666` (Labels, secondary information)
- **Muted Text**: `#999999` (Placeholder, disabled text)

### Background Colors
- **Page Background**: `#f0f0f0` (Main app background)
- **Content Background**: `#ffffff` (Cards, panels, white sections)
- **Header/Bar Background**: `#ebecee` (Top navigation, tools)
- **Dark Bar Background**: `#17222e` (Bottom player/control bar)
- **Input/Box Background**: `#e2e3e6` (Search bars, settings boxes)

### Border Colors
- **Default Border**: `#d5d7da` (Buttons, dividers)
- **Dark Border**: `#333333` (Active or high contrast borders)

### Text on Dark Backgrounds
- **White**: `#ffffff` (Primary text on dark)
- **Light Gray**: `#d8d8d8` (Secondary text on dark)
- **Faint White**: `rgba(255, 255, 255, 0.2)` (Icons, disabled states on dark)

## 2. Typography

### Font Families
- **Primary Stack**: `-apple-system, "system-ui", "Helvetica Neue", Arial, "PingFang SC", "Hiragino Sans GB", STHeiti, "Microsoft YaHei", "Microsoft JhengHei", "Source Han Sans SC", "Noto Sans CJK SC", "Source Han Sans CN", "Noto Sans SC", "Source Han Sans TC", "Noto Sans CJK TC", SimSun, sans-serif`
- **Icon Font**: `iconfont, sans-serif, system-ui`
- **Secondary**: `"Space Grotesk", -apple-system, sans-serif`

### Font Sizes
- **Large/Icon**: `24px`
- **Heading/Title**: `20px`
- **Subheading/Highlight**: `18px`
- **Body**: `16px`, `14px`
- **Small/Label**: `12px`
- **Tiny**: `10px`

## 3. Spacing & Layout

- **Container Width**: `1405px` (Main content wrapper), `1200px` (Inner content)
- **Header Height**: `80px` (h-20)
- **Control Bar Height**: `68px`

## 4. UI Elements

### Buttons
- **Primary Button**: `bg-[#ff6b00] text-white rounded-br-[38px] rounded-t-[38px] rounded-bl-[38px]` (Pill shape with unique rounding)
- **Secondary Button**: `bg-[#f5f3f1] text-[#333333] rounded-br-[38px] rounded-t-[38px] rounded-bl-[38px]`
- **Icon Button**: Transparent background, text color `#666666` or `#333333`, hover color `#ff6b00` or `#333333`.

### Cards & Containers
- **Rounded Corners**:
    - **Small**: `2px`, `4px`
    - **Medium**: `6px`, `8px`
    - **Large**: `12px`, `16px`, `20px`
    - **Pill/Circle**: `38px` (Buttons)
- **Shadows**:
    - `shadow-[rgba(0,0,0,0.15)_0px_2px_30px_0px]`
    - `shadow-[rgba(0,0,0,0.05)_0px_2px_10px_0px]`
    - `shadow-[rgba(0,0,0,0.1)_0px_-2px_12px_0px]` (Bottom sheet)

### Interactive Elements
- **Hover Effects**: Change text color to `#ff6b00` or `#333333`.
- **Focus States**: `focus:outline-none`.

## 5. CSS Classes Pattern
- Tailwind CSS with arbitrary values (`w-[1405px]`, `bg-[#ff6b00]`) is heavily used.
- Caret color is consistently set to `caret-[#333333]` or `caret-white`.
- `select-none` is applied to most UI elements to prevent text selection.

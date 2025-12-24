得到 (dedao.cn) Style Guide
🎨 Brand Overview
dedao.cn (得到) is a Chinese knowledge learning platform with a clean, professional, and content-focused design aesthetic. The platform emphasizes readability, accessibility, and a warm yet authoritative brand presence.

1. Color Palette
Primary Colors
Brand Orange: #ff6b00

Primary CTA buttons, active states, highlights
Conveys energy, learning, and action
Deep Black: #333333

Body text, headings, primary content
High contrast for readability
Secondary Colors
White: #ffffff / rgba(255,255,255,0.92) (with transparency)

Backgrounds, cards, modal overlays
Neutral Gray: #f9f9f9, #f0f0f0, #f5f3f1, #f7f7f7

Input backgrounds, dividers, subtle backgrounds
Light Gray: #d8d8d8

Disabled states, subtle UI elements
Dark Gray: #999999

Secondary text, placeholders, subtle labels
Background Tones
Neutral Background: rgb(245, 245, 245) / neutral-50

Section backgrounds for visual separation
Dark Mode Accent: #17222e

Fixed floating elements, bottom bars
Semantic Colors
Shadow/Overlay: rgba(0,0,0,0.5), rgba(0,0,0,0.1), rgba(0,0,0,0.06)
Labels, overlays, depth effects

2. Typography
Font Stack
Primary: -apple-system, "system-ui", "Helvetica Neue", Arial, 
         "PingFang SC", "Hiragino Sans GB", STHeiti, 
         "Microsoft YaHei", "Microsoft JhengHei", 
         "Source Han Sans SC", "Noto Sans CJK SC", 
         "Source Han Sans CN", "Noto Sans SC", 
         "Source Han Sans TC", "Noto Sans CJK TC", 
         SimSun, sans-serif

Icon Font: iconfont, sans-serif
Type Scale
H1 Logo: 16px (subtle, reserved)
H2 Navigation: 26px / font-weight: 400-500 / line-height: 34px
H5 Modal Headers: 16px / line-height: 26px
Body/Buttons: 14px, 16px / line-height: 34px, 16px
Small Labels: 12px / line-height: 12px
Icon Text: 18px
Font Weights
Normal: 400 (default body text, navigation)
Medium: 500 (active states, emphasis)
Semibold: 600 (tab selections)
Bold: 700 (CTA buttons)

3. Spacing System
Padding Scale
Micro: px-1 (4px), py-[3px] (3px)
Small: px-2.5 (10px), py-2 (8px)
Medium: px-3 (12px), px-4 (16px), py-3 (12px)
Large: px-5 (20px), py-6 (24px)
XL: px-[30px] (30px), py-10 (40px)
Margin Scale
Vertical Rhythm: mb-5 (20px), mt-2.5 (10px), my-0
Horizontal Spacing: mr-[46px] (46px - navigation items), mr-8 (32px)
Negative Space: mr-[-10px], ml-[-10px] (grid compensation)
Container Widths
Max Content Width: 1200px, 1260px
Card Grid: w-1/3 (3-column layout)
Modal Width: 340px
Search Bar: 88px (button), 90% (input)

4. Border Radius
Radius Scale
Subtle: rounded-[3px] (small labels)
Small: rounded-[4px] (hover states, tabs)
Medium: rounded-[6px] (cards, inputs, images)
Large: rounded-[10px] (floating buttons)
XL: rounded-[12px] (bottom bars)
Modal: rounded-[20px]
Pills: rounded-[30px], rounded-[38px] (buttons)
Custom Notation
Uses Tailwind's rounded-br-[Xpx] rounded-t-[Xpx] rounded-bl-[Xpx] pattern (top-left, top-right, bottom-right, bottom-left excluding one corner for visual interest)

5. Shadows & Depth
Shadow Stack
Subtle Lift: drop-shadow(rgba(0,0,0,0.06) 0px 1px 10px)
Card Elevation: shadow-[rgba(0,0,0,0.05) 0px 2px 10px 0px]
Modal/Overlay: shadow-[rgba(0,0,0,0.1) 0px -2px 12px 0px]
Button Depth: shadow-[rgba(0,0,0,0.1) 0px 1px 3px 0px]
Z-Index Layers
Content: base layer
Sticky Navigation: z-[3000]
Sidebar: z-[1000]
Modal Overlay: z-[3000]
Modal Content: z-[4000]
Bottom Sheet: z-[10000]

6. Component Patterns
Buttons
Primary CTA

bg-[#ff6b00] text-white 
font-bold text-[14px] 
h-[38px] w-full
rounded-[38px]
Secondary Button

bg-[#f5f3f1] 
font-bold text-[14px]
h-[38px] w-full
rounded-[38px]
Icon Button (Floating)

bg-[#d8d8d8] w-[30px] h-[30px]
rounded-[30px]
hover:bg-[#ff6b00]
Cards
Content Card

bg-white 
h-[136px] max-h-[136px]
padding: 12px 16px 12px 12px
rounded-[6px]
display: flex
Card Image

w-[84px] h-[112px] min-w-[84px]
rounded-[6px]
border: 0.5px solid rgba(0,0,0,0.1)
Input Fields
Search Bar

bg-[#f9f9f9]
h-[40px]
rounded-[6px]
border: 1px solid #f0f0f0
font-size: 16px
Navigation
Fixed Header

bg-[rgba(255,255,255,0.92)]
height: 64px
max-width: 1200px
position: fixed
z-index: 3000
backdrop-blur: 20px
Tab Navigation

Active: text-[#ff6b00] font-medium
Inactive: text-[#333333] font-normal
font-size: 26px
line-height: 34px
margin-right: 46px
border-bottom: 1px solid #f0f0f0
Labels/Badges
Category Label

bg-[rgba(0,0,0,0.5)]
text-white
font-medium text-[12px]
line-height: 12px
padding: 3px 4px
rounded-[3px]
position: absolute (bottom-right)

7. Layout Principles
Grid System
3-column grid: w-1/3 float-left with padding-x: 10px
Negative margin compensation: -10px on container
Max container: 1200px centered with mx-auto
Spacing Philosophy
Generous whitespace around content sections (pt-16, pb-10)
Consistent vertical rhythm with mb-5 between cards
Horizontal padding: px-5 on mobile-friendly containers

8. Interactive States
Hover Effects
hover:bg-[#f7f7f7] (subtle background)
hover:bg-[#ff6b00] (icon buttons to brand color)
Active States
Active Tab: Orange text (#ff6b00) + medium font weight
Focus: Maintains accessibility with high contrast
Transitions
Smooth transforms: translate-x, translate-y
Opacity changes for show/hide
Backdrop blur for glassmorphism effect

9. Accessibility Features
High Contrast Text: #333333 on white backgrounds
Readable Font Size: Minimum 12px, body at 14-16px
Touch Targets: Minimum 30px × 30px for buttons
Semantic HTML: Proper use of <button>, <input>, headings
Caret Color: Matches text color for consistency

10. Unique Design Elements
Glassmorphism Header
Semi-transparent white background (rgba(255,255,255,0.92))
Backdrop blur effect (backdrop-blur-[20px])
Drop shadow for depth
Corner-Cut Rounded Corners
Custom radius pattern excluding one corner
Example: rounded-br-[6px] rounded-t-[6px] rounded-bl-[6px]
Creates subtle visual interest
Floating Action Sidebar
Fixed position: left-[calc(50% + 620px)]
"Back to top" button with icon
Sticky but non-intrusive

11. Design Philosophy
Core Principles
Content-First: Clean layouts that prioritize readability
Warm Minimalism: Generous whitespace with warm accent color
Trust & Authority: Professional typography and structured layouts
Accessible Learning: High contrast, clear hierarchy
Chinese-First Design: Optimized font stacks for Chinese characters

Visual Tone
Professional yet approachable
Educational and trustworthy
Modern without being trendy
Emphasis on clarity over decoration
12. Implementation Notes
Technology Stack
Framework: React (component-based architecture)
Styling: Tailwind CSS with custom values
Icons: Custom icon font (iconfont)
Images: CDN-hosted with OSS processing

Best Practices
Use semantic component naming
Maintain consistent spacing tokens
Leverage Tailwind utilities for consistency
Optimize images with CDN parameters
Consider mobile-first responsive patterns
To use this brand in a new project:


# Dashboard card design baseline (2026)

The bundled GWM RU cards intentionally follow the strongest current Home Assistant UI patterns instead of inventing a separate visual language.

## References used

1. **Home Assistant Tile card / Sections dashboard**
   - Native Home Assistant theme variables and surfaces.
   - Responsive Sections-compatible sizing.
   - Clear hierarchy, restrained decoration, state-driven color.
   - https://www.home-assistant.io/dashboards/tile/
   - https://www.home-assistant.io/dashboards/cards/

2. **Bubble Card**
   - 56 px primary rows.
   - Pill geometry with radius equal to half the row height.
   - 36 px compact/sub controls.
   - Compact state-driven surfaces instead of heavy shadows.
   - https://github.com/Clooos/Bubble-Card

3. **Mushroom**
   - Compact typography: 14 px primary / 12 px secondary.
   - Medium primary weight and regular secondary weight.
   - 36 px chips with approximately half-height radius.
   - https://github.com/piitaya/lovelace-mushroom

## Rules for GWM RU

- No glassmorphism, neon, decorative gradients, fake automotive chrome, or custom brand palette.
- Use Home Assistant CSS variables so the cards inherit the active theme.
- Remote controls use the same 56 px pill pattern as current Bubble/Tile-style controls.
- Statuses and secondary actions use 36 px chips/sub-controls.
- Primary copy is 14 px / 500; secondary copy is 12 px / 400.
- Semantic colors are limited to Home Assistant primary, warning, error, and success variables.
- The animated vehicle illustration remains functional, but the surrounding UI uses the same native/Bubble/Mushroom design system as the primary card.
- Mobile layouts remain two-column where readable and collapse to one column only at narrow widths.
- No external frontend card dependency is introduced.

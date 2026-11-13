# Visual design

## The price-range bar

One hospital, one service, one shared horizontal price axis:

| Mark | Encodes | Color | Shape |
|---|---|---|---|
| band | range of insurer-negotiated rates (de-identified min–max) | insurer blue at ~16% opacity | rounded bar |
| ticks | each insurer/plan's rate | insurer blue | 2px vertical line |
| selected insurer | that insurer's plans | insurer blue, filled | 4.5px dot with a 2px surface ring |
| diamond | discounted cash price | cash orange | diamond with a 2px surface ring |
| ring | gross "list" price | neutral gray | hollow circle; a chevron when off the scale |

Identity is carried by **shape and color together**, so the bars still read
in grayscale, for color-vision deficiencies and in forced-colors mode (where
the colors map to system colors). The axis is shared by every row in a list
and ends near the 95th percentile of the highest prices shown, so one
outlier can't compress everyone else; values beyond the axis are clamped and
flagged.

## Color

Only two categorical hues are used, and only for identity:

| Role | Light theme | Dark theme |
|---|---|---|
| Insurer rates | `#2a78d6` | `#3987e5` |
| Cash price | `#eb6834` | `#d95926` |
| Chart surface | `#fcfcfb` | `#1a1a19` |

Both pairs were validated (not eyeballed) for lightness band, chroma floor,
color-vision-deficiency separation, normal-vision separation and ≥ 3:1
contrast against the chart surface, in each theme:

| Check | Light | Dark |
|---|---|---|
| CVD ΔE (worst, protan) | 24.7 | 26.8 |
| Normal-vision ΔE | 33.6 | 31.8 |
| Contrast vs surface | ≥ 3:1 | ≥ 3:1 |

The map shows **magnitude**, so it uses a one-hue sequential ramp in the hue
of the entity being mapped: orange when coloring by cash price, blue when
coloring by an insurer's rate. Light theme ramps run light→dark; dark theme
ramps run dark→light so "more" always means "more contrast with the
surface". The ramp domain is the 5th–95th percentile of the values shown.

Status colors (good / warning / critical) are reserved for the file-quality
checklist and always come with an icon and a text label.

## Typography

System UI fonts only (no web fonts, which would be a third-party request).
Tabular figures are used where numbers align in columns (axes, tables).

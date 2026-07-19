# Behavior Sensitivity Personalization Policy

## Purpose

Roady stores behavior-specific warning sensitivity as numeric values from 3 to 10. Manual profile editing may set any valid value in that range, but automatic personalization should update values gradually so one drive summary does not abruptly change the next drive's warning behavior.

## Gradual Update Formula

For each behavior type, apply only a portion of the gap between the current value and the AI-recommended value:

```text
S_next = clamp(S_current + round((S_recommended - S_current) * alpha), 3, 10)
```

- `S_current`: current behavior warning sensitivity.
- `S_recommended`: recommended sensitivity from the personalization analysis.
- `alpha`: update reflection rate. Start with `0.3` for demo and product explanation.
- `clamp(value, 3, 10)`: keeps the result inside the existing backend sensitivity range.

If `S_recommended` differs from `S_current` but rounding produces `0`, move one step toward the recommendation:

```text
delta = round((S_recommended - S_current) * alpha)
if delta == 0 and S_recommended != S_current:
    delta = 1 when S_recommended > S_current else -1
S_next = clamp(S_current + delta, 3, 10)
```

## Example

```text
S_current = 9
S_recommended = 4
alpha = 0.3

delta = round((4 - 9) * 0.3) = round(-1.5) = -2
S_next = clamp(9 - 2, 3, 10) = 7
```

Roady follows the recommended direction, but does not immediately drop from `9` to `4`.

## Presentation Message

Roady does not apply AI personalization recommendations directly. It compares the current driver profile with the recommended value and reflects only a controlled portion of the difference. This keeps personalization responsive while preventing temporary drive results from changing warning sensitivity too aggressively.

"""Checks (and gently repairs) pet JSON before it's ever drawn.

Everything an LLM returns goes through here. Small, unambiguous slips are
fixed and noted (a row one character short, a missing "#" on a colour, a few
too many lines). Anything else becomes an error message precise enough to
send back to the model for a retry.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .spec import ANIMATIONS, LINES, MAX_LINE_LENGTH, NESTED_LINES, Accessory, PetSpec
from .sprites import GRID, TRANSPARENT

MAX_COLORS = 15
MIN_OPAQUE = 60  # pixels; anything less is a blank or broken frame
MAX_NAME = 24
MAX_PERSONALITY = 240
MAX_ERRORS = 30
SLACK = 2  # rows/columns we'll pad or trim without calling it an error
MAX_ACCESSORY = 16  # an accessory sprite is at most this many pixels each way

_HEX = re.compile(r"^#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$")


@dataclass
class Validation:
    spec: PetSpec | None = None
    lines: dict[str, Any] | None = None
    errors: list[str] = field(default_factory=list)
    fixes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and (self.spec is not None or self.lines is not None)


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "pet"


def validate_pet(data: Any, pet_id: str | None = None) -> Validation:
    v = Validation()
    if not isinstance(data, dict):
        v.errors.append("The response must be a single JSON object.")
        return v

    name = _text(data.get("name"), "name", MAX_NAME, v)
    personality = _text(data.get("personality"), "personality", MAX_PERSONALITY, v)
    palette = _palette(data.get("palette"), v)
    frames = _frames(data.get("frames"), palette, v) if palette is not None else None
    lines = _lines(data.get("lines"), v)
    # Optional extras: older pets (and generated ones) simply don't have them.
    anchors = _anchors(data.get("anchors"), v)
    accessories = _accessories(data.get("accessories"), anchors, palette or {}, v)
    blurb = _text(data["blurb"], "blurb", MAX_LINE_LENGTH, v) if data.get("blurb") else ""

    if v.errors or name is None or palette is None or frames is None or lines is None:
        v.errors = v.errors[:MAX_ERRORS]
        return v
    v.lines = lines
    v.spec = PetSpec(
        id=pet_id or slugify(name),
        name=name,
        personality=personality or "",
        palette=palette,
        frames=frames,
        lines=lines,
        description=str(data.get("description", "")),
        model=str(data.get("model", "")),
        blurb=blurb or "",
        anchors=anchors,
        accessories=accessories,
    )
    return v


def validate_lines(data: Any) -> Validation:
    """Validate just the "lines" object (used when regenerating a pet's text only)."""
    v = Validation()
    if isinstance(data, dict) and "lines" in data:
        data = data["lines"]
    lines = _lines(data, v)
    v.errors = v.errors[:MAX_ERRORS]
    if not v.errors:
        v.lines = lines
    return v


# ---- fields -------------------------------------------------------------


def _text(value: Any, key: str, limit: int, v: Validation) -> str | None:
    if not isinstance(value, str) or not value.strip():
        v.errors.append(f'"{key}" must be a non-empty string.')
        return None
    text = " ".join(value.split())
    if len(text) > limit:
        v.fixes.append(f"trimmed {key} to {limit} characters")
        text = text[:limit].rstrip()
    return text


def _palette(value: Any, v: Validation) -> dict[str, str] | None:
    if not isinstance(value, dict) or not value:
        v.errors.append('"palette" must be an object mapping single characters to "#rrggbb" colours.')
        return None
    palette: dict[str, str] = {}
    for key, color in value.items():
        if not isinstance(key, str) or len(key) != 1 or key == TRANSPARENT or key.isspace():
            v.errors.append(f'palette key {key!r} must be one character other than "{TRANSPARENT}".')
            continue
        m = _HEX.match(color) if isinstance(color, str) else None
        if not m:
            v.errors.append(f'palette["{key}"] = {color!r} is not a colour like "#e8833a".')
            continue
        hexpart = m.group(1)
        if len(hexpart) == 3:
            hexpart = "".join(c * 2 for c in hexpart)
        normalized = "#" + hexpart.lower()
        if normalized != color:
            v.fixes.append(f'normalized palette["{key}"] to {normalized}')
        palette[key] = normalized
    if len(palette) > MAX_COLORS:
        v.errors.append(f"palette has {len(palette)} colours; use at most {MAX_COLORS}.")
    if len(palette) < 2 and not v.errors:
        v.errors.append("palette needs at least 2 colours.")
    return palette


def _frames(value: Any, palette: dict[str, str], v: Validation) -> dict[str, tuple] | None:
    if not isinstance(value, dict):
        v.errors.append('"frames" must be an object with one array of frames per animation.')
        return None
    allowed = set(palette) | {TRANSPARENT}
    frames: dict[str, tuple] = {}
    for name, count in ANIMATIONS.items():
        raw = value.get(name)
        if not isinstance(raw, list) or not raw:
            v.errors.append(f'frames.{name} is missing; it needs exactly {count} frame(s).')
            continue
        if len(raw) > count:
            v.fixes.append(f"dropped {len(raw) - count} extra frame(s) from {name}")
            raw = raw[:count]
        if len(raw) < count:
            v.errors.append(f"frames.{name} has {len(raw)} frame(s); it needs exactly {count}.")
            continue
        parsed = [_frame(f, f"frames.{name}[{i}]", allowed, palette, v) for i, f in enumerate(raw)]
        if any(f is None for f in parsed):
            continue
        if count > 1 and len(set(parsed)) == 1:
            v.errors.append(f"all {count} frames of {name} are identical; each frame must differ to animate.")
            continue
        frames[name] = tuple(parsed)
    extra = sorted(set(value) - set(ANIMATIONS))
    if extra:
        v.fixes.append(f"ignored unknown animations: {', '.join(extra)}")
    return frames if len(frames) == len(ANIMATIONS) else None


def _frame(raw: Any, where: str, allowed: set[str], palette: dict[str, str], v: Validation) -> tuple | None:
    if isinstance(raw, str):
        raw = raw.splitlines()
        v.fixes.append(f"split {where} from one string into rows")
    if not isinstance(raw, list) or not all(isinstance(r, str) for r in raw):
        v.errors.append(f"{where} must be an array of {GRID} strings.")
        return None
    rows = [r.strip() for r in raw]
    if " " not in palette:
        if any(" " in r for r in rows):
            v.fixes.append(f"treated spaces in {where} as transparent")
        rows = [r.replace(" ", TRANSPARENT) for r in rows]

    # Rows: pad or trim a couple of empty rows, otherwise it's an error.
    if len(rows) != GRID:
        diff = len(rows) - GRID
        if abs(diff) > SLACK:
            v.errors.append(f"{where} has {len(rows)} rows; it needs exactly {GRID}.")
            return None
        if diff < 0:
            rows = [TRANSPARENT * GRID] * -diff + rows
        else:
            for _ in range(diff):
                if not rows[0].strip(TRANSPARENT):
                    rows.pop(0)
                elif not rows[-1].strip(TRANSPARENT):
                    rows.pop()
                else:
                    v.errors.append(f"{where} has {len(rows)} rows; it needs exactly {GRID}.")
                    return None
        v.fixes.append(f"adjusted {where} to {GRID} rows")

    fixed_rows = []
    for r, row in enumerate(rows):
        if len(row) != GRID:
            diff = len(row) - GRID
            if abs(diff) > SLACK or (diff > 0 and row[GRID:].strip(TRANSPARENT)):
                v.errors.append(f"{where} row {r} has {len(row)} characters; every row needs exactly {GRID}.")
                return None
            row = row[:GRID] if diff > 0 else row + TRANSPARENT * -diff
            v.fixes.append(f"padded/trimmed {where} row {r} to {GRID} characters")
        bad = sorted(set(row) - allowed)
        if bad:
            v.errors.append(
                f"{where} row {r} uses {''.join(bad)!r}, which is not in the palette "
                f'(use only {"".join(sorted(palette))} or "{TRANSPARENT}").'
            )
            return None
        fixed_rows.append(row)

    opaque = sum(len(row) - row.count(TRANSPARENT) for row in fixed_rows)
    if opaque < MIN_OPAQUE:
        v.errors.append(f"{where} only has {opaque} coloured pixels; draw the whole character (at least {MIN_OPAQUE}).")
        return None
    return tuple(fixed_rows)


def _anchors(value: Any, v: Validation) -> dict[str, dict[str, tuple]]:
    """Named points per frame, e.g. where the eyes are, for accessories to sit on."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        v.errors.append('"anchors" must map anchor names to per-animation point lists.')
        return {}
    out: dict[str, dict[str, tuple]] = {}
    for name, table in value.items():
        if not isinstance(table, dict):
            v.errors.append(f"anchors.{name} must map every animation to a list of points.")
            continue
        parsed: dict[str, tuple] = {}
        for anim, count in ANIMATIONS.items():
            points = table.get(anim)
            if not isinstance(points, list) or len(points) != count:
                v.errors.append(f"anchors.{name}.{anim} needs exactly {count} point(s), one per frame (null to skip a frame).")
                continue
            row = []
            for i, pt in enumerate(points):
                if pt is None:
                    row.append(None)
                elif (
                    isinstance(pt, list)
                    and len(pt) == 2
                    and all(isinstance(c, int) and not isinstance(c, bool) for c in pt)
                    and all(-MAX_ACCESSORY < c < GRID for c in pt)
                ):
                    row.append((pt[0], pt[1]))
                else:
                    v.errors.append(f"anchors.{name}.{anim}[{i}] must be [x, y] grid coordinates or null.")
                    row.append(None)
            parsed[anim] = tuple(row)
        out[name] = parsed
    return out


def _accessories(value: Any, anchors: dict, palette: dict[str, str], v: Validation) -> dict[str, Accessory]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        v.errors.append('"accessories" must map names to {label, anchor, default, sprite}.')
        return {}
    allowed = set(palette) | {TRANSPARENT}
    out: dict[str, Accessory] = {}
    for name, acc in value.items():
        where = f"accessories.{name}"
        if not isinstance(acc, dict):
            v.errors.append(f"{where} must be an object.")
            continue
        anchor = acc.get("anchor")
        if anchor not in anchors:
            v.errors.append(f"{where}.anchor {anchor!r} isn't one of the pet's anchors.")
            continue
        sprite = acc.get("sprite")
        if (
            not isinstance(sprite, list)
            or not 1 <= len(sprite) <= MAX_ACCESSORY
            or not all(isinstance(r, str) and 1 <= len(r) <= MAX_ACCESSORY for r in sprite)
        ):
            v.errors.append(f"{where}.sprite must be 1-{MAX_ACCESSORY} rows of at most {MAX_ACCESSORY} characters.")
            continue
        bad = sorted(set("".join(sprite)) - allowed)
        if bad:
            v.errors.append(f"{where}.sprite uses {''.join(bad)!r}, which is not in the palette.")
            continue
        label = acc.get("label", name)
        out[name] = Accessory(
            name=name,
            label=str(label)[:20],
            anchor=anchor,
            sprite=tuple(sprite),
            default=bool(acc.get("default", True)),
        )
    return out


def _lines(value: Any, v: Validation) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        v.errors.append('"lines" must be an object of line arrays.')
        return None
    out: dict[str, Any] = {}
    for key, (lo, hi) in LINES.items():
        out[key] = _line_list(value.get(key), f"lines.{key}", lo, hi, v)
    for group, spec in NESTED_LINES.items():
        node = value.get(group)
        if not isinstance(node, dict):
            v.errors.append(f"lines.{group} must be an object with {', '.join(spec)}.")
            continue
        out[group] = {k: _line_list(node.get(k), f"lines.{group}.{k}", lo, hi, v) for k, (lo, hi) in spec.items()}
    return out


def _line_list(value: Any, where: str, lo: int, hi: int, v: Validation) -> list[str]:
    if not isinstance(value, list):
        v.errors.append(f"{where} must be an array of {lo}-{hi} short strings.")
        return []
    seen: set[str] = set()
    clean: list[str] = []
    too_long = 0
    for item in value:
        if not isinstance(item, str):
            continue
        line = " ".join(item.split()).strip().strip('"').strip()
        if not line or line.lower() in seen:
            continue
        if len(line) > MAX_LINE_LENGTH:
            too_long += 1
            continue
        seen.add(line.lower())
        clean.append(line)
    if too_long:
        if len(clean) >= lo:
            v.fixes.append(f"dropped {too_long} line(s) over {MAX_LINE_LENGTH} characters from {where}")
        else:
            v.errors.append(f"{where} has {too_long} line(s) longer than {MAX_LINE_LENGTH} characters; keep every line short.")
            return clean
    if len(clean) > hi:
        v.fixes.append(f"kept the first {hi} of {len(clean)} lines in {where}")
        clean = clean[:hi]
    if len(clean) < lo:
        v.errors.append(f"{where} has {len(clean)} usable line(s); it needs {lo}-{hi} distinct ones.")
    return clean

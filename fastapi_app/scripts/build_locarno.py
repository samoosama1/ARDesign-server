"""
Build Locarno classification seed data from the Turkish XLS.

Emits fastapi_app/app/data/locarno_seed.json — a compact JSON snapshot consumed
by the alembic migration that populates locarno_main_class + locarno_subclass.

Run once whenever WIPO publishes a new Locarno edition / Turkpatent updates the
XLS, then write a new migration that diffs against the previous seed:

    python scripts/build_locarno.py

Source spreadsheet structure:
  col A: "SINIF N" or "NN-NN" subclass code
  col B: Turkish product name (or ALL-CAPS subclass summary header — ignored)
  col C: WIPO indicator ID No
  col D: English product name (only on individual product rows)
  col E: French (ignored)
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import xlrd

# ---------- Paths ----------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
XLS_PATH = REPO_ROOT / "Locarno Sınıfları (2022).xls"
SEED_OUT = REPO_ROOT / "fastapi_app" / "app" / "data" / "locarno_seed.json"

# ---------- Official WIPO English main-class titles (Locarno 14th ed.) ------
# The XLS has no English for main-class header rows; sourced from WIPO.

MAIN_CLASS_TITLES: dict[int, str] = {
    1: "Foodstuffs",
    2: "Articles of clothing and haberdashery",
    3: "Travel goods, cases, parasols and personal belongings, not elsewhere specified",
    4: "Brushware",
    5: "Textile piecegoods, artificial and natural sheet material",
    6: "Furnishing",
    7: "Household goods, not elsewhere specified",
    8: "Tools and hardware",
    9: "Packages and containers for the transport or handling of goods",
    10: "Clocks and watches and other measuring instruments, checking and signalling instruments",
    11: "Articles of adornment",
    12: "Means of transport or hoisting",
    13: "Equipment for production, distribution or transformation of electricity",
    14: "Recording, telecommunication or data processing equipment",
    15: "Machines, not elsewhere specified",
    16: "Photographic, cinematographic and optical apparatus",
    17: "Musical instruments",
    18: "Printing and office machinery",
    19: "Stationery and office equipment, artists' and teaching materials",
    20: "Sales and advertising equipment, signs",
    21: "Games, toys, tents and sports goods",
    22: "Arms, pyrotechnic articles, articles for hunting, fishing and pest killing",
    23: "Fluid distribution equipment, sanitary, heating, ventilation and air-conditioning equipment, solid fuel",
    24: "Medical and laboratory equipment",
    25: "Building units and construction elements",
    26: "Lighting apparatus",
    27: "Tobacco and smokers' supplies",
    28: "Pharmaceutical and cosmetic products, toilet articles and apparatus",
    29: "Devices and equipment against fire hazards, for accident prevention and for rescue",
    30: "Articles for the care and handling of animals",
    31: "Machines and appliances for preparing food or drink, not elsewhere specified",
    32: "Graphic symbols and logos, surface patterns, ornamentation",
}

# ---------- Parsers --------------------------------------------------------

CLASS_PAT = re.compile(r"^SINIF\s+(\d+)$", re.IGNORECASE)
SUB_PAT = re.compile(r"^(\d{2})-(\d{2})$")
BRACKET_PAT = re.compile(r"\[([^\]]+)\]")


def asciify(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


def slugify(s: str) -> str:
    s = asciify(s)
    s = re.sub(r"[^A-Za-z0-9]+", "_", s)
    return re.sub(r"_+", "_", s).strip("_").upper()


def split_name(name: str) -> tuple[str, list[str]]:
    """Split 'Sorbets [ices]' -> ('Sorbets', ['ices'])."""
    brackets = BRACKET_PAT.findall(name)
    base = BRACKET_PAT.sub("", name).strip()
    return base, brackets


def build_identifier(english_rows: list[str]) -> str:
    """
    Concatenate names + bracket contents per spec:
      ['Sorbets [ices]', 'Sherbets [ices]'] -> 'SORBETS_SHERBETS_ICES'
      ['Biscuits', 'Cookies']               -> 'BISCUITS_COOKIES'
      ['Caramels [candy]']                  -> 'CARAMELS_CANDY'
    """
    bases: list[str] = []
    brackets: list[str] = []
    for row in english_rows:
        base, brs = split_name(row)
        if base:
            bases.append(base)
        brackets.extend(brs)

    def dedup_slug(items: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for it in items:
            slug = slugify(it)
            if slug and slug not in seen:
                seen.add(slug)
                out.append(slug)
        return out

    parts = dedup_slug(bases) + dedup_slug(brackets)
    name = "_".join(parts)
    # Identifiers can't start with a digit if we ever map them back to Python
    # symbols (e.g. "3D printers" -> "3D_PRINTERS"). Cheap to fix once here.
    if name and name[0].isdigit():
        name = "_" + name
    return name


def build_label(english_rows: list[str]) -> str:
    return ", ".join(english_rows)


def parse_xls() -> tuple[dict, dict]:
    """Returns (groups, order) — see build_dataset for shape."""
    if not XLS_PATH.exists():
        raise FileNotFoundError(f"Source XLS not found: {XLS_PATH}")

    wb = xlrd.open_workbook(str(XLS_PATH))
    ws = wb.sheets()[0]

    groups: dict[int, dict[int, list[str]]] = defaultdict(lambda: defaultdict(list))
    order: dict[int, list[int]] = defaultdict(list)
    current_main: int | None = None

    for r in range(ws.nrows):
        code = str(ws.cell_value(r, 0)).strip()
        cm = CLASS_PAT.match(code)
        if cm:
            current_main = int(cm.group(1))
            continue
        if not SUB_PAT.match(code) or current_main is None:
            continue
        id_no = ws.cell_value(r, 2)
        en = ws.cell_value(r, 3)
        if not id_no or not isinstance(en, str) or not en.strip():
            continue
        id_int = int(id_no)
        en = en.strip()
        if id_int not in groups[current_main]:
            order[current_main].append(id_int)
        groups[current_main][id_int].append(en)

    return groups, order


def build_dataset() -> dict:
    """Returns the seed payload: list[main_class] + list[subclass]."""
    groups, order = parse_xls()

    main_classes = []
    subclasses = []
    used_values: set[str] = set()

    for mc in sorted(MAIN_CLASS_TITLES):
        main_value = f"SINIF_{mc}"
        main_classes.append({
            "value": main_value,
            "number": mc,
            "label": MAIN_CLASS_TITLES[mc],
            "sort_index": mc,
        })

        sub_sort = 0
        for id_no in order.get(mc, []):
            english_rows = groups[mc][id_no]
            ident = build_identifier(english_rows) or f"UNNAMED_{id_no}"
            # Disambiguate against earlier collisions.
            original = ident
            suffix = 2
            while ident in used_values:
                ident = f"{original}_{suffix}"
                suffix += 1
            used_values.add(ident)

            subclasses.append({
                "value": ident,
                "main_class_value": main_value,
                "label": build_label(english_rows),
                "locarno_id": id_no,
                "sort_index": sub_sort,
            })
            sub_sort += 1

        # Synthetic catch-all per main class.
        misc = f"MISCELLANEOUS_CLASS_{mc}"
        used_values.add(misc)
        subclasses.append({
            "value": misc,
            "main_class_value": main_value,
            "label": "Miscellaneous",
            "locarno_id": None,
            "sort_index": sub_sort,
        })

    return {"main_classes": main_classes, "subclasses": subclasses}


def _emit_compact(dataset: dict) -> str:
    """One record per line so PR diffs across Locarno editions stay readable."""
    def line(obj: dict) -> str:
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))

    parts = ['{\n  "main_classes": [\n']
    parts.append(",\n".join(f"    {line(m)}" for m in dataset["main_classes"]))
    parts.append('\n  ],\n  "subclasses": [\n')
    parts.append(",\n".join(f"    {line(s)}" for s in dataset["subclasses"]))
    parts.append("\n  ]\n}\n")
    return "".join(parts)


def main() -> None:
    dataset = build_dataset()
    SEED_OUT.parent.mkdir(parents=True, exist_ok=True)
    SEED_OUT.write_text(_emit_compact(dataset), encoding="utf-8")
    print(
        f"Wrote {SEED_OUT.relative_to(REPO_ROOT)}: "
        f"{len(dataset['main_classes'])} main classes, "
        f"{len(dataset['subclasses'])} subclasses"
    )


if __name__ == "__main__":
    main()

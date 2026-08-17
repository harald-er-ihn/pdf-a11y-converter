# src/infrastructure/pdf/tag_extractor.py
# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Extraktion vorhandener PDF-Tags aus dem Eingangs-PDF.

Dieser Core liest den /StructTreeRoot eines PDFs, falls vorhanden, und erzeugt
ein neutrales JSON-Artefakt. Die vorhandenen Tags sind nur eine Signalquelle
für spätere Rekonstruktion und werden nicht blind übernommen.

Extrahiert werden u.a.:
- /RoleMap
- Struktur-Elemente mit /S
- /Alt
- /ActualText
- /Lang
- /Title
- Kindstruktur über /K
- MCID-/MCR-/OBJR-Hinweise, soweit mit pikepdf sicher zugänglich

Direkt testbar mit:

    python -m src.infrastructure.pdf.tag_extractor input.pdf output.json
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import pikepdf

logger = logging.getLogger("pdf-converter")


MAX_DEPTH = 80


def _pdf_name_to_str(value: Any) -> str | None:
    """Konvertiert PDF-Namen/String-artige Werte robust nach str."""
    if value is None:
        return None
    try:
        text = str(value)
    except Exception:  # pylint: disable=broad-exception-caught
        return None

    if text.startswith("/"):
        text = text[1:]
    return text


def _pdf_text_to_str(value: Any) -> str | None:
    """Konvertiert PDF-Textwerte robust nach str."""
    if value is None:
        return None
    try:
        text = str(value)
    except Exception:  # pylint: disable=broad-exception-caught
        return None

    return text


def _object_ref(value: Any) -> str | None:
    """Gibt eine stabile indirekte Objekt-Referenz zurück, falls vorhanden."""
    try:
        objgen = getattr(value, "objgen", None)
        if objgen:
            return f"{objgen[0]} {objgen[1]} R"
    except Exception:  # pylint: disable=broad-exception-caught
        return None
    return None


def _object_key(value: Any) -> tuple[int, int] | None:
    """Key für Cycle-Detection bei indirekten PDF-Objekten."""
    try:
        objgen = getattr(value, "objgen", None)
        if objgen:
            return int(objgen[0]), int(objgen[1])
    except Exception:  # pylint: disable=broad-exception-caught
        return None
    return None


def _safe_get(dictionary: Any, key: str, default: Any = None) -> Any:
    """Robustes Dictionary-get für pikepdf.Dictionary."""
    try:
        return dictionary.get(key, default)
    except Exception:  # pylint: disable=broad-exception-caught
        return default


def _is_name(value: Any, name: str) -> bool:
    """Vergleicht PDF-Namen robust, z.B. /MCR."""
    try:
        return str(value) == name
    except Exception:  # pylint: disable=broad-exception-caught
        return False


def _build_page_ref_map(pdf: pikepdf.Pdf) -> dict[tuple[int, int], int]:
    """Mappt Page-Objektreferenzen auf 1-basierte Seitenzahlen."""
    page_refs: dict[tuple[int, int], int] = {}

    for idx, page in enumerate(pdf.pages, start=1):
        try:
            page_obj = getattr(page, "obj", page)
            key = _object_key(page_obj)
            if key:
                page_refs[key] = idx
        except Exception:  # pylint: disable=broad-exception-caught
            continue

    return page_refs


def _page_num_for_ref(
    page_obj: Any, page_refs: dict[tuple[int, int], int]
) -> int | None:
    """Ermittelt 1-basierte Seitenzahl aus /Pg-Referenz, falls möglich."""
    key = _object_key(page_obj)
    if not key:
        return None
    return page_refs.get(key)


def _extract_role_map(struct_tree_root: pikepdf.Dictionary) -> dict[str, str]:
    """Extrahiert /RoleMap aus /StructTreeRoot."""
    role_map: dict[str, str] = {}

    raw_role_map = _safe_get(struct_tree_root, "/RoleMap")
    if not isinstance(raw_role_map, pikepdf.Dictionary):
        return role_map

    for key, value in raw_role_map.items():
        src = _pdf_name_to_str(key)
        dst = _pdf_name_to_str(value)
        if src and dst:
            role_map[src] = dst

    return role_map


def resolve_role(tag: str | None, role_map: dict[str, str]) -> str | None:
    """Löst benutzerdefinierte Rollen über /RoleMap auf, mit Zyklenschutz."""
    if not tag:
        return tag

    current = tag
    visited: set[str] = set()

    while current in role_map and current not in visited:
        visited.add(current)
        current = role_map[current]

    return current


def _extract_mcid_from_scalar(value: Any) -> int | None:
    """Erkennt direkte MCID-Kinder, die im /K-Array als Integer stehen."""
    if isinstance(value, int):
        return value

    try:
        # pikepdf.Integer ist nicht immer plain int, lässt sich aber oft casten.
        if not isinstance(
            value,
            (
                pikepdf.Dictionary,
                pikepdf.Array,
                pikepdf.Name,
                pikepdf.String,
            ),
        ):
            return int(value)
    except Exception:  # pylint: disable=broad-exception-caught
        return None

    return None


def _extract_kids(
    value: Any,
    role_map: dict[str, str],
    page_refs: dict[tuple[int, int], int],
    stats: dict[str, int],
    depth: int,
    visited: set[tuple[int, int]],
) -> list[dict[str, Any]]:
    """Extrahiert beliebige /K-Kindstrukturen als Liste."""
    if value is None:
        return []

    if isinstance(value, (list, tuple, pikepdf.Array)):
        kids: list[dict[str, Any]] = []
        for item in value:
            extracted = _extract_node(
                item,
                role_map=role_map,
                page_refs=page_refs,
                stats=stats,
                depth=depth,
                visited=visited,
            )
            if extracted is None:
                continue
            if isinstance(extracted, list):
                kids.extend(extracted)
            else:
                kids.append(extracted)
        return kids

    extracted = _extract_node(
        value,
        role_map=role_map,
        page_refs=page_refs,
        stats=stats,
        depth=depth,
        visited=visited,
    )
    if extracted is None:
        return []
    if isinstance(extracted, list):
        return extracted
    return [extracted]


def _extract_node(
    node: Any,
    role_map: dict[str, str],
    page_refs: dict[tuple[int, int], int],
    stats: dict[str, int],
    depth: int,
    visited: set[tuple[int, int]],
) -> dict[str, Any] | list[dict[str, Any]] | None:
    """Rekursive Extraktion eines StructTree-Knotens oder MCID-Kindes."""
    if depth > MAX_DEPTH:
        stats["truncated_count"] += 1
        return {
            "kind": "truncated",
            "reason": f"max depth {MAX_DEPTH} reached",
        }

    direct_mcid = _extract_mcid_from_scalar(node)
    if direct_mcid is not None:
        stats["mcid_count"] += 1
        return {
            "kind": "mcid",
            "mcid": direct_mcid,
        }

    if isinstance(node, (list, tuple, pikepdf.Array)):
        return _extract_kids(
            node,
            role_map=role_map,
            page_refs=page_refs,
            stats=stats,
            depth=depth + 1,
            visited=visited,
        )

    if not isinstance(node, pikepdf.Dictionary):
        return None

    obj_key = _object_key(node)
    if obj_key:
        if obj_key in visited:
            stats["cycle_count"] += 1
            return {
                "kind": "cycle_ref",
                "object": f"{obj_key[0]} {obj_key[1]} R",
            }
        visited = set(visited)
        visited.add(obj_key)

    type_value = _safe_get(node, "/Type")

    if _is_name(type_value, "/MCR"):
        mcid_raw = _safe_get(node, "/MCID")
        mcid = None
        try:
            if mcid_raw is not None:
                mcid = int(mcid_raw)
        except Exception:  # pylint: disable=broad-exception-caught
            mcid = None

        page_obj = _safe_get(node, "/Pg")
        page_num = _page_num_for_ref(page_obj, page_refs)

        stats["mcr_count"] += 1
        if mcid is not None:
            stats["mcid_count"] += 1

        result: dict[str, Any] = {
            "kind": "mcr",
            "mcid": mcid,
        }
        if page_num is not None:
            result["page"] = page_num
        page_ref = _object_ref(page_obj)
        if page_ref:
            result["page_ref"] = page_ref
        return result

    if _is_name(type_value, "/OBJR"):
        page_obj = _safe_get(node, "/Pg")
        page_num = _page_num_for_ref(page_obj, page_refs)

        result = {
            "kind": "objr",
        }
        if page_num is not None:
            result["page"] = page_num

        obj = _safe_get(node, "/Obj")
        obj_ref = _object_ref(obj)
        if obj_ref:
            result["object_ref"] = obj_ref

        stats["objr_count"] += 1
        return result

    raw_tag = _pdf_name_to_str(_safe_get(node, "/S"))
    if raw_tag:
        stats["tag_count"] += 1

        standard_tag = resolve_role(raw_tag, role_map)

        result = {
            "kind": "struct",
            "tag": raw_tag,
            "standard_tag": standard_tag,
        }

        obj_ref = _object_ref(node)
        if obj_ref:
            result["object_ref"] = obj_ref

        alt = _pdf_text_to_str(_safe_get(node, "/Alt"))
        if alt:
            result["alt"] = alt
            stats["alt_count"] += 1

        actual_text = _pdf_text_to_str(_safe_get(node, "/ActualText"))
        if actual_text:
            result["actual_text"] = actual_text
            stats["actual_text_count"] += 1

        lang = _pdf_text_to_str(_safe_get(node, "/Lang"))
        if lang:
            result["lang"] = lang
            stats["lang_count"] += 1

        title = _pdf_text_to_str(_safe_get(node, "/Title"))
        if title:
            result["title"] = title
            stats["title_count"] += 1

        element_id = _pdf_text_to_str(_safe_get(node, "/ID"))
        if element_id:
            result["id"] = element_id

        page_obj = _safe_get(node, "/Pg")
        page_num = _page_num_for_ref(page_obj, page_refs)
        if page_num is not None:
            result["page"] = page_num

        kids = _extract_kids(
            _safe_get(node, "/K"),
            role_map=role_map,
            page_refs=page_refs,
            stats=stats,
            depth=depth + 1,
            visited=visited,
        )
        if kids:
            result["children"] = kids

        return result

    # Fallback: Dictionary ohne /S, aber evtl. mit /K.
    if "/K" in node:
        return _extract_kids(
            _safe_get(node, "/K"),
            role_map=role_map,
            page_refs=page_refs,
            stats=stats,
            depth=depth + 1,
            visited=visited,
        )

    return None


def _empty_stats() -> dict[str, int]:
    """Initialisiert Summary-Zähler."""
    return {
        "tag_count": 0,
        "mcid_count": 0,
        "mcr_count": 0,
        "objr_count": 0,
        "alt_count": 0,
        "actual_text_count": 0,
        "lang_count": 0,
        "title_count": 0,
        "cycle_count": 0,
        "truncated_count": 0,
    }


def _skipped_result(pdf_path: Path, reason: str) -> dict[str, Any]:
    """Standardisiertes Ergebnis für ungetaggte/nicht extrahierbare PDFs."""
    return {
        "status": "skipped",
        "reason": reason,
        "source_pdf": str(pdf_path),
        "is_tagged": False,
        "role_map": {},
        "tree": None,
        "summary": _empty_stats(),
    }


def write_json_artifact(data: dict[str, Any], output_path: Path) -> None:
    """Schreibt JSON-Artefakt mit UTF-8."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def extract_existing_tags(
    pdf_path: str | Path,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """
    Extrahiert vorhandene PDF-Tags als neutrales Dict.

    Bei ungetaggten PDFs wird kein Fehler geworfen, sondern ein sauberes
    skipped-Ergebnis zurückgegeben.
    """
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        result = _skipped_result(pdf_path, "file missing")
        result["status"] = "error"
        if output_path:
            write_json_artifact(result, Path(output_path))
        return result

    try:
        with pikepdf.open(str(pdf_path)) as pdf:
            root = pdf.Root

            if "/StructTreeRoot" not in root:
                result = _skipped_result(pdf_path, "StructTreeRoot missing")
                if output_path:
                    write_json_artifact(result, Path(output_path))
                return result

            struct_tree_root = root.StructTreeRoot
            role_map = _extract_role_map(struct_tree_root)
            page_refs = _build_page_ref_map(pdf)
            stats = _empty_stats()

            children = _extract_kids(
                _safe_get(struct_tree_root, "/K"),
                role_map=role_map,
                page_refs=page_refs,
                stats=stats,
                depth=0,
                visited=set(),
            )

            result = {
                "status": "success",
                "source_pdf": str(pdf_path),
                "is_tagged": True,
                "role_map": role_map,
                "tree": {
                    "kind": "struct_tree_root",
                    "children": children,
                },
                "summary": stats,
            }

            lang = _pdf_text_to_str(_safe_get(root, "/Lang"))
            if lang:
                result["document_lang"] = lang

            mark_info = _safe_get(root, "/MarkInfo")
            if isinstance(mark_info, pikepdf.Dictionary):
                marked = _safe_get(mark_info, "/Marked")
                if marked is not None:
                    result["mark_info"] = {
                        "marked": bool(marked),
                    }

            if output_path:
                write_json_artifact(result, Path(output_path))

            return result

    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.debug("Tag-Extraktion fehlgeschlagen: %s", exc)
        result = _skipped_result(pdf_path, f"extraction failed: {exc}")
        result["status"] = "error"
        if output_path:
            write_json_artifact(result, Path(output_path))
        return result


def _normalize_tag_name(tag: Any) -> str:
    """Normalisiert Tag-Namen für robuste Vergleiche."""
    return str(tag or "").strip().strip("/").lower()


def iter_struct_nodes(existing_tags: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Liefert alle Strukturknoten aus einem existing_tags-Ergebnis flach zurück.

    Die Funktion ist bewusst JSON-/Dict-basiert, damit sie sowohl direkt nach
    extract_existing_tags() als auch aus einem gespeicherten Artefakt nutzbar ist.
    """
    nodes: list[dict[str, Any]] = []

    def _walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                _walk(item)
            return

        if not isinstance(node, dict):
            return

        if node.get("kind") == "struct":
            nodes.append(node)

        children = node.get("children")
        if children:
            _walk(children)

    tree = (
        existing_tags.get("tree") if isinstance(existing_tags, dict) else None
    )
    if isinstance(tree, dict):
        _walk(tree.get("children", []))

    return nodes


def find_struct_nodes_by_tag(
    existing_tags: dict[str, Any],
    tag_names: set[str],
) -> list[dict[str, Any]]:
    """
    Findet Strukturknoten anhand von /S oder aufgelöster standard_tag.

    Beispiel:
        find_struct_nodes_by_tag(existing_tags, {"Formula", "Math"})
    """
    wanted = {_normalize_tag_name(t) for t in tag_names}
    matches: list[dict[str, Any]] = []

    for node in iter_struct_nodes(existing_tags):
        raw_tag = _normalize_tag_name(node.get("tag"))
        std_tag = _normalize_tag_name(node.get("standard_tag"))
        if raw_tag in wanted or std_tag in wanted:
            matches.append(node)

    return matches


def has_struct_tag(existing_tags: dict[str, Any], tag_names: set[str]) -> bool:
    """Prüft, ob vorhandene Tags mindestens einen der angegebenen Tagtypen enthalten."""
    return bool(find_struct_nodes_by_tag(existing_tags, tag_names))


def collect_struct_texts(
    existing_tags: dict[str, Any],
    tag_names: set[str] | None = None,
    fields: tuple[str, ...] = ("actual_text", "alt", "title"),
) -> list[str]:
    """
    Sammelt Textsignale aus vorhandenen Strukturknoten.

    Standardmäßig werden /ActualText, /Alt und /Title berücksichtigt.
    Wenn tag_names gesetzt ist, werden nur passende Tagtypen betrachtet.
    """
    if tag_names:
        nodes = find_struct_nodes_by_tag(existing_tags, tag_names)
    else:
        nodes = iter_struct_nodes(existing_tags)

    texts: list[str] = []
    seen: set[str] = set()

    for node in nodes:
        for field in fields:
            value = node.get(field)
            if not value:
                continue
            text_value = str(value).strip()
            if not text_value or text_value in seen:
                continue
            seen.add(text_value)
            texts.append(text_value)

    return texts


def main() -> None:
    """Kleines Debug-CLI für isolierte Tests."""
    parser = argparse.ArgumentParser(
        description="Extrahiert vorhandene PDF-Tags als JSON-Artefakt."
    )
    parser.add_argument("input", help="Pfad zur PDF-Datei")
    parser.add_argument(
        "output",
        nargs="?",
        help="Pfad zur JSON-Ausgabe. Default: <input>.existing_tags.json",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = (
        Path(args.output)
        if args.output
        else input_path.with_suffix(".existing_tags.json")
    )

    result = extract_existing_tags(input_path, output_path)

    print(f"status: {result.get('status')}")
    print(f"is_tagged: {result.get('is_tagged')}")
    print(f"artifact: {output_path}")
    summary = result.get("summary", {})
    print(f"tag_count: {summary.get('tag_count', 0)}")
    print(f"mcid_count: {summary.get('mcid_count', 0)}")
    print(f"alt_count: {summary.get('alt_count', 0)}")
    print(f"actual_text_count: {summary.get('actual_text_count', 0)}")


if __name__ == "__main__":
    main()

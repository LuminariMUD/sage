"""Regression coverage for the approved divine concordances."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CANON_FACTIONS = REPO_ROOT / "lore_docs" / "canon" / "factions"
DRAFT_FACTIONS = REPO_ROOT / "lore_docs" / "drafts" / "factions"
DEITIES_PATH = CANON_FACTIONS / "DEITIES.md"
TWO_ORDERS_PATH = CANON_FACTIONS / "THE_TWO_ORDERS_OF_DIVINITY.md"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_divine_concordances_exist_only_in_canon() -> None:
    assert DEITIES_PATH.is_file()
    assert TWO_ORDERS_PATH.is_file()
    assert not (DRAFT_FACTIONS / DEITIES_PATH.name).exists()
    assert not (DRAFT_FACTIONS / TWO_ORDERS_PATH.name).exists()


def test_deity_concordance_has_one_complete_forty_name_roster() -> None:
    document = read(DEITIES_PATH)
    roster_block = document.split("## The Forty Names", 1)[1].split("\n---\n", 1)[0]
    roster_cells = re.findall(r"^\| [^|]+ \| ([^|]+) \|$", roster_block, re.MULTILINE)
    roster_names = [
        name.strip()
        for cell in roster_cells
        if cell.strip() not in {"Recognized names", "---"}
        for name in cell.split(",")
    ]
    entry_block = document.split("## The Great Cadences", 1)[1].split(
        "## The Knightly Constellations", 1
    )[0]
    entry_names = re.findall(r"^### ([A-Z][A-Za-z']+)", entry_block, re.MULTILINE)

    assert document.count("# The Gods of Lumia\n") == 1
    assert len(roster_names) == len(set(roster_names)) == 40
    assert set(entry_names) == set(roster_names)
    assert len(re.findall(r"^- \*\*Cadence:\*\*", document, re.MULTILINE)) == 40
    assert len(re.findall(r"^- \*\*Sign:\*\*", document, re.MULTILINE)) == 40
    assert len(re.findall(r"^- \*\*(?:Tenets|Law):\*\*", document, re.MULTILINE)) == 40
    assert "This canon document adopts the following reconciliations:" in document
    assert "Twenty-one regional powers are established by this concordance" in document


def test_two_orders_concordance_establishes_the_approved_distinction() -> None:
    document = read(TWO_ORDERS_PATH)

    required_claims = (
        "# The Two Orders of Divinity",
        "## The First Order: The Woven Gods",
        "## The Second Order: The Deep Titans",
        "## The Two Roads of Divine Magic",
        "The **Titan Blessed** are direct conduits of Titans",
        "The **False Titans** are Woven imitations",
        "The **Twenty-First Titan** is dangerous",
        "Historical drafts are testimony, not continuing authority.",
    )
    for claim in required_claims:
        assert claim in document

    assert "pending approval" not in document.lower()
    assert "promotion would" not in document.lower()


def test_divine_canon_references_resolve() -> None:
    for document_path in (DEITIES_PATH, TWO_ORDERS_PATH):
        references = re.findall(r"`(lore_docs/canon/[^`]+\.md)`", read(document_path))
        assert references
        for reference in references:
            assert (
                REPO_ROOT / reference
            ).is_file(), f"{document_path.name} has a missing canon reference: {reference}"


def test_deity_lore_body_contains_no_legacy_implementation_mapping() -> None:
    lore_body = read(DEITIES_PATH).split("## Provenance and Canon Decisions", 1)[0]
    forbidden = (
        "DOMAIN_",
        "WEAPON_TYPE_",
        "Import Schema",
        "Guidance for Implementers",
        "Suggested Domains",
        "Favored Weapon",
        "src/deities",
        "alignment grid",
    )
    for residue in forbidden:
        assert residue.lower() not in lore_body.lower()

"""Integrity checks for approved character-creation lore."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CANON_ROOT = REPO_ROOT / "lore_docs" / "canon"
HOMELANDS_PATH = CANON_ROOT / "locations" / "the_thirteen_homelands.md"
LANGUAGES_PATH = CANON_ROOT / "cultures" / "languages_of_the_homelands.md"
COMPASS_PATH = CANON_ROOT / "cultures" / "the_characters_compass.md"

HOMELANDS = {
    "Ashenport": "homeland/ashenport",
    "Sanctus": "homeland/sanctus",
    "Onduis": "homeland/onduis",
    "Selerish": "homeland/selerish",
    "Carstan": "homeland/carstan",
    "Axtros": "homeland/axtros",
    "Hir": "homeland/hir",
    "Quechian": "homeland/quechian",
    "Vailand": "homeland/vailand",
    "Oorpii": "homeland/oorpii",
    "Kellust": "homeland/kellust",
    "East Ubdina": "homeland/east-ubdina",
    "West Ubdina": "homeland/west-ubdina",
}

LANGUAGES = {
    "Ashen Cant": "language/ashen-cant",
    "Sanctine": "language/sanctine",
    "Onduic": "language/onduic",
    "Seleric": "language/seleric",
    "Carstani": "language/carstani",
    "Axtrosi": "language/axtrosi",
    "Hiri": "language/hiri",
    "Quechian": "language/quechian",
    "Vailic": "language/vailic",
    "Oorpic": "language/oorpic",
    "Tal": "language/tal",
    "Ubdinic": "language/ubdinic",
}

BACKGROUNDS = {
    "Acolyte": "background/acolyte",
    "Charlatan": "background/charlatan",
    "Criminal/Spy": "background/criminal",
    "Entertainer": "background/entertainer",
    "Folk Hero": "background/folk-hero",
    "Gladiator": "background/gladiator",
    "Trader": "background/trader",
    "Hermit": "background/hermit",
    "Squire": "background/squire",
    "Noble": "background/noble",
    "Outlander": "background/outlander",
    "Pirate": "background/pirate",
    "Sage": "background/sage",
    "Sailor": "background/sailor",
    "Soldier": "background/soldier",
    "Urchin": "background/urchin",
}

PROFILE_FIELDS = ("Goals", "Personality", "Ideals", "Bonds", "Flaws")
PROFILE_ITEMS = (
    "profile/short-description",
    "profile/long-description",
    "profile/background-story",
    "profile/background",
    "profile/goals",
    "profile/personality",
    "profile/ideals",
    "profile/bonds",
    "profile/flaws",
    "profile/age",
    "profile/region",
    "profile/faction",
    "profile/hometown",
    "profile/deity",
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def h2_section(document: str, heading: str) -> str:
    match = re.search(
        rf"^## {re.escape(heading)}\n(?P<body>.*?)(?=^## |\Z)",
        document,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"missing section: {heading}"
    return match.group("body")


def stable_ids(document: str, namespace: str) -> set[str]:
    return set(re.findall(rf"`({re.escape(namespace)}/[a-z-]+)`", document))


def test_approved_character_creation_documents_exist() -> None:
    assert HOMELANDS_PATH.is_file()
    assert LANGUAGES_PATH.is_file()
    assert COMPASS_PATH.is_file()


def test_repository_lore_references_resolve() -> None:
    documents = (HOMELANDS_PATH, LANGUAGES_PATH, COMPASS_PATH)

    for document_path in documents:
        for reference in re.findall(
            r"`(lore_docs/[^`]+\.md)`",
            read(document_path),
        ):
            assert (
                REPO_ROOT / reference
            ).is_file(), f"{document_path.name} has a missing lore reference: {reference}"


def test_every_runtime_homeland_has_a_complete_canon_record() -> None:
    document = read(HOMELANDS_PATH)
    card_summaries: set[str] = set()

    assert stable_ids(document, "homeland") == set(HOMELANDS.values())
    assert "| 13" in document

    for name, stable_id in HOMELANDS.items():
        section = h2_section(document, name)
        assert f"`{stable_id}`" in section
        for required_heading in (
            "### Card summary",
            "### Player-facing lore",
            "### Cultural anchors",
            "### Media anchors",
            "### Provenance",
        ):
            assert required_heading in section, f"{name} lacks {required_heading}"

        assert "placeholder" not in section.lower()
        summary = section.split("### Card summary", 1)[1].split("###", 1)[0].strip()
        assert summary
        assert summary not in card_summaries, f"duplicate card summary: {name}"
        card_summaries.add(summary)


def test_homeland_identity_collisions_are_explicitly_resolved() -> None:
    document = read(HOMELANDS_PATH)
    decisions = h2_section(document, "Canonical Crosswalk")

    assert "Onduis is the canonical spelling" in decisions
    assert "Ashenport is a city within Onduis" in decisions
    assert "Sanctus is a city within Axtros" in decisions
    assert "Hir is not Ashenport" in decisions
    assert "East and West Ubdina are distinct Homelands" in decisions


def test_selectable_hometown_reuses_approved_city_lore() -> None:
    document = read(HOMELANDS_PATH)
    hometown = h2_section(document, "Hometown Crosswalk")

    assert "`hometown/1`" in hometown
    assert "`homeland/ashenport`" in hometown
    assert "**Hometown detail:**" in hometown
    assert "CITY_SANCTUS" in hometown
    assert "must not become a Hometown option" in hometown


def test_every_homeland_language_has_player_facing_canon() -> None:
    document = read(LANGUAGES_PATH)

    assert stable_ids(document, "language") == set(LANGUAGES.values())

    for name, stable_id in LANGUAGES.items():
        section = h2_section(document, name)
        assert f"`{stable_id}`" in section
        assert "**Sample expression:**" in section
        assert "**Player help summary:**" in section

    registry = h2_section(document, "Language Registry")
    for homeland in HOMELANDS:
        assert homeland in registry


def test_language_canon_rejects_the_common_placeholder_reward() -> None:
    document = read(LANGUAGES_PATH)
    introduction = document[: document.index("## Language Registry")]
    requirements = h2_section(document, "Implementation Requirements")

    assert "every Homeland grants its listed Heart Tongue" in introduction
    assert "Common remains universal" in requirements
    assert "reject Common as the mapped reward" in requirements


def test_profile_fields_have_complete_source_owned_guidance() -> None:
    document = read(COMPASS_PATH)
    lexicon = h2_section(document, "Complete Role-Play Hub Lexicon")

    for profile_id in PROFILE_ITEMS:
        assert f"`{profile_id}`" in lexicon

    for name in PROFILE_FIELDS:
        section = re.search(
            rf"^### {re.escape(name)}\n(?P<body>.*?)(?=^### |\Z)",
            document,
            flags=re.MULTILINE | re.DOTALL,
        )
        assert section is not None, f"missing profile guidance: {name}"
        body = section.group("body")
        assert "**Hub summary:**" in body
        assert "**Screen introduction:**" in body
        assert "**Editor prompt:**" in body
        assert "**Generator shape:**" in body


def test_every_background_has_distinct_lumia_inspiration() -> None:
    document = read(COMPASS_PATH)

    assert stable_ids(document, "background") == set(BACKGROUNDS.values())

    for name in BACKGROUNDS:
        section = h2_section(document, name)
        assert "### Permanent-background biography" in section
        assert "### Inspiration seeds" in section
        for field in ("Personality", "Ideals", "Bonds", "Flaws"):
            assert f"**{field}**" in section, f"{name} lacks {field} seeds"
            seed_block = re.search(
                rf"^\*\*{field}\*\*\n(?P<body>.*?)(?=^\*\*|\Z)",
                section,
                flags=re.MULTILINE | re.DOTALL,
            )
            assert seed_block is not None
            seeds = re.findall(
                r"^- (.+(?:\n  .+)*)",
                seed_block.group("body"),
                flags=re.MULTILINE,
            )
            assert len(seeds) >= 2, f"{name} needs two {field} seeds"
            assert len(seeds) == len(set(seeds)), f"{name} repeats a {field} seed"


def test_public_compass_copy_has_no_imported_campaign_residue() -> None:
    document = read(COMPASS_PATH)
    public_copy = document[: document.index("## Provenance")]

    banned = (
        "Palanthas",
        "this chapter",
        "Unused Feat",
        "ask staff",
        "detailed information is not yet available",
        "Non-Spell-Effect",
    )
    for phrase in banned:
        assert phrase.casefold() not in public_copy.casefold()


def test_compass_states_inspiration_and_mechanics_boundaries() -> None:
    document = read(COMPASS_PATH)
    inspiration = h2_section(document, "Inspiration Is Not Selection")
    mechanics = h2_section(document, "Editorial and Implementation Rules")
    assert re.search(
        r"will not set or\s*>?\s*change your character's Background",
        inspiration,
    )
    assert "Goals do not use a Background theme" in inspiration
    assert "mechanics are published" in mechanics
    assert "Lore supplies biography" in mechanics

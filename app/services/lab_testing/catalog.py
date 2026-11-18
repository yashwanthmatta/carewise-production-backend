"""A synthetic lab test catalog, grouped by health topic.

Every entry is marked synthetic and unavailable. Real availability, panel contents, specimen
requirements, preparation instructions, turnaround and prices must come from a signed lab
partner's own catalog; none of that is invented here, so those fields stay empty.
The descriptions are plain educational text about what a test measures, nothing more.
"""

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class CatalogTest:
    key: str
    name: str
    category: str
    measures: str
    includes: tuple[str, ...] = ()
    specimen: str = "Blood"
    # Filled only from a partner's confirmed catalog. Empty means "not confirmed".
    partner_price_cents: int | None = None
    preparation: str = ""
    turnaround: str = ""
    source: str = "synthetic"
    available: bool = False

    def public(self) -> dict:
        data = asdict(self)
        data["includes"] = list(self.includes)
        return data


@dataclass(frozen=True)
class Category:
    key: str
    name: str
    summary: str
    tests: tuple[CatalogTest, ...] = field(default_factory=tuple)


def _t(key, name, category, measures, includes=(), specimen="Blood"):
    return CatalogTest(key=key, name=name, category=category, measures=measures, includes=tuple(includes), specimen=specimen)


CATEGORIES: tuple[Category, ...] = (
    Category("heart", "Heart and cholesterol", "Fats in the blood that doctors use, with blood pressure and other risks, to judge heart health.", (
        _t("lipid-panel", "Lipid panel", "heart", "The main cholesterol tests in one draw.", ("Total cholesterol", "LDL cholesterol", "HDL cholesterol", "Triglycerides")),
    )),
    Category("metabolic", "Blood sugar", "How the body handles sugar, now and over the last few months.", (
        _t("glucose", "Glucose", "metabolic", "The sugar level in the blood at the time of the draw."),
        _t("a1c", "Hemoglobin A1c", "metabolic", "Average blood sugar over the last 2 to 3 months."),
    )),
    Category("thyroid", "Thyroid", "The signal that tells the thyroid how hard to work, and the thyroid's own hormone.", (
        _t("tsh", "TSH", "thyroid", "The brain's signal to the thyroid."),
        _t("free-t4", "Free T4", "thyroid", "The main hormone the thyroid makes."),
    )),
    Category("nutrients", "Nutrients", "Vitamins and stored iron that are often checked when someone is tired.", (
        _t("vitamin-d", "Vitamin D (25-hydroxy)", "nutrients", "The body's store of vitamin D."),
        _t("b12", "Vitamin B12", "nutrients", "A vitamin needed for nerves and red blood cells."),
        _t("ferritin", "Ferritin", "nutrients", "How much iron the body has stored."),
    )),
    Category("kidney", "Kidneys", "How well the kidneys filter the blood, and the salts they balance.", (
        _t("kidney-panel", "Kidney function", "kidney", "Kidney filtering and the salts the kidneys balance.", ("Creatinine", "eGFR", "BUN", "Sodium", "Potassium")),
    )),
    Category("liver", "Liver", "Enzymes and proteins that show whether the liver is irritated and how it is working.", (
        _t("liver-panel", "Liver panel", "liver", "Liver enzymes and proteins.", ("ALT", "AST", "ALP", "Bilirubin", "Albumin")),
    )),
    Category("blood", "Blood count and iron", "Red cells, white cells and platelets, and the iron that red cells need.", (
        _t("cbc", "Complete blood count (CBC)", "blood", "Red cells, white cells and platelets.", ("Hemoglobin", "Hematocrit", "White blood cells", "Platelets")),
        _t("iron-panel", "Iron panel", "blood", "Iron in the blood and the protein that carries it.", ("Iron", "TIBC", "Ferritin")),
    )),
)

TESTS: dict[str, CatalogTest] = {test.key: test for category in CATEGORIES for test in category.tests}


def catalog(category: str | None = None) -> list[dict]:
    """The catalog for display. Every test is synthetic and unavailable until a partner confirms it."""
    out = []
    for item in CATEGORIES:
        if category and item.key != category:
            continue
        out.append({"key": item.key, "name": item.name, "summary": item.summary, "tests": [test.public() for test in item.tests]})
    return out

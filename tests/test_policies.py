import pytest

from citywheels.policies import DEFAULT_POLICIES_DIR, _sections, search_policies


def test_documents_are_split_into_sections():
    sections = _sections(DEFAULT_POLICIES_DIR)

    assert len(sections) == 22
    assert all(s["file"] and s["section"] and s["text"] for s in sections)
    assert {"file": "prices.md", "section": "Prices",
            "text": "All prices are in euros (EUR) and include VAT."} in sections


@pytest.mark.parametrize(
    "query, file, section",
    [
        ("What time do you open on Saturday?", "faq.md", "When are you open?"),
        ("How much is an e-bike for a whole day?", "prices.md", "Bike rental"),
        ("Can my 14-year-old rent an e-bike?", "faq.md", "Are there age limits?"),
        (
            "How is my money refunded if I paid with a voucher?",
            "cancellations.md",
            "How the money comes back",
        ),
        ("late return fee", "prices.md", "Late return"),
    ],
)
def test_finds_relevant_section(query, file, section):
    best = search_policies(query)[0]

    assert (best["file"], best["section"]) == (file, section)
    assert set(best) == {"file", "section", "text"}
    assert best["text"].strip()


@pytest.mark.parametrize("query", ["What is the capital of Australia?", "", None])
def test_unrelated_query_returns_nothing(query):
    assert search_policies(query) == []


def test_top_k_limits_results():
    assert len(search_policies("bike", top_k=2)) == 2
    assert len(search_policies("bike", top_k=5)) == 5


def test_reads_policies_from_given_dir(tmp_path):
    (tmp_path / "rules.md").write_text(
        "# Rules\n\n## Pets\n\nNo dogs allowed.\n\n## Hours\n\nOpen at noon.\n", encoding="utf-8"
    )

    assert search_policies("dogs", policies_dir=tmp_path) == [
        {"file": "rules.md", "section": "Pets", "text": "No dogs allowed."}
    ]

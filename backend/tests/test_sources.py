from app.services import sources
from app.services.intent import classify_category, has_vanilla_signal, is_mod_request


def test_wiki_keywords_translates_and_drops_filler():
    assert sources.wiki_keywords("¿Cómo consigo las élitras?") == "elytra"
    assert sources.wiki_keywords("Dónde encuentro diamantes en Minecraft Java") == "diamond"
    assert "crafting table" in sources.wiki_keywords("¿Cómo hago una mesa de crafteo?")


def test_curated_matches_common_questions():
    for q, expected in [("Como consigo las elytras ?", "elytra"), ("¿Dónde hay diamantes?", "diamond"),
                        ("cómo consigo netherita", "netherite"), ("¿Cómo hago un portal al Nether?", "nether")]:
        docs = sources.curated_documents(q)
        assert docs and expected in (docs[0]["url"].lower() + docs[0]["content"].lower()), q
    assert sources.curated_documents("hola, ¿qué tal?") == []


def test_curated_keyword_needs_word_boundaries():
    assert sources.curated_documents("escribe un camaleón") == []  # "cama" no debe coincidir con "camaleón"


def test_official_sources_only_when_relevant():
    assert not sources.needs_help_center("¿Cómo consigo las élitras?")
    assert not sources.needs_official_pages("¿Cómo consigo las élitras?")
    assert sources.needs_official_pages("¿Qué trae la última actualización?")
    assert sources.needs_help_center("No puedo iniciar sesión en el launcher")


def test_mod_detection_has_word_boundaries():
    assert is_mod_request("¿Qué mods hay para Fabric?")
    assert not is_mod_request("Quiero cambiar de modo creativo")
    assert classify_category("¿Cómo consigo las élitras?") == "objetos"
    assert has_vanilla_signal("¿Cómo consigo las élitras?")
    assert not has_vanilla_signal("Sodium")

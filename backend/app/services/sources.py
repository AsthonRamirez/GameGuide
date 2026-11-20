"""Fuentes de conocimiento: Minecraft Wiki (comunitaria), Help Center y minecraft.net (oficiales),
Modrinth (mods) y fichas curadas de respaldo. Cada función devuelve documentos normalizados."""
from __future__ import annotations
import hashlib
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from ..core.config import BASE_DIR

log = logging.getLogger("gameguide.sources")

HTTP = requests.Session()
HTTP.headers.update({
    "User-Agent": "GameGuideAI/1.1 (educational prototype; +https://github.com/AsthonRamirez/GameGuide)",
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
})
WIKI_API = "https://minecraft.wiki/api.php"
MODRINTH_BASE = "https://api.modrinth.com/v2"
HELP_CENTER_BASE = "https://help.minecraft.net"
OFFICIAL_PAGES = [
    ("Minecraft — Acerca del juego", "https://www.minecraft.net/en-us/about-minecraft"),
    ("Minecraft — Historial de actualizaciones", "https://www.minecraft.net/en-us/updates/minecraft-updates-timeline-and-evolution"),
]

# Preguntas que justifican consultar fuentes oficiales (antes entraban siempre y ocupaban contexto).
SUPPORT_PATTERN = re.compile(
    r"\b(soporte|support|cuenta|account|launcher|lanzador|descarg\w*|comprar|compra|licencia|realms|"
    r"error|bug|crash|no abre|no inicia|reembolso|microsoft|xbox|servidor oficial|actualizaci\w+|update|"
    r"versi[oó]n|version|snapshot|lanzamiento|release|novedades|parche|patch)\b", re.I)
UPDATES_PATTERN = re.compile(
    r"\b(actualizaci\w+|update|versi[oó]n|version|snapshot|lanzamiento|release|novedades|nuevo en|"
    r"qu[eé] hay de nuevo|historial|parche|patch)\b", re.I)


def needs_help_center(question: str) -> bool:
    return bool(SUPPORT_PATTERN.search(question))


def needs_official_pages(question: str) -> bool:
    return bool(UPDATES_PATTERN.search(question))


# ------------------------------------------------------------------ términos ES → EN
WIKI_TERM_MAP = {
    "diamante": "diamond", "diamantes": "diamond", "aldeano": "villager", "aldeanos": "villager",
    "aldea": "village", "aldeas": "village", "mesa de trabajo": "crafting table",
    "mesa de crafteo": "crafting table", "mesa de encantamientos": "enchanting table",
    "encantamiento": "enchanting", "encantamientos": "enchanting", "poción": "potion",
    "pociones": "potion", "esmeralda": "emerald", "esmeraldas": "emerald", "netherita": "netherite",
    "armadura": "armor", "fortaleza": "fortress", "bastión": "bastion", "dragón del end": "ender dragon",
    "dragón": "dragon", "criatura": "mob", "criaturas": "mob", "bloque": "block", "bloques": "block",
    "objeto": "item", "objetos": "item", "elytra": "elytra", "élitra": "elytra", "élitras": "elytra",
    "elitras": "elytra", "mineral": "ore", "minerales": "ore", "bioma": "biome", "biomas": "biome",
    "aldeano bibliotecario": "librarian villager", "ciudad del end": "end city",
    "tridente": "trident", "ballesta": "crossbow", "tótem": "totem of undying", "totem": "totem of undying",
    "faro": "beacon", "yunque": "anvil", "cama": "bed", "ahogado": "drowned", "ahogados": "drowned",
    "esqueleto": "skeleton", "golem de hierro": "iron golem", "hierro": "iron", "oro": "gold",
    "cofre": "chest", "horno": "furnace", "pico": "pickaxe", "espada": "sword", "hacha": "axe",
    "arco": "bow", "trigo": "wheat", "granja": "farm", "obsidiana": "obsidian", "caballo": "horse",
    "lobo": "wolf", "gato": "cat", "perro": "dog", "abeja": "bee", "fantasma": "phantom",
    "brújula": "compass", "libro": "book", "lapislázuli": "lapis lazuli", "cuarzo": "quartz",
    "trampa": "trap", "fortuna": "fortune", "reparación": "mending", "experiencia": "experience",
    "portal": "portal", "pesca": "fishing", "caña de pescar": "fishing rod", "cohete": "firework rocket",
    "fuegos artificiales": "firework", "cuevas": "cave", "cueva": "cave", "mazmorra": "dungeon",
    "templo": "temple", "mansión": "woodland mansion", "monumento": "ocean monument",
}
# Verbos/relleno en español que no aportan a la búsqueda en la Wiki (en inglés).
WIKI_FILLER = {
    "conseguir", "consigo", "consigue", "obtener", "obtengo", "fabricar", "fabrico", "crear", "creo",
    "construir", "construyo", "encontrar", "encuentro", "donde", "dónde", "cuando", "cuándo", "puedo",
    "se", "hace", "hacer", "hago", "quiero", "necesito", "ayuda", "ayúdame", "dime", "explica",
    "minecraft", "java", "bedrock", "edition", "edición", "vanilla", "juego", "tutorial", "guía",
    "para", "como", "cómo", "que", "qué", "cual", "cuál", "el", "la", "los", "las", "un", "una", "de",
    "del", "en", "con", "por", "y", "o", "a", "al", "me", "mi", "es", "son", "hay", "lo", "le",
}


def wiki_keywords(question: str) -> str:
    """Convierte la pregunta en palabras clave en inglés para la búsqueda de la Wiki."""
    q = " " + re.sub(r"[¿?¡!,.;:()\"]", " ", question.lower()) + " "
    found = []
    for es in sorted((k for k in WIKI_TERM_MAP if " " in k), key=len, reverse=True):
        if f" {es} " in q:
            found.append(WIKI_TERM_MAP[es])
            q = q.replace(f" {es} ", " ")
    for word in q.split():
        if word in WIKI_TERM_MAP:
            found.append(WIKI_TERM_MAP[word])
        elif word not in WIKI_FILLER and len(word) > 2:
            found.append(word)
    return " ".join(dict.fromkeys(found))[:120]


# ------------------------------------------------------------------ documentos
def clean_html(raw_html):
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header"]):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()


def make_source_id(source_type, url, title):
    raw = f"{source_type}|{url}|{title}".encode("utf-8", errors="ignore")
    return hashlib.sha256(raw).hexdigest()


def normalize_document(source_name, source_type, title, content, url, category="general",
                       game_version=None, source_updated_at=None, was_cached=False, max_chars=30000):
    content = re.sub(r"\s+", " ", str(content or "")).strip()[:max_chars]
    if not content or not url:
        return None
    now = datetime.now(timezone.utc).isoformat()
    return {
        "source_id": make_source_id(source_type, url, title),
        "source_name": source_name, "source_type": source_type,
        "title": str(title or "Documento sin título")[:300],
        "content": content, "url": url, "category": category,
        "game_version": game_version, "source_updated_at": source_updated_at,
        "retrieved_at": now, "updated_at": now, "was_cached": was_cached,
    }


# ------------------------------------------------------------------ fichas curadas
_FAQ = None


def _load_faq():
    global _FAQ
    if _FAQ is None:
        try:
            raw = json.loads((BASE_DIR / "app" / "data" / "curated_faq.json").read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("No se pudo cargar curated_faq.json: %s", exc)
            raw = []
        # \w{0,2} admite plurales (elytra -> elytras) sin coincidir con palabras largas ("cama" vs "camaleón").
        _FAQ = [(re.compile(r"(?<!\w)(?:" + "|".join(item["keywords"]) + r")\w{0,2}(?!\w)", re.I), item)
                for item in raw]
    return _FAQ


def curated_documents(question: str, limit: int = 2):
    """Fichas curadas cuyo tema aparece en la pregunta. Se usan como candidatas normales (no reemplazan a la Wiki)."""
    docs = []
    for pattern, item in _load_faq():
        if pattern.search(question):
            doc = normalize_document("GameGuide AI — ficha curada Vanilla", "curated", item["title"],
                                     item["content"], item["url"], category="vanilla")
            if doc:
                docs.append(doc)
        if len(docs) >= limit:
            break
    return docs


# ------------------------------------------------------------------ Minecraft Wiki
def _wiki_page(title: str):
    # Una página por petición: así MediaWiki devuelve el extracto completo (con varios títulos solo
    # la primera página trae texto completo) y no se usa exchars, que la API limita a 1200 caracteres.
    try:
        r = HTTP.get(WIKI_API, params={
            "action": "query", "prop": "extracts|info", "explaintext": 1, "inprop": "url",
            "titles": title, "redirects": 1, "format": "json", "formatversion": 2,
        }, timeout=15)
        r.raise_for_status()
        pages = r.json().get("query", {}).get("pages", [])
        page = pages[0] if pages else {}
        if page.get("missing") or not page.get("extract"):
            return None
        url = page.get("fullurl") or "https://minecraft.wiki/w/" + quote(page.get("title", "").replace(" ", "_"))
        return normalize_document("Minecraft Wiki (comunitaria)", "community_wiki",
                                  page.get("title", title), page.get("extract", ""), url,
                                  category="vanilla", source_updated_at=page.get("touched"))
    except Exception as exc:
        log.warning("Wiki: no se pudo leer '%s': %s", title, str(exc)[:120])
        return None


def search_minecraft_wiki(keywords: str, raw_question: str = "", limit: int = 3):
    """Busca con palabras clave en inglés; si no hay resultados, reintenta con la pregunta original."""
    titles = []
    for query in dict.fromkeys(q for q in (keywords, raw_question) if q):
        try:
            r = HTTP.get(WIKI_API, params={
                "action": "query", "list": "search", "srsearch": query, "srnamespace": 0,
                "srlimit": limit, "format": "json", "formatversion": 2,
            }, timeout=15)
            r.raise_for_status()
            titles = [h["title"] for h in r.json().get("query", {}).get("search", []) if h.get("title")]
        except Exception as exc:
            log.warning("Wiki: búsqueda falló (%s): %s", query[:40], str(exc)[:120])
            continue
        if titles:
            break
    if not titles:
        return []
    with ThreadPoolExecutor(max_workers=len(titles)) as pool:
        pages = list(pool.map(_wiki_page, titles))
    return [p for p in pages if p]


# ------------------------------------------------------------------ Help Center (oficial)
def search_official_help_center(question, limit=4):
    """Una sola petición por idioma: el buscador de Zendesk ya devuelve el cuerpo del artículo."""
    docs = []
    for locale in ["es-mx", "en-us"]:
        try:
            r = HTTP.get(f"{HELP_CENTER_BASE}/api/v2/help_center/articles/search.json",
                         params={"query": question, "locale": locale, "per_page": limit}, timeout=15)
            r.raise_for_status()
            payload = r.json()
            for item in (payload.get("results") or payload.get("articles") or [])[:limit]:
                body = clean_html(item.get("body") or item.get("snippet") or "")
                doc = normalize_document(
                    "Minecraft Help Center (oficial)", "official",
                    item.get("title") or "Artículo de Minecraft Help", body,
                    item.get("html_url") or item.get("url") or f"{HELP_CENTER_BASE}/hc/{locale}",
                    category="vanilla")
                if doc:
                    docs.append(doc)
            if docs:
                break
        except Exception as exc:
            log.warning("Help Center (%s) no disponible: %s", locale, str(exc)[:140])
    return docs


# ------------------------------------------------------------------ minecraft.net (oficial)
_OFFICIAL_PAGE_CACHE = {}


def _official_page(item):
    title, url = item
    now = time.time()
    try:
        cached = _OFFICIAL_PAGE_CACHE.get(url)
        if cached and now - cached["timestamp"] < 86400:
            text_body = cached["content"]
        else:
            r = HTTP.get(url, timeout=18)
            r.raise_for_status()
            text_body = clean_html(r.text)
            _OFFICIAL_PAGE_CACHE[url] = {"timestamp": now, "content": text_body}
        return normalize_document("Minecraft.net (oficial)", "official", title, text_body[:10000], url, "vanilla")
    except Exception as exc:
        log.warning("Página oficial no disponible %s: %s", url, str(exc)[:120])
        return None


def search_official_minecraft_pages(question=""):
    with ThreadPoolExecutor(max_workers=len(OFFICIAL_PAGES)) as pool:
        return [d for d in pool.map(_official_page, OFFICIAL_PAGES) if d]


# ------------------------------------------------------------------ Modrinth (código original)
MOD_NOISE_WORDS = {
    "mod","mods","modpack","modpacks","pack","packs","shader","shaders","resource","texture",
    "paquete","paquetes","recursos","texturas","quiero","necesito","busco","recomienda",
    "recomiendas","recomiéndame","recomendar","recomendación","mejor","mejores","usar","puedo",
    "existe","algún","alguno","alguna","para","que","qué","cual","cuál","como","cómo","hay",
    "de","la","el","los","las","un","una","en","con","sin","por","me","mi","tu","y","o","a",
    "minecraft","the","a","an","and","or","of","to","for","with","best","good","some","any",
    "forge","neoforge","fabric","quilt","modrinth","curseforge","versión","version","consultar","ver",
    "hace","hacer","hacen","dime","dame","explica","explícame","explicame","cuéntame","cuentame","háblame","hablame",
    "sobre","acerca","información","informacion","funciona","sirve","es","son","del","al","se","lo","le","su","sus","tengo","java","edition","edición",
}
MOD_TERM_MAP = {
    "recetas":"recipes", "receta":"recipe", "crafteo":"crafting", "mapa":"map", "minimapa":"minimap",
    "optimización":"optimization", "optimizacion":"optimization", "rendimiento":"performance",
    "mochila":"backpack", "mochilas":"backpacks", "dragones":"dragons", "magia":"magic",
    "tecnología":"technology", "tecnologia":"technology", "granja":"farming", "granjas":"farming",
    "construcción":"building", "construccion":"building", "herramientas":"tools", "armas":"weapons",
    "mascotas":"pets", "animales":"animals", "cocina":"cooking", "comida":"food", "armadura":"armor",
    "armaduras":"armor", "jefes":"bosses", "mazmorras":"dungeons", "mazmorra":"dungeon",
    "inventario":"inventory", "sonido":"sound", "iluminación":"lighting", "iluminacion":"lighting",
    "agua":"water", "realista":"realistic", "realistas":"realistic", "medieval":"medieval", "agricultura":"farming", "aventura":"adventure",
    "decoración":"decoration", "decoracion":"decoration", "muebles":"furniture",
}

def detect_mod_project_type(question):
    q = question.lower()
    if re.search(r"\bmod ?packs?\b", q):
        return "modpack"
    if re.search(r"\bshaders?\b", q):
        return "shader"
    if re.search(r"resource ?packs?|texture ?packs?|paquetes? de (recursos|texturas)", q):
        return "resourcepack"
    return "mod"

def detect_mod_loader(question):
    q = question.lower()
    for loader in ["neoforge", "forge", "fabric", "quilt"]:
        if re.search(rf"\b{loader}\b", q):
            return loader
    return None

def build_modrinth_query(question):
    """Convierte la pregunta en palabras clave (ES→EN) para que Modrinth encuentre mejores resultados."""
    # Conserva nombres propios conocidos en vez de enviar a Modrinth toda la frase en español.
    if re.search(r"farmer['’]?s\s+delight", question, flags=re.I):
        return "Farmer's Delight"
    words = re.findall(r"[a-zA-Z0-9áéíóúñüÁÉÍÓÚÑÜ\-]+", question.lower())
    keywords = []
    for w in words:
        if w in MOD_NOISE_WORDS or len(w) < 2:
            continue
        keywords.append(MOD_TERM_MAP.get(w, w))
    keywords = list(dict.fromkeys(keywords))
    return " ".join(keywords)[:120] or question[:120]


MODRINTH_TYPES = {"mod", "modpack", "shader", "resourcepack"}
MODRINTH_LOADERS = {"fabric", "forge", "neoforge", "quilt"}
RELEASE_VERSION = re.compile(r"\d+\.\d+(?:\.\d+)?")

def _modrinth_request(query, project_type, game_version, loader, limit):
    """Una sola consulta a /search con los filtros indicados (los vacíos no se aplican)."""
    facets = []
    if project_type:
        facets.append([f"project_type:{project_type}"])
    if game_version:
        facets.append([f"versions:{game_version}"])
    if loader:
        facets.append([f"categories:{loader}"])
    params = {"query": query, "index": "relevance", "limit": limit}
    if facets:
        params["facets"] = json.dumps(facets)
    response = HTTP.get(f"{MODRINTH_BASE}/search", params=params, timeout=(3, 8))
    response.raise_for_status()
    return response.json().get("hits", [])


def search_modrinth(question, game_version="", limit=5, detail_top=1,
                    search_terms=None, project_type=None, loader=None):
    """
    Busca mods, modpacks, shaders y resource packs con la API pública de Modrinth (sin API Key).
    Si con todos los filtros no hay resultados, relaja los filtros paso a paso (versión → cargador → tipo)
    para no quedarse con las manos vacías. Devuelve (documentos, nota | None).
    """
    project_type = project_type if project_type in MODRINTH_TYPES else detect_mod_project_type(question)
    loader = loader if loader in MODRINTH_LOADERS else (detect_mod_loader(question) if project_type in ("mod", "modpack") else None)
    version = game_version.strip() if game_version and RELEASE_VERSION.fullmatch(game_version.strip()) else ""
    query = (search_terms or "").strip() or build_modrinth_query(question)
    raw_query = re.sub(r"\s+", " ", question).strip()[:120]

    # Limita las llamadas en serie: primero intenta con los filtros solicitados;
    # si no hay resultados, realiza una sola búsqueda amplia.
    steps = [(project_type, version, loader, query, "")]
    if raw_query and raw_query != query:
        fallback_query = raw_query
    else:
        fallback_query = query
    steps.append(("", "", "", fallback_query,
                  "sin filtros de tipo, versión ni cargador"))

    try:
        hits, note, seen = [], None, set()
        for i, (ptype_f, ver_f, loader_f, q, label) in enumerate(steps):
            key = (ptype_f, ver_f, loader_f, q)
            if key in seen:
                continue
            seen.add(key)
            hits = _modrinth_request(q, ptype_f, ver_f, loader_f, max(1, min(int(limit), 20)))
            if hits:
                if label:
                    note = f"Modrinth no tenía resultados exactos; se muestran resultados {label}. Verifica la compatibilidad."
                break
        if not hits:
            return [], f"Modrinth no devolvió resultados para «{query}»."

        docs = []
        for position, item in enumerate(hits):
            slug = item.get("slug") or item.get("project_id")
            if not slug:
                continue
            name = item.get("title") or "Proyecto de Modrinth"
            description = item.get("description") or "Sin descripción disponible."
            versions = item.get("versions") or []
            releases = [v for v in versions if RELEASE_VERSION.fullmatch(v)] or versions[-15:]
            categories = item.get("categories") or []
            ptype = item.get("project_type") or project_type or "mod"

            body_text, loaders, env = "", [], ""
            if position < detail_top:
                try:
                    detail = HTTP.get(f"{MODRINTH_BASE}/project/{slug}", timeout=(3, 6))
                    if detail.ok:
                        info = detail.json()
                        body_text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", info.get("body") or "")
                        body_text = re.sub(r"<[^>]+>", " ", body_text)
                        body_text = re.sub(r"[#*_`>|]+", " ", body_text)
                        body_text = re.sub(r"\s+", " ", body_text).strip()[:2500]
                        loaders = info.get("loaders") or []
                        env = f"Cliente: {info.get('client_side','?')}, Servidor: {info.get('server_side','?')}"
                except Exception:
                    pass

            # Nota: el contenido NO depende de la consulta (se guarda en caché y se reutiliza).
            content = (
                f"Nombre: {name}. Tipo: {ptype}. Descripción: {description}. "
                f"Autor: {item.get('author') or 'No especificado'}. "
                f"Descargas: {item.get('downloads', 0)}. "
                f"Versiones de Minecraft Java compatibles según Modrinth: {', '.join(releases) or 'No especificadas'}. "
                + (f"Cargadores: {', '.join(loaders)}. " if loaders else "")
                + (f"Entorno: {env}. " if env else "")
                + f"Categorías: {', '.join(categories[:20]) or 'No especificadas'}. "
                + (f"Detalle: {body_text}" if body_text else "")
            )
            doc = normalize_document(
                source_name="Modrinth (mods)", source_type="modrinth", title=name, content=content,
                url=f"https://modrinth.com/{ptype}/{slug}", category="mods",
                game_version=game_version or None, source_updated_at=item.get("date_modified"),
            )
            if doc:
                docs.append(doc)
        return docs, note

    except requests.HTTPError as exc:
        status = getattr(exc.response, "status_code", "desconocido")
        return [], f"Modrinth respondió con un error HTTP {status}. Intenta nuevamente más tarde."
    except Exception as exc:
        return [], "No fue posible consultar Modrinth: " + str(exc)[:180]

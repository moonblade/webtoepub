"""
Anubis proof-of-work challenge solver.

Royal Road (and other sites) use Anubis (https://github.com/TecharoHQ/anubis)
to block automated scrapers. This module solves the challenge using the site's
own WASM module via wasmtime, then returns an authenticated requests.Session
that can fetch pages freely for ~7 days per cookie.

Supported algorithms: argon2id, sha256, hashx (all WASM-based).
Falls back gracefully if WASM fetch fails.
"""

import ctypes
import json
import re
import time
from typing import Optional

import requests
from wasmtime import Engine, Func, FuncType, Linker, Module, Store, ValType

from utils import custom_logger

logger = custom_logger(__name__)

ANUBIS_WASM_VARIANT = "simd128"
ANUBIS_PASS_CHALLENGE_PATH = "/.within.website/x/cmd/anubis/api/pass-challenge"
ANUBIS_CSS_LOAD_PATH = "/.within.website/x/cmd/anubis/ext/css-load"
ANUBIS_WASM_PATH = "/.within.website/x/cmd/anubis/static/wasm"
ANUBIS_CHALLENGE_SCRIPT_ID = "anubis_challenge"

_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def _extract_challenge(html: str) -> Optional[dict]:
    """Parse the Anubis challenge JSON embedded in an HTML page."""
    match = re.search(
        r'<script id="anubis_challenge" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def _is_anubis_challenge_page(html: str) -> bool:
    return bool(re.search(r'id=["\']anubis_challenge["\']', html))


def _solve_wasm(
    session: requests.Session,
    base_url: str,
    algorithm: str,
    random_data: str,
    difficulty: int,
) -> tuple[str, int, int]:
    """
    Download and run the Anubis WASM proof-of-work module.

    Returns (response_hash_hex, nonce, elapsed_ms).
    Raises RuntimeError on any failure.
    """
    ua = session.headers.get("User-Agent", _DEFAULT_UA)

    # Try simd128 first, fall back to baseline
    wasm_bytes = None
    for variant in (ANUBIS_WASM_VARIANT, "baseline"):
        url = f"{base_url}{ANUBIS_WASM_PATH}/{variant}/{algorithm}.wasm?cacheBuster=v1.28.2"
        r = requests.get(url, headers={"User-Agent": ua})
        if r.status_code == 200 and r.content[:4] == b"\x00asm":
            wasm_bytes = r.content
            logger.info(f"Fetched Anubis WASM ({variant}/{algorithm}), {len(wasm_bytes)} bytes")
            break

    if not wasm_bytes:
        raise RuntimeError(f"Could not fetch Anubis WASM for algorithm '{algorithm}'")

    engine = Engine()
    store = Store(engine)
    module = Module(engine, wasm_bytes)
    linker = Linker(engine)

    # The WASM imports one function: anubis.anubis_update_nonce(i32)
    nonce_ft = FuncType([ValType.i32()], [])
    linker.define(
        store,
        "anubis",
        "anubis_update_nonce",
        Func(store, nonce_ft, lambda _n: None),
    )

    instance = linker.instantiate(store, module)
    exports = instance.exports(store)

    memory = exports["memory"]
    data_ptr_fn = exports["data_ptr"]
    set_data_length_fn = exports["set_data_length"]
    anubis_work_fn = exports["anubis_work"]
    result_hash_ptr_fn = exports["result_hash_ptr"]
    result_hash_size_fn = exports["result_hash_size"]

    # Write hex-decoded random_data into WASM linear memory
    data_bytes = bytes.fromhex(random_data)
    buf_ptr = data_ptr_fn(store)
    raw_ptr = ctypes.cast(memory.data_ptr(store), ctypes.POINTER(ctypes.c_ubyte))
    for i, b in enumerate(data_bytes):
        raw_ptr[buf_ptr + i] = b
    set_data_length_fn(store, len(data_bytes))

    logger.info(f"Running Anubis WASM proof-of-work (difficulty={difficulty})...")
    t0 = time.time()
    # anubis_work(difficulty, starting_nonce, threads) -> nonce
    result_nonce = anubis_work_fn(store, difficulty, 0, 1)
    elapsed_ms = int((time.time() - t0) * 1000)

    hash_ptr = result_hash_ptr_fn(store)
    hash_size = result_hash_size_fn(store)
    raw_ptr2 = ctypes.cast(memory.data_ptr(store), ctypes.POINTER(ctypes.c_ubyte))
    hash_hex = bytes([raw_ptr2[hash_ptr + i] for i in range(hash_size)]).hex()

    logger.info(f"Anubis PoW solved: nonce={result_nonce}, elapsed={elapsed_ms}ms")
    return hash_hex, result_nonce, elapsed_ms


def solve_anubis(session: requests.Session, url: str) -> bool:
    """
    Detect and solve an Anubis challenge for *url*, adding the auth cookie to
    *session*.  Returns True on success, False if no challenge was found or if
    solving failed.

    The session is mutated in-place; subsequent requests within it will carry
    the auth cookie automatically.
    """
    r = session.get(url)
    if not _is_anubis_challenge_page(r.text):
        return False  # not blocked

    challenge_data = _extract_challenge(r.text)
    if not challenge_data:
        logger.warning("Anubis challenge page detected but could not parse challenge JSON")
        return False

    challenge = challenge_data["challenge"]
    rules = challenge_data["rules"]
    challenge_id = challenge["id"]
    random_data = challenge["randomData"]
    difficulty = rules["difficulty"]
    algorithm = rules["algorithm"]
    extensions = rules.get("extensions", [])

    # Extract origin (scheme + host) from url
    from urllib.parse import urlparse
    parsed = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    logger.info(
        f"Anubis challenge detected: id={challenge_id}, "
        f"algo={algorithm}, difficulty={difficulty}, extensions={extensions}"
    )

    # css-load extension: fetch the CSS verification endpoint first
    if "css-load" in extensions:
        css_url = f"{base_url}{ANUBIS_CSS_LOAD_PATH}/{challenge_id}"
        css_r = session.get(css_url)
        logger.debug(f"css-load: {css_r.status_code}")

    try:
        response_hash, nonce, elapsed_ms = _solve_wasm(
            session, base_url, algorithm, random_data, difficulty
        )
    except Exception as e:
        logger.error(f"Anubis WASM solver failed: {e}")
        return False

    # Submit the proof-of-work solution
    from urllib.parse import urlparse, urlunparse, urlencode
    redir_path = parsed.path or "/"
    params = urlencode({
        "id": challenge_id,
        "response": response_hash,
        "nonce": str(nonce),
        "redir": redir_path,
        "elapsedTime": str(elapsed_ms),
    })
    pass_url = f"{base_url}{ANUBIS_PASS_CHALLENGE_PATH}?{params}"
    result = session.get(pass_url, allow_redirects=True)

    auth_cookie_name = next(
        (k for k in session.cookies.keys() if "anubis-auth" in k), None
    )
    if auth_cookie_name:
        logger.info(f"Anubis challenge solved! Auth cookie: {auth_cookie_name}")
        return True

    logger.warning(
        f"Anubis pass-challenge returned {result.status_code} but no auth cookie was set"
    )
    return False


def make_royal_road_session() -> requests.Session:
    """
    Return a requests.Session pre-authenticated against Royal Road's Anubis
    challenge.  The cookie is valid for ~7 days; on failure the plain session
    is returned so callers can degrade gracefully.
    """
    session = requests.Session()
    session.headers.update({"User-Agent": _DEFAULT_UA})

    probe_url = "https://www.royalroad.com/fiction/36049"  # any RR page works
    try:
        ok = solve_anubis(session, probe_url)
        if not ok:
            logger.info("Royal Road does not appear to require Anubis (or already authenticated)")
    except Exception as e:
        logger.error(f"Anubis solver raised an exception: {e}")

    return session

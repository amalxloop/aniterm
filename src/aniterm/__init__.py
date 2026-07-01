import json, os, shutil, subprocess, sys, tempfile, time, urllib.parse, urllib.request
from argparse import ArgumentParser, RawDescriptionHelpFormatter

_X = bytes([0xa3, 0x7f, 0x4b, 0xd9, 0x15, 0x82, 0xec, 0x56])

def _x(s):
    d = bytes.fromhex(s)
    return bytes(d[i] ^ _X[i & 7] for i in range(len(d))).decode()

ANILIST_API = "https://graphql.anilist.co"
VIDNEST_API = _x("cb0b3fa966b8c379cd1a3cf763eb8838c60c3ff773f78279cb162ab77cef8979c21122b470")
VIDNEST_ALPHABET = _x("f13d7bbf65cad40ce6061d957ef4db3591167d9454c8d9239036009f51fa800592311faa7bc58d27ce2712bd40f0982cc90804bb56e5bd069a4b23b670d5c7799e")

STYLE_BOLD = "\033[1m"
STYLE_DIM = "\033[2m"
STYLE_GREEN = "\033[92m"
STYLE_YELLOW = "\033[93m"
STYLE_BLUE = "\033[94m"
STYLE_MAGENTA = "\033[95m"
STYLE_CYAN = "\033[96m"
STYLE_RED = "\033[91m"
STYLE_RESET = "\033[0m"


_anilist_cache = {}
_last_anilist_call = 0.0


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def anilist_query(query, variables=None):
    global _last_anilist_call
    cache_key = (query, json.dumps(variables or {}, sort_keys=True))
    if cache_key in _anilist_cache:
        return _anilist_cache[cache_key]
    elapsed = time.time() - _last_anilist_call
    if elapsed < 0.8:
        time.sleep(0.8 - elapsed)
    data = {"query": query, "variables": variables or {}}
    req = urllib.request.Request(
        ANILIST_API,
        data=json.dumps(data).encode(),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "aniterm/1.0",
        },
    )
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req) as r:
                result = json.loads(r.read())
                _last_anilist_call = time.time()
                _anilist_cache[cache_key] = result
                return result
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            if "1101" in body and attempt == 0:
                eprint(f"{STYLE_YELLOW}AniList rate limited, waiting 60s...{STYLE_RESET}")
                time.sleep(60)
                continue
            if "1101" in body:
                eprint(f"{STYLE_RED}AniList rate limit hit. Wait 1-2 minutes then try again.{STYLE_RESET}")
            else:
                eprint(f"{STYLE_RED}AniList error ({e.code}). Try again later.{STYLE_RESET}")
            sys.exit(1)


def search_anime(search_term, page=1, per_page=20):
    query = """
    query ($search: String, $page: Int, $perPage: Int) {
      Page(page: $page, perPage: $perPage) {
        media(search: $search, type: ANIME) {
          id idMal
          title { romaji english native }
          format episodes status season seasonYear
          coverImage { large }
          studios(isMain: true) { nodes { name } }
          nextAiringEpisode { episode airingAt }
        }
      }
    }
    """
    result = anilist_query(query, {"search": search_term, "page": page, "perPage": per_page})
    return result.get("data", {}).get("Page", {}).get("media", [])


def get_anime_info(anilist_id):
    query = """
    query ($id: Int) {
      Media(id: $id, type: ANIME) {
        id title { romaji english native }
        format episodes status description season seasonYear genres
        coverImage { large }
        studios(isMain: true) { nodes { name } }
        nextAiringEpisode { episode airingAt }
        relations {
          edges {
            relationType
            node { id title { romaji english } format episodes season seasonYear status }
          }
        }
      }
    }
    """
    result = anilist_query(query, {"id": anilist_id})
    return result.get("data", {}).get("Media")


def custom_b64_decode(s):
    rev = {c: i for i, c in enumerate(VIDNEST_ALPHABET)}
    s = s.rstrip("=")
    buf = 0
    bits = 0
    out = bytearray()
    for ch in s:
        if ch not in rev:
            continue
        v = rev[ch]
        buf = (buf << 6) | v
        bits += 6
        if bits >= 8:
            bits -= 8
            out.append((buf >> bits) & 0xFF)
            buf &= (1 << bits) - 1
    return bytes(out)


def decrypt_vidnest(data):
    if not data.get("encrypted") or not data.get("data"):
        return data
    return json.loads(custom_b64_decode(data["data"]).decode("utf-8"))


NEG_CACHE = set()


def fetch_episode_sources(anilist_id, episode, sub_or_dub="sub"):
    key = (anilist_id, episode, sub_or_dub)
    if key in NEG_CACHE:
        raise Exception(f"HTTP 502: Dub not available for this anime")
    url = f"{VIDNEST_API}/{anilist_id}/{episode}/{sub_or_dub.lower()}"
    ua = _x("ee1031b079ee8d7996517bf93dd58538c7103caa35ccb876924f65e92ea2bb3fcd497fe235fada62985f39af2fb3df618d4f62f952e78f3dcc5079e924b2dc67934e6b9f7cf08930cc0764e826b5c266")
    ori = _x("cb0b3fa966b8c379d5162fb770f19878c50a25")
    ref = _x("cb0b3fa966b8c379d5162fb770f19878c50a25f6")
    headers = {"User-Agent": ua, "Origin": ori, "Referer": ref}
    for attempt in range(3 if sub_or_dub == "sub" else 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as r:
                return decrypt_vidnest(json.loads(r.read()))
        except urllib.error.HTTPError as e:
            if e.code == 502 and sub_or_dub == "dub":
                NEG_CACHE.add(key)
                raise Exception(f"HTTP 502: Dub not available for this anime")
            if e.code == 502 and attempt < 2:
                eprint(f"  {STYLE_YELLOW}502, retrying...{STYLE_RESET}")
                time.sleep(2 ** attempt)
                continue
            body = e.read().decode(errors="replace")[:200]
            raise Exception(f"HTTP {e.code}: {body}")


def make_proxy_url(stream_url):
    ua = _x("ee1031b079ee8d7996517bf93dd58538c7103caa35ccb876924f65e92ea2bb3fcd497fe235fada62985f39af2fb3df618d4f62f952e78f3dcc5079e924b2dc67934e6b9f7cf08930cc0764e826b5c266")
    ori = _x("cb0b3fa966b8c379ce1a2cb865ee8d2f8d1d3ea36f")
    ref = _x("cb0b3fa966b8c379ce1a2cb865ee8d2f8d1d3ea36fad")
    proxy_headers = {
        "user-agent": ua,
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.5",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
        "origin": ori,
        "referer": ref,
    }
    params = urllib.parse.urlencode({
        "url": stream_url,
        "headers": json.dumps(proxy_headers, separators=(",", ":")),
    })
    base = _x("cb0b3fa966b8c379ce1a2cb876ee8323c7512ab77cef8d38c41e65bf60ecc326d11033a0")
    return f"{base}?{params}"


def _android_check_vo():
    result = subprocess.run(["mpv", "--vo=help"], capture_output=True, text=True)
    return "null" in result.stdout and "mediacodec" not in result.stdout


def _android_play_intent(stream_url):
    """Fallback: open stream in Android's native video player."""
    eprint(f"{STYLE_YELLOW}Opening in Android video player...{STYLE_RESET}")
    proxy_url = make_proxy_url(stream_url)
    cmd = ["am", "start", "-a", "android.intent.action.VIEW",
           "-d", proxy_url, "-t", "video/*"]
    subprocess.run(cmd, capture_output=True)


def _download_subtitle(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:137.0) Gecko/20100101 Firefox/137.0",
        "Referer": _x("cb0b3fa966b8c379ce1a2cb865ee8d2f8d1d3ea36fad"),
    })
    with urllib.request.urlopen(req) as resp:
        data = resp.read()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".vtt")
    tmp.write(data)
    tmp.close()
    return tmp.name


def play_episode(stream_url, title=None, subtitle_urls=None):
    if not shutil.which("mpv"):
        eprint(f"{STYLE_RED}mpv not found. Install it first.{STYLE_RESET}")
        sys.exit(1)
    if "ANDROID_ROOT" in os.environ and _android_check_vo():
        _android_play_intent(stream_url)
        return
    proxy_url = make_proxy_url(stream_url)
    cmd = ["mpv", proxy_url, "--msg-level=all=info", "--ytdl-format=bestvideo+bestaudio/best"]
    sub_files = []
    if subtitle_urls:
        for url in subtitle_urls:
            try:
                f = _download_subtitle(url)
                sub_files.append(f)
                cmd.append(f"--sub-file={f}")
            except Exception:
                pass
    if "ANDROID_ROOT" in os.environ:
        cmd.extend(["--vo=mediacodec", "--hwdec=mediacodec-copy"])
    try:
        import curl_cffi
        cmd.append("--ytdl-raw-options=impersonate=Chrome-142")
    except ImportError:
        pass
    if title:
        cmd.append(f"--title={title}")
    subprocess.run(cmd)
    for f in sub_files:
        try:
            os.unlink(f)
        except Exception:
            pass


def fmt_title(m):
    t = m.get("title", {})
    return t.get("english") or t.get("romaji") or "Unknown"


def get_episode_count(media):
    ep = media.get("episodes")
    if ep is not None:
        return ep
    nxt = media.get("nextAiringEpisode")
    if nxt and nxt.get("episode"):
        return nxt["episode"] - 1
    return None


def fmt_compact(m):
    t = m.get("title", {})
    name = t.get("english") or t.get("romaji") or "Unknown"
    ep = get_episode_count(m)
    f = m.get("format") or ""
    y = m.get("seasonYear") or ""
    s = (m.get("season") or "")[:2]
    p = [str(m["id"]), name]
    if f: p.append(f"[{f}]")
    if ep: p.append(f"{ep}eps")
    if y: p.append(str(y))
    if s: p.append(s)
    return " ".join(p)


def try_play(anilist_id, episode, sub_or_dub):
    try:
        data = fetch_episode_sources(anilist_id, episode, sub_or_dub)
    except Exception as e:
        msg = str(e)
        if sub_or_dub == "dub" and ("502" in msg or "Dub not available" in msg):
            eprint(f"{STYLE_YELLOW}Dub not available for this anime.{STYLE_RESET}")
            if sys.stdin.isatty():
                try:
                    choice = input(f"{STYLE_BOLD}Try sub instead? [Y/n]: {STYLE_RESET}").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    choice = "n"
                if choice in ("", "y", "yes"):
                    return try_play(anilist_id, episode, "sub")
        else:
            eprint(f"{STYLE_RED}{msg}{STYLE_RESET}")
        return False
    if not data.get("success"):
        eprint(f"{STYLE_RED}{data.get('error', 'Unknown error')}{STYLE_RESET}")
        return False
    sources = data.get("sources", [])
    if not sources or not sources[0].get("file"):
        eprint(f"{STYLE_RED}No video source found.{STYLE_RESET}")
        return False
    url = sources[0]["file"]
    tracks = data.get("tracks", [])
    sub_urls = [t["file"] for t in tracks if t.get("file") and t.get("kind") in ("captions", "subtitles")]
    media = get_anime_info(anilist_id)
    title = fmt_title(media) if media else f"Anime {anilist_id}"
    label = f"{title} - Ep {episode} ({sub_or_dub.upper()})"
    print(f"  {STYLE_GREEN}▶{STYLE_RESET} {STYLE_BOLD}{label}{STYLE_RESET}")
    play_episode(url, title=label, subtitle_urls=sub_urls or None)
    return True


def play(anilist_id, episode, sub_or_dub, loop=False):
    while True:
        ok = try_play(anilist_id, episode, sub_or_dub)
        if not ok:
            if not loop:
                sys.exit(1)
            break
        if not loop:
            break
        try:
            choice = input(f"\n{STYLE_BOLD}[n]ext  [p]rev  [q]uit (ep {episode}): {STYLE_RESET}").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break
        if choice == "n":
            episode += 1
        elif choice == "p":
            episode = max(1, episode - 1)
        else:
            break


def cmd_search(args):
    q = " ".join(args.query)
    results = search_anime(q, page=args.page)
    if not results:
        eprint(f"{STYLE_YELLOW}No results for '{q}'.{STYLE_RESET}")
        sys.exit(1)
    has_fzf = shutil.which("fzf")
    if has_fzf:
        lines = [fmt_compact(m) for m in results]
        result = subprocess.run(
            ["fzf", "--prompt", "Anime> ", "--header", f'Search: "{q}"',
             "--with-nth", "2..", "--delimiter", " ",
             "--bind", "ctrl-c:abort,esc:abort",
             "--height", "80%", "--reverse"],
            input="\n".join(lines), capture_output=True, text=True,
        )
        if result.returncode != 0:
            sys.exit(0)
        sel = result.stdout.strip()
        if not sel:
            sys.exit(0)
        anilist_id = int(sel.split()[0])
        cmd_info(anilist_id, args)
    else:
        for i, m in enumerate(results, 1):
            print(f"{STYLE_CYAN}{i:>3}.{STYLE_RESET} {fmt_compact(m)}")


def cmd_info(anilist_id, args):
    media = get_anime_info(anilist_id)
    if not media:
        eprint(f"{STYLE_RED}ID {anilist_id} not found.{STYLE_RESET}")
        sys.exit(1)
    title = fmt_title(media)
    ep = get_episode_count(media)
    f = media.get("format") or "?"
    y = media.get("seasonYear") or ""
    s = media.get("season") or ""
    print(f"\n{STYLE_BOLD}{title}{STYLE_RESET}")
    print(f"  ID: {anilist_id} | {f} | {ep or '?'} episodes", end="")
    status = media.get("status", "")
    if status == "RELEASING":
        print(f"  {STYLE_GREEN} ● AIRING{STYLE_RESET}", end="")
    print()
    if y: print(f"  {s} {y}")
    edges = media.get("relations", {}).get("edges", [])
    if edges:
        print()
        for e in edges:
            n = e["node"]
            t = f"[{e['relationType'].replace('_',' ').title()}]"
            print(f"  {STYLE_GREEN}{t}{STYLE_RESET} {fmt_compact(n)}")
    print()
    if ep is None:
        print(f"  {STYLE_DIM}(Episode count unknown - specify episode number directly){STYLE_RESET}")
        return

    has_fzf = shutil.which("fzf")
    while True:
        if has_fzf:
            lines = [f"{i:>{len(str(ep))}}" for i in range(1, ep + 1)]
            result = subprocess.run(
                ["fzf", "--prompt", "Episode> ", "--header", f"{title} (1-{ep})",
                 "--bind", "ctrl-c:abort,esc:abort",
                 "--height", "80%", "--reverse"],
                input="\n".join(lines), capture_output=True, text=True,
            )
            if result.returncode != 0:
                break
            sel = result.stdout.strip()
            if not sel:
                continue
            target = int(sel)
            sd = "dub" if args.dub else "sub"
            try_play(anilist_id, target, sd)
        else:
            try:
                c = input(f"{STYLE_BOLD}Episode (1-{ep}, Enter=q): {STYLE_RESET}").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if c == "" or not c.isdigit():
                break
            target = int(c)
            if target < 1 or target > ep:
                eprint(f"{STYLE_RED}Invalid (1-{ep}).{STYLE_RESET}")
                continue
            sd = "dub" if args.dub else "sub"
            try_play(anilist_id, target, sd)


def cmd_interactive(args):
    q = " ".join(args.query) if args.query else None
    if q:
        results = search_anime(q, page=1, per_page=15)
        if not results:
            eprint(f"{STYLE_YELLOW}No results.{STYLE_RESET}")
            sys.exit(1)
        has_fzf = shutil.which("fzf")
        if has_fzf:
            lines = [fmt_compact(m) for m in results]
            result = subprocess.run(
                ["fzf", "--prompt", "Anime> ", "--header", f'Search: "{q}"',
                 "--with-nth", "2..", "--delimiter", " ",
                 "--bind", "ctrl-c:abort,esc:abort",
                 "--height", "80%", "--reverse"],
                input="\n".join(lines), capture_output=True, text=True,
            )
            if result.returncode != 0:
                sys.exit(0)
            sel = result.stdout.strip()
            if not sel:
                sys.exit(0)
            anilist_id = int(sel.split()[0])
            media = get_anime_info(anilist_id)
            if not media:
                eprint(f"{STYLE_RED}ID {anilist_id} not found.{STYLE_RESET}")
                sys.exit(1)
            total = get_episode_count(media)
        else:
            for i, m in enumerate(results, 1):
                print(f"{STYLE_CYAN}{i:>3}.{STYLE_RESET} {fmt_compact(m)}")
            try:
                c = input(f"\n{STYLE_BOLD}Select (1-{len(results)}): {STYLE_RESET}").strip()
            except (EOFError, KeyboardInterrupt):
                print(); sys.exit(0)
            if not c.isdigit() or int(c) < 1 or int(c) > len(results):
                eprint(f"{STYLE_RED}Invalid.{STYLE_RESET}"); sys.exit(1)
            media = results[int(c) - 1]
            anilist_id = media["id"]
            total = get_episode_count(media)
    else:
        anilist_id = args.id
        media = get_anime_info(anilist_id)
        if not media:
            eprint(f"{STYLE_RED}ID {anilist_id} not found.{STYLE_RESET}")
            sys.exit(1)
        total = get_episode_count(media)
        print(f"\n{STYLE_BOLD}{fmt_title(media)}{STYLE_RESET}")

    if total is None:
        try:
            ep = input(f"{STYLE_BOLD}Episode (Enter=1): {STYLE_RESET}").strip()
            ep = int(ep) if ep else 1
        except (EOFError, KeyboardInterrupt):
            print(); sys.exit(0)
        sd = "dub" if args.dub else "sub"
        play(anilist_id, ep, sd, loop=True)
        return

    try:
        sd = input(f"{STYLE_BOLD}Type (sub/dub, Enter=sub): {STYLE_RESET}").strip().lower() or "sub"
    except (EOFError, KeyboardInterrupt):
        print(); sys.exit(0)
    if sd not in ("sub", "dub"):
        sd = "sub"

    has_fzf = shutil.which("fzf")
    title = fmt_title(media)
    while True:
        if has_fzf:
            lines = [f"{i:>{len(str(total))}}" for i in range(1, total + 1)]
            result = subprocess.run(
                ["fzf", "--prompt", "Episode> ", "--header", f"{title} (1-{total})",
                 "--bind", "ctrl-c:abort,esc:abort",
                 "--height", "80%", "--reverse"],
                input="\n".join(lines), capture_output=True, text=True,
            )
            if result.returncode != 0:
                break
            sel = result.stdout.strip()
            if not sel:
                continue
            ep = int(sel)
        else:
            try:
                ep_input = input(f"{STYLE_BOLD}Episode (1-{total}, Enter=q): {STYLE_RESET}").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if ep_input == "" or not ep_input.isdigit():
                break
            ep = int(ep_input)
            if ep < 1 or ep > total:
                eprint(f"{STYLE_RED}Invalid (1-{total}).{STYLE_RESET}")
                continue
        try_play(anilist_id, ep, sd)


def main():
    p = ArgumentParser(
        prog="aniterm",
        description=f"{STYLE_BOLD}aniterm{STYLE_RESET} - stream anime from the terminal",
        formatter_class=RawDescriptionHelpFormatter,
    )
    p.add_argument("command", nargs="*", help="<query> | <id> [ep...] | -i [query] | search <query>")
    p.add_argument("-d", "--dub", action="store_true", help="dub instead of sub")
    p.add_argument("-i", "--interactive", action="store_true", help="interactive mode")
    p.add_argument("-n", "--next", action="store_true", help="prompt for next/prev episode after playback")
    p.add_argument("--page", type=int, default=1, help="search page")

    args = p.parse_args()
    cmd = args.command

    if not cmd:
        p.print_help()
        sys.exit(0)

    if args.interactive:
        args.id = None
        args.query = []
        for c in cmd:
            if c.isdigit() and args.id is None:
                args.id = int(c)
            else:
                args.query.append(c)
        cmd_interactive(args)
        return

    first = cmd[0]

    if first == "search":
        args.query = cmd[1:]
        cmd_search(args)
    elif first.isdigit():
        anilist_id = int(first)
        episodes = [int(x) for x in cmd[1:] if x.isdigit()]
        if episodes:
            sd = "dub" if args.dub else "sub"
            for i, ep in enumerate(episodes):
                loop = args.next and i == len(episodes) - 1
                play(anilist_id, ep, sd, loop=loop)
        else:
            cmd_info(anilist_id, args)
    else:
        args.query = cmd
        cmd_search(args)


if __name__ == "__main__":
    main()

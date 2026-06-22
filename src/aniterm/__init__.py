import json, shutil, subprocess, sys, time, urllib.parse, urllib.request
from argparse import ArgumentParser, RawDescriptionHelpFormatter

ANILIST_API = "https://graphql.anilist.co"
VIDNEST_API = "https://new.vidnest.fun/hianime/anime"
VIDNEST_ALPHABET = "RB0fpH8ZEyVLkv7c2i6MAJ5u3IKFDxlS1NTsnGaqmXYdUrtzjwObCgQP94hoeW+/="

STYLE_BOLD = "\033[1m"
STYLE_DIM = "\033[2m"
STYLE_GREEN = "\033[92m"
STYLE_YELLOW = "\033[93m"
STYLE_BLUE = "\033[94m"
STYLE_MAGENTA = "\033[95m"
STYLE_CYAN = "\033[96m"
STYLE_RED = "\033[91m"
STYLE_RESET = "\033[0m"


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def anilist_query(query, variables=None):
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
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


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


def fetch_episode_sources(anilist_id, episode, sub_or_dub="sub"):
    url = f"{VIDNEST_API}/{anilist_id}/{episode}/{sub_or_dub.lower()}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:137.0) Gecko/20100101 Firefox/137.0",
        "Origin": "https://vidnest.fun",
        "Referer": "https://vidnest.fun/",
    }
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as r:
                return decrypt_vidnest(json.loads(r.read()))
        except urllib.error.HTTPError as e:
            if e.code == 502 and attempt < 2:
                eprint(f"  {STYLE_YELLOW}502, retrying...{STYLE_RESET}")
                time.sleep(2 ** attempt)
                continue
            raise


def make_proxy_url(stream_url):
    proxy_headers = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:137.0) Gecko/20100101 Firefox/137.0",
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.5",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
        "origin": "https://megaplay.buzz",
        "referer": "https://megaplay.buzz/",
    }
    params = urllib.parse.urlencode({
        "url": stream_url,
        "headers": json.dumps(proxy_headers, separators=(",", ":")),
    })
    return f"https://megacloud.animanga.fun/proxy?{params}"


def play_episode(stream_url, title=None):
    if not shutil.which("mpv"):
        eprint(f"{STYLE_RED}mpv not found. Install it first.{STYLE_RESET}")
        sys.exit(1)
    proxy_url = make_proxy_url(stream_url)
    cmd = [
        "mpv", proxy_url,
        "--msg-level=all=info",
        "--ytdl-format=bestvideo+bestaudio/best",
        "--ytdl-raw-options=impersonate=Chrome-142",
    ]
    if title:
        cmd.append(f"--title={title}")
    subprocess.run(cmd)


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


def play(anilist_id, episode, sub_or_dub):
    try:
        data = fetch_episode_sources(anilist_id, episode, sub_or_dub)
    except urllib.error.HTTPError as e:
        eprint(f"{STYLE_RED}Server error: {e.code}{STYLE_RESET}")
        sys.exit(1)
    except Exception as e:
        eprint(f"{STYLE_RED}{e}{STYLE_RESET}")
        sys.exit(1)
    if not data.get("success"):
        eprint(f"{STYLE_RED}{data.get('error', 'Unknown error')}{STYLE_RESET}")
        sys.exit(1)
    sources = data.get("sources", [])
    if not sources or not sources[0].get("file"):
        eprint(f"{STYLE_RED}No video source found.{STYLE_RESET}")
        sys.exit(1)
    url = sources[0]["file"]
    media = get_anime_info(anilist_id)
    title = fmt_title(media) if media else f"Anime {anilist_id}"
    label = f"{title} - Ep {episode} ({sub_or_dub.upper()})"
    print(f"  {STYLE_GREEN}▶{STYLE_RESET} {STYLE_BOLD}{label}{STYLE_RESET}")
    play_episode(url, title=label)


def cmd_search(args):
    q = " ".join(args.query)
    results = search_anime(q, page=args.page)
    if not results:
        eprint(f"{STYLE_YELLOW}No results for '{q}'.{STYLE_RESET}")
        sys.exit(1)
    for i, m in enumerate(results, 1):
        print(f"{STYLE_CYAN}{i:>3}.{STYLE_RESET} {fmt_compact(m)}")


def cmd_info(anilist_id):
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
    print(f"  ID: {anilist_id} | {f} | {ep or '?'} episodes")
    status = media.get("status", "")
    if status == "RELEASING":
        print(f"  {STYLE_GREEN}● AIRING{STYLE_RESET}", end="")
    if y: print(f"  {s} {y}", end="")
    print()
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
    elif ep > 100:
        cols = 8
        step = ep // 100
        ranges = []
        for i in range(1, ep + 1, step):
            end = min(i + step - 1, ep)
            ranges.append(f"{i}-{end}")
        for i in range(0, len(ranges), cols):
            print(f"  {'  '.join(f'{STYLE_GREEN}{r:>8}{STYLE_RESET}' for r in ranges[i:i+cols])}")
    else:
        cols = 8
        for i in range(1, ep + 1):
            print(f"{STYLE_GREEN}{i:>4}{STYLE_RESET}", end="")
            if i % cols == 0:
                print()
        if ep % cols != 0:
            print()
    print(f"\n{STYLE_DIM}Usage: aniterm {anilist_id} <ep>  |  aniterm {anilist_id} <ep> -dub{STYLE_RESET}")


def cmd_interactive(args):
    q = " ".join(args.query) if args.query else None
    if q:
        results = search_anime(q, page=1, per_page=15)
        if not results:
            eprint(f"{STYLE_YELLOW}No results.{STYLE_RESET}")
            sys.exit(1)
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
    else:
        try:
            ep = input(f"{STYLE_BOLD}Episode (1-{total}, Enter=1): {STYLE_RESET}").strip()
            ep = int(ep) if ep else 1
        except (EOFError, KeyboardInterrupt):
            print(); sys.exit(0)
        if ep < 1 or ep > total:
            eprint(f"{STYLE_RED}Invalid (1-{total}).{STYLE_RESET}"); sys.exit(1)
    try:
        sd = input(f"{STYLE_BOLD}Type (sub/dub, Enter=sub): {STYLE_RESET}").strip().lower() or "sub"
    except (EOFError, KeyboardInterrupt):
        print(); sys.exit(0)
    if sd not in ("sub", "dub"):
        sd = "sub"
    play(anilist_id, ep, sd)


def main():
    p = ArgumentParser(
        prog="aniterm",
        description=f"{STYLE_BOLD}aniterm{STYLE_RESET} - stream anime from the terminal",
        formatter_class=RawDescriptionHelpFormatter,
    )
    p.add_argument("command", nargs="*", help="search <query> | <id> [ep...] | -i [query]")
    p.add_argument("-d", "--dub", action="store_true", help="dub instead of sub")
    p.add_argument("-i", "--interactive", action="store_true", help="interactive mode")
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
            for ep in episodes:
                play(anilist_id, ep, sd)
        else:
            cmd_info(anilist_id)
    else:
        args.query = cmd
        cmd_search(args)


if __name__ == "__main__":
    main()

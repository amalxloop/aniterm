# aniterm

Stream anime from your terminal. Uses AniList search and [VidNest](https://vidnest.fun) sources.

## Requirements

- **mpv** — video player
- **yt-dlp** — streaming with Cloudflare bypass
- **curl_cffi** — TLS fingerprint impersonation (`pip install curl_cffi`)
- **python3** — standard library only (no pip deps for the script itself)

## Install

```bash
pip install curl_cffi           # needed by yt-dlp for impersonation
chmod +x aniterm
ln -s "$PWD/aniterm" ~/.local/bin/aniterm  # or copy to PATH
```

## Usage

```
aniterm search <query>           Search anime on AniList
aniterm <id>                     Show info + episode grid + related entries
aniterm <id> <ep>                Play episode (subbed by default)
aniterm <id> <ep> -dub           Play dubbed episode
aniterm -i <query>               Interactive: search -> pick -> play
aniterm <id> -i                  Interactive episode selector
```

### Examples

```bash
aniterm search "cowboy bebop"
aniterm 1                        # list episodes
aniterm 1 1                      # play episode 1
aniterm 21 1000                  # play One Piece episode 1000
aniterm 21 1 -dub                # play dubbed
aniterm -i "attack on titan"     # interactive
```

## How it works

1. **Search** — queries [AniList GraphQL API](https://anilist.co) (no API key needed)
2. **Sources** — fetches encrypted episode data from `new.vidnest.fun/hianime/anime/{id}/{ep}/{sub|dub}`
3. **Decrypt** — response uses custom base64 with alphabet `RB0fpH8ZEyVLkv7c2i6MAJ5u3IKFDxlS1NTsnGaqmXYdUrtzjwObCgQP94hoeW+/=`
4. **Proxy** — HLS stream is proxied through `megacloud.animanga.fun` to bypass CDN restrictions
5. **Play** — launches `mpv` with `yt-dlp` impersonation (`Chrome-142`) for Cloudflare bypass

## Notes

- Episode count for ongoing anime (e.g. One Piece) is derived from `nextAiringEpisode` on AniList
- All episode numbers above ~1000 (like One Piece) are confirmed working on VidNest

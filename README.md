# Aniterm

Stream anime from your terminal.

## Requirements

- **mpv** — video player
- **yt-dlp** — streaming
- **curl_cffi** — `pip install curl_cffi`
- **python3**

## Install

```bash
pip install aniterm           # from PyPI
pip install curl_cffi         # needed by yt-dlp for Cloudflare bypass
```

Or run directly from the repo:

```bash
git clone https://github.com/amalxloop/aniterm.git
pip install curl_cffi
./aniterm/aniterm
```

## Usage

```
aniterm <query>                   Search anime
aniterm <id>                      Show info + episode list
aniterm <id> <ep>                 Play episode (subbed)
aniterm <id> <ep> -dub            Play dubbed episode
aniterm <id> <ep> -n              Next/prev prompt after playback
aniterm -i <query>                Interactive mode
aniterm <id> -i                   Pick episode interactively
```

### Examples

```bash
aniterm cowboy bebop              # search (no keyword needed)
aniterm 1                         # list episodes
aniterm 1 1                       # play episode 1
aniterm 21 1000                   # play One Piece episode 1000
aniterm -i "attack on titan"      # interactive
```

## Notes

- Episode counts for ongoing anime (e.g. One Piece) are derived from AniList's `nextAiringEpisode` data

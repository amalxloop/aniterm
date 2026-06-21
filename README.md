# aniterm

Stream anime from your terminal.

## Requirements

- **mpv** — video player
- **yt-dlp** — streaming
- **curl_cffi** — `pip install curl_cffi`
- **python3**

## Install

```bash
pip install curl_cffi
chmod +x aniterm
ln -s "$PWD/aniterm" ~/.local/bin/aniterm
```

## Usage

```
aniterm search <query>           Search anime
aniterm <id>                     Show info + episode list
aniterm <id> <ep>                Play episode (subbed by default)
aniterm <id> <ep> -dub           Play dubbed episode
aniterm -i <query>               Interactive mode
aniterm <id> -i                  Pick episode interactively
```

### Examples

```bash
aniterm search "cowboy bebop"
aniterm 1                        # list episodes
aniterm 1 1                      # play episode 1
aniterm 21 1000                  # play One Piece episode 1000
aniterm -i "attack on titan"     # interactive
```

## Notes

- Episode counts for ongoing anime (e.g. One Piece) are derived from AniList's `nextAiringEpisode` data

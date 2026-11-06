# Renders demo/logo.gif: demo/ascii.txt centered on a clear screen (same 800x300 frame as find-tool.tape, smaller
# font (9pt: 25x122 terminal) so the 112x18 art fits). Appended to the main demo with:
#   ffmpeg -i demo/find-tool.gif -i demo/logo.gif -filter_complex \
#     "[0:v][1:v]concat=n=2:v=1[v];[v]split[a][b];[a]palettegen[p];[b][p]paletteuse" demo/find-tool-with-logo.gif
Output demo/logo.gif

Set Shell bash
Set FontSize 9
Set LineHeight 1.0
Set Width 800
Set Height 300
Set Padding 20
Set Theme "Catppuccin Mocha"

Hide
Type `export PS1=''; clear; tput civis; python3 -c 'import os, sys; L = [l.rstrip() for l in open(sys.argv[1], encoding="utf-8").read().split("\n")]; L = [l for l in L if l.strip()] and L[next(i for i, l in enumerate(L) if l.strip()):len(L) - next(i for i, l in enumerate(reversed(L)) if l.strip())]; ind = min(len(l) - len(l.lstrip()) for l in L if l.strip()); L = [l[ind:] for l in L]; c, r = os.get_terminal_size(); w = max(map(len, L)); print("\n" * max((r - len(L)) // 2, 0) + "\n".join(" " * max((c - w) // 2, 0) + l for l in L), end="")' demo/ascii.txt; read -s`
Enter
Sleep 1500ms
Show
Sleep 4s

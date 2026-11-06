# Renders demo/find-tool.gif. Run from the repository root: vhs demo/find-tool.tape
# Needs Moss credentials (`moss init`, or a .env with MOSS_PROJECT_ID/KEY) and a built `find-tool` index.
Output demo/find-tool.gif

Set Shell bash
Set FontSize 14
Set Width 800
Set Height 300
Set Padding 20
Set Theme "Catppuccin Mocha"
Set TypingSpeed 40ms
Set WaitPattern /^\$\s*$/
Set WaitTimeout 20s

Hide
Type "export PS1='$ ' PATH=$PWD/plugin/bin:$PATH; [ -f .env ] && { set -a; . ./.env; set +a; }; clear"
Enter
Wait
Show

Type "# Describe the job; get the 5 best-matching installed tools"
Enter
Wait
Type `find-tool "turn a screen recording into an animated webp"`
Enter
Wait
Sleep 4s

Hide
Type "clear"
Enter
Wait
Show
Type `find-tool "measure my internet connection speed"`
Enter
Wait
Sleep 4s

Hide
Type "clear"
Enter
Wait
Show
Type `find-tool "set an organization secret for specific repositories"`
Enter
Wait
Sleep 5s

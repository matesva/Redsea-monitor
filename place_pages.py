import os, re

# Soubory v kořeni ve tvaru  slozka__soubor.ext  se přesunou do  slozka/soubor.ext
# např.  uspesnost__index.html  ->  uspesnost/index.html

pat = re.compile(r"^([A-Za-z0-9._-]+)__(.+)$")
moved = 0
for name in sorted(os.listdir(".")):
    if not os.path.isfile(name):
        continue
    m = pat.match(name)
    if not m or name.startswith("."):
        continue
    folder, rest = m.group(1), m.group(2)
    os.makedirs(folder, exist_ok=True)
    target = os.path.join(folder, rest)
    os.replace(name, target)
    print("přesunuto:", name, "->", target)
    moved += 1
print("Hotovo, přesunuto souborů:", moved)

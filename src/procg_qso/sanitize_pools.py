"""Remove hyphens from pool *data* lines (replace with space, collapse whitespace).
Comment (#) and blank lines are left untouched. Idempotent."""
import re, sys, pathlib

def sanitize_line(s: str) -> str:
    out = s.replace('-', ' ')
    out = re.sub(r'\s{2,}', ' ', out).strip()
    return out

def process(path: pathlib.Path) -> list[tuple[str, str]]:
    changed = []
    lines = path.read_text(encoding='utf-8').splitlines()
    new = []
    for ln in lines:
        if ln.strip() == '' or ln.lstrip().startswith('#'):
            new.append(ln)                      # leave comments/blanks
            continue
        fixed = sanitize_line(ln)
        if fixed != ln:
            changed.append((ln, fixed))
        new.append(fixed)
    if changed:
        path.write_text('\n'.join(new) + '\n', encoding='ascii')
    return changed

pooldir = pathlib.Path(sys.argv[1])
total = 0
for f in sorted(pooldir.glob('*.txt')):
    ch = process(f)
    if ch:
        print(f"\n{f.name}: {len(ch)} line(s) changed")
        for old, new in ch:
            print(f"  - {old!r}\n  + {new!r}")
        total += len(ch)
print(f"\n=== {total} data line(s) sanitized across all pools ===")

"""Check repository Markdown targets; external checks require --online.

Local services, intentional examples and fenced code are not public deployment claims.
This checks reachability, not the truth of a page or mailbox delivery.
"""

import argparse
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def prose(text):
    return re.sub(r"^\s*(`{3,}|~{3,}).*?^\s*\1\s*$", "", text, flags=re.M | re.S)


def anchors(path):
    text = prose(path.read_text(encoding="utf-8"))
    found = set(re.findall(r"(?:id|name)=[\'\"]([^\'\"]+)", text))
    used = Counter()
    for heading in re.findall(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*$", text, flags=re.M):
        heading = re.sub(r"!?\[([^\]]+)\]\([^)]*\)", r"\1", heading)
        slug = re.sub(r"[^\w\-\s]", "", re.sub(r"<[^>]*>", "", heading).lower())
        slug = slug.replace(" ", "-")
        found.add(slug + (f"-{used[slug]}" if used[slug] else ""))
        used[slug] += 1
    return found


def external(url):
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "portfolio-link-check/1"})
        with urllib.request.urlopen(request, timeout=15) as response:
            return "redirected" if response.url != url else "working", response.url
    except urllib.error.HTTPError as error:
        # An authentication/rate-limit/network failure is not proof of a deleted page.
        return ("broken" if error.code in (404, 410) else "unverified"), str(error)
    except (OSError, ValueError) as error:
        return "unverified", str(error)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--online", action="store_true", help="Also request external HTTP targets")
    args = parser.parse_args()
    tracked = (
        subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT
        )
        .decode()
        .split("\0")
    )
    failures = 0
    checked = 0
    urls = set()
    for filename in sorted(set(tracked)):
        path = ROOT / filename
        if path.suffix != ".md" or not path.is_file():
            continue
        text = prose(path.read_text(encoding="utf-8"))
        targets = re.findall(r"\]\(([^\s)]+)(?:\s+[^)]*)?\)", text)
        targets += re.findall(r"^\s*\[[^\]]+\]:\s*(\S+)", text, flags=re.M)
        # Bare HTTP references in documentation also deserve a reachability check.
        targets += re.findall(r"https?://[^\s<>\'\"`)\]}]+", text)
        for target in set(targets):
            target = target.strip("<>").rstrip(".,;")
            parsed = urllib.parse.urlsplit(target)
            if parsed.scheme in ("http", "https"):
                host = parsed.hostname or ""
                if host not in ("localhost", "127.0.0.1", "0.0.0.0", "api") and not re.search(
                    r"YOUR[-_]|example\.|\.invalid", target, flags=re.I
                ):
                    urls.add(target.split("#", 1)[0])
                continue
            if parsed.scheme:
                continue
            resolved = (
                (ROOT / urllib.parse.unquote(parsed.path).lstrip("/"))
                if parsed.path.startswith("/")
                else (path.parent / urllib.parse.unquote(parsed.path) if parsed.path else path)
            )
            checked += 1
            valid = resolved.exists()
            if valid and parsed.fragment and resolved.suffix == ".md":
                valid = urllib.parse.unquote(parsed.fragment) in anchors(resolved)
            if not valid:
                failures += 1
                print(f"broken-local: {filename}: {target}")
    print(f"Local Markdown targets checked: {checked}; broken: {failures}")
    if args.online:
        with ThreadPoolExecutor(max_workers=4) as executor:
            for url, (status, detail) in zip(sorted(urls), executor.map(external, sorted(urls))):
                print(f"{status}: {url} -> {detail}")
                failures += status == "broken"
    else:
        print(f"External HTTP targets collected: {len(urls)}; use --online to request them")
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())

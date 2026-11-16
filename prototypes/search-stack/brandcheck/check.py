"""Screenshots of matchmaker's pages and a check of their controls, before and after a
change to its look (README, "Branding check"). Runs in the image of ./Dockerfile.

    check.py capture OUT URL    screenshots and controls of each page and width into OUT
    check.py compare BEFORE AFTER    one PASS/FAIL line per page and width; exit 1 on a FAIL

A control is what a visitor can operate: links, buttons, fields, and any other element
the page gives a pointer cursor (upstream's example cards are clickable <div>s). For
each: visible, inside the page's width, not covered by another element at its centre,
enabled, reached by the Tab key, and for a text field, typing arrives. compare fails
when a control the baseline had is gone or does worse on one of these, or the page
scrolls sideways where it did not; moves and new or renamed controls are notes, for a
look at the screenshots.
"""

import json
import sys
from pathlib import Path

PAGES = {"landing": "/", "results": "/search?q=ferritin", "chat": "/chat"}
WIDTHS = (1440, 1024, 390)
HEIGHT = 900
MOVE_NOTE_PX = 8  # moves and size changes above this are listed

INVENTORY = """() => {
  const SEL = 'a[href],button,input,textarea,select,[role=button],[role=link],[role=switch],'
    + '[role=checkbox],[role=tab],[tabindex]:not([tabindex="-1"])';
  const isCtl = el => el.matches(SEL) || getComputedStyle(el).cursor === 'pointer';
  const inCtl = el => { for (let p = el.parentElement; p; p = p.parentElement) if (isCtl(p)) return true; return false; };
  const name = el => (el.getAttribute('aria-label') || el.getAttribute('alt')
    || el.querySelector('img[alt]')?.getAttribute('alt') || el.getAttribute('placeholder')
    || el.innerText || el.getAttribute('title') || el.value || '').trim().replace(/\\s+/g, ' ').slice(0, 60);
  return [...document.querySelectorAll('body *')].filter(el => isCtl(el) && !inCtl(el)).map((el, i) => {
    el.dataset.bc = i;
    const r = el.getBoundingClientRect();
    return {id: i, tag: el.tagName.toLowerCase(), name: name(el),
      box: [Math.round(r.x), Math.round(r.y + scrollY), Math.round(r.width), Math.round(r.height)],
      visible: r.width > 0 && r.height > 0 && el.checkVisibility({opacityProperty: true, visibilityProperty: true}),
      in_width: r.left >= 0 && r.right <= document.documentElement.clientWidth,
      enabled: !el.disabled && el.getAttribute('aria-disabled') !== 'true',
      text_field: el.matches('textarea, input:not([type]), input[type=text], input[type=search]')};
  });
}"""

UNCOVERED = """id => {
  const el = document.querySelector(`[data-bc="${id}"]`);
  if (!el) return null;
  el.scrollIntoView({block: 'center', inline: 'center', behavior: 'instant'});
  const r = el.getBoundingClientRect();
  const t = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
  return !!t && (el === t || el.contains(t));
}"""

FOCUSED = "() => document.activeElement?.closest('[data-bc]')?.dataset.bc ?? null"


def capture(out: Path, url: str) -> None:
    from playwright.sync_api import sync_playwright

    out.mkdir(parents=True, exist_ok=True)
    result = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for page_name, path in PAGES.items():
            for width in WIDTHS:
                key = f"{page_name}-{width}"
                page = browser.new_page(viewport={"width": width, "height": HEIGHT})
                page.goto(url + path, wait_until="load")
                try:  # the results stream in; the chat page may keep a connection open
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
                page.wait_for_timeout(1000)
                page.screenshot(path=out / f"{key}.png", full_page=True)
                controls = page.evaluate(INVENTORY)
                for c in controls:
                    c["uncovered"] = c["visible"] and page.evaluate(UNCOVERED, c["id"])
                page.evaluate("window.scrollTo(0, 0)")
                # Tab from the top, before anything had focus: the order focus visits
                order: list[str] = []
                for _ in range(300):
                    page.keyboard.press("Tab")
                    bc = page.evaluate(FOCUSED)
                    if bc is not None and bc in order and bc == order[0]:
                        break  # round the page once
                    if bc is not None and bc not in order:
                        order.append(bc)
                page.evaluate("document.activeElement?.blur()")
                for c in controls:
                    c["tab"] = (
                        order.index(str(c["id"])) + 1 if str(c["id"]) in order else None
                    )
                    field = page.locator(f'[data-bc="{c["id"]}"]')
                    if (
                        c["visible"]
                        and c["enabled"]
                        and c["text_field"]
                        and field.count()
                    ):
                        field.fill("ferritin")
                        c["typing"] = field.input_value() == "ferritin"
                        field.fill("")
                result[key] = {
                    "sideways": page.evaluate(
                        "document.documentElement.scrollWidth > document.documentElement.clientWidth"
                    ),
                    "height": page.evaluate("document.documentElement.scrollHeight"),
                    "controls": controls,
                }
                page.close()
        browser.close()
    (out / "controls.json").write_text(json.dumps(result, indent=1))
    print(f"captured {len(result)} pages into {out}")


def match(before: list[dict], after: list[dict]) -> tuple[list, list, list]:
    """Pairs of (before, after) by tag and name, then the rest by tag and nearest place
    (renamed); and what is left over on either side."""
    pairs, left = [], list(after)
    rest = []
    for b in before:
        a = next(
            (a for a in left if (a["tag"], a["name"]) == (b["tag"], b["name"])), None
        )
        if a:
            pairs.append((b, a))
            left.remove(a)
        else:
            rest.append(b)
    gone = []
    for b in rest:
        near = [a for a in left if a["tag"] == b["tag"]]
        dist = lambda a: abs(a["box"][0] - b["box"][0]) + abs(a["box"][1] - b["box"][1])  # noqa: E731
        a = min(near, key=dist, default=None)
        if a and dist(a) <= 200:
            pairs.append((b, a))
            left.remove(a)
        else:
            gone.append(b)
    return pairs, gone, left


def label(c: dict) -> str:
    return f'{c["tag"]} "{c["name"]}"'


def compare(before_dir: Path, after_dir: Path) -> int:
    before = json.loads((before_dir / "controls.json").read_text())
    after = json.loads((after_dir / "controls.json").read_text())
    failed = 0
    for key, b_page in before.items():
        a_page = after.get(key)
        if a_page is None:
            print(f"FAIL  {key}: not captured after")
            failed = 1
            continue
        fails, notes, known, down = [], [], [], []
        if a_page["sideways"] and not b_page["sideways"]:
            fails.append("the page now scrolls sideways")
        pairs, gone, new = match(b_page["controls"], a_page["controls"])
        fails += [f"gone: {label(b)}" for b in gone if b["visible"]]
        for b, a in pairs:
            if (b["tag"], b["name"]) != (a["tag"], a["name"]):
                notes.append(f"renamed: {label(b)} -> {label(a)}")
            if not b["visible"]:
                continue
            for prop, what in [
                ("visible", "hidden"),
                ("in_width", "outside the page's width"),
                ("uncovered", "covered by another element"),
                ("enabled", "disabled"),
                ("typing", "typing does not arrive"),
            ]:
                if b.get(prop) and not a.get(prop):
                    fails.append(f"{what}: {label(a)}")
            if b["tab"] and not a["tab"]:
                fails.append(f"no longer reached by Tab: {label(a)}")
            elif not b["tab"]:
                known.append(f"not reached by Tab, before and after: {label(a)}")
            d = [x - y for x, y in zip(a["box"], b["box"])]
            if max(abs(d[0]), abs(d[2]), abs(d[3])) > MOVE_NOTE_PX:
                notes.append(
                    f"moved {d[0]:+d},{d[1]:+d}, size {d[2]:+d}x{d[3]:+d}: {label(a)}"
                )
            elif abs(d[1]) > MOVE_NOTE_PX:
                down.append(d[1])  # only up or down: something above it changed height
        if down:
            notes.append(
                f"{len(down)} controls only moved up or down, {min(down):+d} to {max(down):+d} px"
            )
        notes += [f"new: {label(a)}" for a in new if a["visible"]]
        if a_page["height"] != b_page["height"]:
            notes.append(f"page height {b_page['height']} -> {a_page['height']}")
        print(f"{'FAIL' if fails else 'PASS'}  {key}: {len(pairs)} controls")
        for line in fails + notes + known:
            print(f"        {line}")
        failed |= bool(fails)
    return failed


if __name__ == "__main__":
    cmd, *args = sys.argv[1:]
    if cmd == "capture":
        capture(Path(args[0]), args[1].rstrip("/"))
    elif cmd == "compare":
        sys.exit(compare(Path(args[0]), Path(args[1])))
    else:
        sys.exit(f"unknown command {cmd}")

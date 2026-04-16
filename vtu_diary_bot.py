"""
VTU Internyet Diary Automation Bot (Ollama / local AI version)
--------------------------------------------------------------
Requirements:  pip install playwright python-dotenv requests
               + Ollama running with llama3.2 pulled

Usage:
    python vtu_diary_bot.py
"""

import os, sys, json, requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ── Config ───────────────────────────────────────────────────────────────────
load_dotenv("config.env")

VTU_USERNAME  = os.getenv("VTU_USERNAME")
VTU_PASSWORD  = os.getenv("VTU_PASSWORD")
OLLAMA_URL    = os.getenv("OLLAMA_URL",   "http://localhost:11434")
OLLAMA_MODEL  = os.getenv("OLLAMA_MODEL", "llama3.2")
PORTAL_URL    = "https://vtu.internyet.in/sign-in"


# ── Step 1: Collect input ────────────────────────────────────────────────────
def get_study_notes() -> str:
    print("\n" + "="*60)
    print("  VTU Internyet Diary Bot  (powered by Ollama)")
    print("="*60)
    print("\nPaste what you studied / worked on today.")
    print("When done, type DONE on a new line and press Enter.\n")
    lines = []
    while True:
        line = input()
        if line.strip().upper() == "DONE":
            break
        lines.append(line)
    notes = "\n".join(lines).strip()
    if not notes:
        print("No notes entered. Exiting.")
        sys.exit(0)
    return notes


def get_hours() -> float:
    while True:
        raw = input("\nHours worked today? (0–24, steps of 0.25 — e.g. 8, 7.5): ").strip()
        try:
            h = float(raw)
            if 0 <= h <= 24 and round(h * 4) == h * 4:
                return h
            print("Must be 0–24 in 0.25 steps.")
        except ValueError:
            print("Invalid — try again.")


# ── Step 2: Generate fields via Ollama ───────────────────────────────────────
def check_ollama():
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        models = [m["name"] for m in r.json().get("models", [])]
        matched = [m for m in models if OLLAMA_MODEL.split(":")[0] in m]
        if not matched:
            print(f"[Warning] Model '{OLLAMA_MODEL}' not found in Ollama.")
            print(f"  Run:  ollama pull {OLLAMA_MODEL}")
            sys.exit(1)
    except requests.exceptions.ConnectionError:
        print("[Error] Ollama is not running.")
        print("  - Mac/Windows: open the Ollama app")
        print("  - Linux: run  ollama serve  in another terminal")
        sys.exit(1)


def generate_diary_fields(notes: str) -> dict:
    import re
    check_ollama()
    print(f"\n[AI] Generating diary fields using {OLLAMA_MODEL}...")
    print("     (first run may be slow — model is warming up)\n")

    prompt = f"""You are a VTU internship diary assistant. Given a student's raw notes, generate professional diary entries.

Student notes:
\"\"\"{notes}\"\"\"

Reply ONLY with a valid JSON object. No markdown, no explanation, nothing else before or after the JSON.
ALL values must be plain strings — do NOT use JSON arrays for learnings, work_summary, or blockers.

Follow this exact format:
{{
  "work_summary": "2-3 sentence professional summary. Past tense. Max 380 characters.",
  "learnings": "• Point one. • Point two. • Point three. • Point four.",
  "blockers": "No blockers encountered today.",
  "skills": ["Skill1", "Skill2", "Skill3"]
}}

Important rules:
- learnings must be a single plain string with bullet points joined together using • symbol, NOT a JSON array
- work_summary must be a plain string, NOT a list
- skills must be a JSON array of 3-6 specific technical skill names from the notes"""

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1}
    }

    try:
        resp = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=120)
        resp.raise_for_status()
        raw = resp.json().get("response", "").strip()
    except requests.exceptions.Timeout:
        print("[Error] Ollama timed out. Try a smaller model like llama3.2:1b")
        sys.exit(1)

    # Strip markdown fences if present
    if "```" in raw:
        parts = raw.split("```")
        for part in parts:
            if part.startswith("json"):
                raw = part[4:].strip()
                break
            elif "{" in part:
                raw = part.strip()
                break

    # Extract JSON block
    start = raw.find("{")
    end   = raw.rfind("}") + 1
    if start != -1 and end > start:
        raw = raw[start:end]

    # Fix: if learnings/work_summary is a JSON array of strings, convert to single string
    def fix_array_field(text, key):
        pattern = rf'"{key}":\s*\[([^\]]*)\]'
        def replacer(m):
            items = re.findall(r'"([^"]*)"', m.group(1))
            joined = " ".join(f"• {item.strip().lstrip('•').strip()}" for item in items if item.strip())
            return f'"{key}": "{joined}"'
        return re.sub(pattern, replacer, text, flags=re.DOTALL)

    for field in ("learnings", "work_summary", "blockers"):
        raw = fix_array_field(raw, field)

    try:
        fields = json.loads(raw)
    except json.JSONDecodeError:
        print("[Error] Could not parse AI response. Raw output:\n", raw)
        print("\nFalling back to manual entry...")
        return manual_entry()

    # Final safety: if model still returned a list, join it
    for key in ("learnings", "work_summary", "blockers"):
        if isinstance(fields.get(key), list):
            fields[key] = " ".join(f"• {str(x).strip().lstrip('•').strip()}" for x in fields[key])

    return fields


def manual_entry() -> dict:
    print("\nEnter fields manually:\n")
    return {
        "work_summary": input("Work Summary:\n> ").strip(),
        "learnings":    input("\nLearnings / Outcomes:\n> ").strip(),
        "blockers":     input("\nBlockers / Risks:\n> ").strip(),
        "skills":       [s.strip() for s in input("\nSkills (comma-separated):\n> ").split(",")]
    }


# ── Step 3: Review & confirm ─────────────────────────────────────────────────
def confirm_fields(fields: dict, hours: float) -> dict:
    print("\n" + "-"*60)
    print("  GENERATED DIARY FIELDS — Review")
    print("-"*60)

    for key, label, limit in [
        ("work_summary", "Work Summary",        2000),
        ("learnings",    "Learnings/Outcomes",  2000),
        ("blockers",     "Blockers/Risks",       1000),
    ]:
        val = fields.get(key, "")
        print(f"\n[{label}]  ({len(val)}/{limit} chars)")
        print(val)

    print(f"\n[Skills]  {', '.join(fields.get('skills', []))}")
    print(f"[Hours]   {hours}")
    print()

    if input("Proceed with these fields? (y/n) [y]: ").strip().lower() == "n":
        print("Edit below — press Enter to keep existing value.\n")
        for key, label, _ in [
            ("work_summary", "Work Summary",       None),
            ("learnings",    "Learnings/Outcomes", None),
            ("blockers",     "Blockers/Risks",      None),
        ]:
            v = input(f"{label}:\n> ").strip()
            if v:
                fields[key] = v
        sk = input("Skills (comma-separated):\n> ").strip()
        if sk:
            fields["skills"] = [s.strip() for s in sk.split(",")]

    return fields


# ── Step 4: Browser automation ───────────────────────────────────────────────
def smart_fill(page, selectors: str, value: str, label: str):
    """Try to fill a field; pause for manual input if not found."""
    try:
        el = page.locator(selectors).first
        el.wait_for(timeout=6000)
        el.click()
        el.fill(value)
        print(f"  ✓ {label}")
    except PWTimeout:
        print(f"  ✗ Could not auto-find '{label}' field.")
        print(f"    Paste this manually in the browser:\n\n{value}\n")
        input("    Press Enter when done...")


def fill_diary(fields: dict, hours: float):
    print("\n[Browser] Launching Chromium...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=250)
        page    = browser.new_page(viewport={"width": 1280, "height": 900})

        # ── Login ──────────────────────────────────────────────────────────
        print(f"[Browser] Opening {PORTAL_URL}")
        page.goto(PORTAL_URL, wait_until="networkidle")

        try:
            # Wait for the email field to be visible
            page.wait_for_selector("input[autocomplete='email']", timeout=15000)

            # Fill email — click 3 times to select all, then type
            email_field = page.locator("input[autocomplete='email']")
            email_field.click(click_count=3)
            email_field.fill(VTU_USERNAME)

            # Fill password
            password_field = page.locator("input#password")
            password_field.click(click_count=3)
            password_field.fill(VTU_PASSWORD)

            # Small pause to let any JS validation settle
            page.wait_for_timeout(500)

            # Click Sign In button
            page.locator("button[type='submit']").click()

            # Wait for redirect to dashboard after login
            page.wait_for_url("**/dashboard**", timeout=15000)
            print("  ✓ Logged in successfully")
        except PWTimeout:
            print("  ✗ Login timed out or failed.")
            print("    Check your credentials in config.env")
            print("    OR log in manually in the browser window.")
            input("    Press Enter once you are logged in...")

        # ── Navigate to diary ──────────────────────────────────────────────
        print("[Browser] Navigating to Work Diary...")
        try:
            page.locator(
                "a:has-text('Diary'), a:has-text('Work Diary'), "
                "a:has-text('Daily Diary'), nav >> text=Diary"
            ).first.click(timeout=8000)
            page.wait_for_load_state("networkidle")
            print("  ✓ On diary page")
        except PWTimeout:
            print("  ✗ Could not find Diary link.")
            print("    Navigate to the Work Diary section manually.")
            input("    Press Enter once you are on the diary page...")

        # ── Add new entry if button exists ─────────────────────────────────
        try:
            page.locator(
                "button:has-text('Add'), button:has-text('New Entry'), "
                "button:has-text('Add Entry'), a:has-text('Add Entry')"
            ).first.click(timeout=5000)
            page.wait_for_load_state("networkidle")
            print("  ✓ Opened new entry form")
        except PWTimeout:
            pass  # Form may already be visible

        # ── Fill each field ────────────────────────────────────────────────
        print("\n[Browser] Filling form fields...")

        smart_fill(page,
            "textarea[placeholder*='work' i], textarea[name*='summary' i], "
            "textarea[name*='work' i], textarea[id*='summary' i], textarea[id*='work' i]",
            fields["work_summary"], "Work Summary")

        # Hours — handle both number input and range slider
        try:
            h_el = page.locator(
                "input[type='number'][name*='hour' i], input[type='number'][id*='hour' i], "
                "input[name*='hour' i], input[id*='hour' i]"
            ).first
            h_el.wait_for(timeout=5000)
            h_el.fill(str(hours))
            print(f"  ✓ Hours ({hours})")
        except PWTimeout:
            try:
                slider = page.locator("input[type='range']").first
                slider.wait_for(timeout=3000)
                slider.fill(str(hours))
                print(f"  ✓ Hours slider ({hours})")
            except PWTimeout:
                print(f"  ✗ Could not set hours. Set it manually to: {hours}")
                input("    Press Enter when done...")

        smart_fill(page,
            "textarea[name*='learn' i], textarea[id*='learn' i], "
            "textarea[placeholder*='learn' i], textarea[name*='outcome' i], "
            "textarea[id*='outcome' i], textarea[placeholder*='outcome' i]",
            fields["learnings"], "Learnings / Outcomes")

        smart_fill(page,
            "textarea[name*='block' i], textarea[id*='block' i], "
            "textarea[placeholder*='block' i], textarea[name*='risk' i], "
            "textarea[id*='risk' i]",
            fields["blockers"], "Blockers / Risks")

        # ── Skills (tag input) ─────────────────────────────────────────────
        print("  → Adding skills...")
        try:
            skill_input = page.locator(
                "input[placeholder*='skill' i], input[name*='skill' i], input[id*='skill' i]"
            ).first
            skill_input.wait_for(timeout=5000)
            for skill in fields.get("skills", []):
                skill_input.click()
                skill_input.fill(skill)
                page.wait_for_timeout(300)
                page.keyboard.press("Enter")
                page.wait_for_timeout(400)
            print(f"  ✓ Skills: {', '.join(fields.get('skills', []))}")
        except PWTimeout:
            print("  ✗ Could not find Skills input. Add manually:")
            print("   ", ", ".join(fields.get("skills", [])))
            input("    Press Enter when done...")

        # ── Submit ─────────────────────────────────────────────────────────
        print("\n[Browser] All fields filled! Check the browser window.")
        if input("\nSubmit the diary entry now? (y/n) [y]: ").strip().lower() != "n":
            try:
                page.locator(
                    "button[type='submit'], button:has-text('Submit'), "
                    "button:has-text('Save'), button:has-text('Add')"
                ).first.click(timeout=5000)
                page.wait_for_load_state("networkidle")
                print("\n[Done] ✓ Diary entry submitted successfully!")
            except PWTimeout:
                print("  ✗ Could not find submit button — click it manually.")
                input("    Press Enter after submitting...")
        else:
            print("Skipped submission. Submit manually in the browser.")
            input("Press Enter to close the browser...")

        browser.close()


# ── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    missing = [k for k, v in {
        "VTU_USERNAME": VTU_USERNAME,
        "VTU_PASSWORD": VTU_PASSWORD
    }.items() if not v]

    if missing:
        print(f"[Error] Missing in config.env: {', '.join(missing)}")
        sys.exit(1)

    notes  = get_study_notes()
    hours  = get_hours()
    fields = generate_diary_fields(notes)
    fields = confirm_fields(fields, hours)
    fill_diary(fields, hours)
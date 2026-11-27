"""FL-21c: a taken consultation time is said in words ("taken" / "محجوز"), is disabled and cannot be chosen.

The API already sends `slots` with `available` true or false (test_site_settings.py checks that shape and that the old
`busy` list stays). These tests check the booking grid in the frontend source, because the repo has no browser test
runner for it (shortcut: a source check, not a rendered one; add a component test when a runner exists).
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
INTAKE = (ROOT / "frontend" / "components" / "Intake.tsx").read_text()
GRID = INTAKE.split("taken:!s.available", 1)[1].split("</button>)}", 1)[0]


def test_a_slot_the_api_marks_unavailable_is_taken_and_the_old_busy_list_still_counts():
    assert "taken:!s.available||busy.includes(s.time)" in INTAKE
    assert "taken:busy.includes(x)" in INTAKE  # the fixed list used when the API sends no slots


def test_a_taken_slot_is_disabled_not_focusable_and_cannot_be_chosen():
    assert "aria-disabled={taken}" in GRID and "disabled={taken}" in GRID
    assert "tabIndex={taken?-1:undefined}" in GRID
    assert "onClick={()=>{if(!taken)setTime(x);}}" in GRID  # even a forced click does not set the time


def test_a_taken_slot_says_taken_in_english_and_arabic_in_text_not_only_colour():
    assert "lang?'محجوز':'taken'" in GRID
    assert "booked" not in GRID


def test_a_time_that_becomes_taken_is_dropped_so_it_cannot_be_submitted():
    assert "slots.some(s=>s.time===time&&s.available)" in INTAKE
    assert "if(wantsMeeting&&(!date||!time))" in INTAKE  # no time, no submit

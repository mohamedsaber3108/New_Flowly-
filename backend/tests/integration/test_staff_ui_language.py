"""FL-09c: the team's sign-in texts in Arabic and English, and the code box only after the server asks for a code.

There is no browser test runner here, so the /team console is checked by reading its source; the admin sign-in page
is checked by rendering it.
"""

from pathlib import Path

import pytest
from django.conf import settings
from django.test import Client

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[3]
CONSOLE = (ROOT / "frontend" / "components" / "TeamConsole.tsx").read_text()


def login_page(query=""):
    return Client().get(f"/{settings.ADMIN_URL}login/{query}").content.decode()


# --- Django admin sign-in page ----------------------------------------------------------------------


def test_the_session_ended_notice_is_in_english_and_arabic_and_english_is_the_default():
    html = login_page("?expired=1")
    assert 'class="fl-en" lang="en">Your session ended after a period of inactivity' in html
    assert 'class="fl-ar" lang="ar" dir="rtl">انتهت جلستك' in html
    # the page picks the language in the browser, from the same setting as the site; the server sends English
    assert "localStorage.getItem('flowly-language') === 'ar'" in html
    assert 'data-flowly-lang="ar"' not in html.split("<body", 1)[1]  # nothing is hidden on the server side
    assert 'html:not([data-flowly-lang="ar"]) .fl-ar' in html  # Arabic is hidden unless the site language is Arabic


def test_the_enrol_link_has_arabic_text_too_and_points_to_the_same_page():
    html = login_page()
    assert html.count('href="/account/mfa/enroll/"') == 2
    assert "Set up two-step verification" in html and "فعّل التحقق بخطوتين" in html


def test_without_the_expired_flag_there_is_no_session_notice():
    assert "انتهت جلستك" not in login_page()


# --- /team console ----------------------------------------------------------------------------------


def test_the_team_console_follows_the_site_language_right_to_left_in_arabic():
    assert "export default function TeamConsole({lang=0}:{lang?:number})" in CONSOLE
    assert "dir={lang?'rtl':'ltr'}" in CONSOLE
    app = (ROOT / "frontend" / "components" / "FlowlyApp.tsx").read_text()
    assert "<TeamConsole lang={lang}/>" in app  # the same language setting as the rest of the site


@pytest.mark.parametrize(
    "arabic",
    [
        "دخول الفريق",  # sign-in heading
        "كلمة المرور",
        "رمز التحقق",  # code
        "تسجيل الدخول",  # sign in
        "فعّله من هنا",  # enrol link text
        "تم تسجيل خروجك.",  # signed out
        "تم تسجيل خروجك بعد ٣٠ دقيقة بلا نشاط.",  # session_idle
        "وصلت جلستك إلى حدّها الأقصى، وهو ٨ ساعات.",  # session_expired
        "انتهت جلستك.",  # any other end
        "سجّل الدخول من جديد",  # a way back in
        "ستنتهي جلستك بعد حوالي",  # expiry notice
        "ابقَ مسجّلًا",  # stay signed in
        "البريد أو كلمة المرور غير صحيحة.",  # a server message
        "رمز التحقق غير صحيح.",
    ],
)
def test_the_team_console_has_the_arabic_text(arabic):
    assert arabic in CONSOLE


def test_the_code_box_appears_only_after_the_server_asks_for_a_code():
    assert "{needsCode&&<label" in CONSOLE  # not drawn until needed
    assert "useState(false)" in CONSOLE and "[needsCode,setNeedsCode]" in CONSOLE
    assert "d.errors?.code==='mfa_required'||d.errors?.code==='mfa_invalid'" in CONSOLE
    assert "setNeedsCode(true)" in CONSOLE and "setNeedsCode(false)" in CONSOLE  # shown, then hidden after sign-in
    # the old always-visible box (and its English-only label) is gone
    assert "if you have two-step verification" not in CONSOLE


def test_codes_addresses_and_references_stay_left_to_right_in_arabic():
    assert CONSOLE.count('dir="ltr"') >= 8  # email, password, code, token boxes; references and addresses in <bdi>
    assert '<pre dir="ltr">' in CONSOLE
    assert '<bdi dir="ltr">{selected.email}</bdi>' in CONSOLE
    # the code box also takes recovery codes (letters and a dash), so a phone must be able to type them
    code_box = CONSOLE.split('autoComplete="one-time-code"', 1)[1].split("/>", 1)[0]
    assert 'inputMode="numeric"' not in CONSOLE
    assert 'inputMode="text"' in CONSOLE.split('autoComplete="one-time-code"', 1)[0][-80:]
    assert 'autoCapitalize="off"' in code_box and "spellCheck={false}" in code_box


def test_request_kind_and_audience_are_shown_in_arabic():
    assert "const kindAr:Record<string,string>={discovery:" in CONSOLE
    assert "const audienceAr:Record<string,string>={business:" in CONSOLE
    assert "{kl(selected.kind)} · {al(selected.audience)}" in CONSOLE and "{al(r.audience)}" in CONSOLE
    assert "{selected.kind}" not in CONSOLE and "{r.audience}" not in CONSOLE  # no raw English word is left


def test_the_server_messages_a_team_member_can_meet_are_translated_in_one_table():
    for message in (
        "Invalid email or password.",
        "Enter the verification code from your authenticator app, or a recovery code.",
        "That verification code is not valid.",
        "Too many failed sign-in attempts. Try again in 15 minutes.",
    ):
        assert f"'{message}':'" in CONSOLE, message

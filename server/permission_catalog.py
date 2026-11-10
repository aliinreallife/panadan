"""Persian human-readable permissions and predefined access group templates.

This module defines PRESENTATION ONLY, not a new authorization subsystem.
Actual authorization remains enforced by server.security permissions() in
SQLite/PostgreSQL, browser sessions and scoped REST/MCP bearer tokens.

An access group is an explicit one-time preset: selecting it copies its
capabilities into that user's grants. Later edits do NOT silently change
other users. Existing accounts and saved grants are left untouched.
"""
from __future__ import annotations

# Preserve the ordering: lower-risk capabilities first, elevated last.
PERMISSION_CATEGORIES = (
    {
        "id": "safe",
        "label": "کم‌خطر",
        "description": "دسترسی به آمار تجمیعی، بدون جزئیات تماس یا متن مکالمه.",
        "items": (
            {"id": "metrics:read", "label": "مشاهده آمار",
             "description": "گزارش‌ها و شاخص‌های تجمیعی، بدون دریافت جزئیات محرمانه تماس."},
        ),
    },
    {
        "id": "internal",
        "label": "داخلی",
        "description": "اطلاعات کاری روزمره؛ همچنان مختص افراد مجاز سازمان.",
        "items": (
            {"id": "calls:read", "label": "فهرست تماس‌ها",
             "description": "دیدن فهرست و اطلاعات غیرحساس هر تماس؛ شامل متن کامل و اطلاعات محرمانه نیست."},
        ),
    },
    {
        "id": "confidential",
        "label": "محرمانه",
        "description": "شامل اطلاعات حساس مشتری یا مکالمه؛ فقط برای افراد دارای نیاز کاری.",
        "items": (
            {"id": "calls:sensitive", "label": "جزئیات حساس تماس",
             "description": "دسترسی به جزئیات حساس رکورد تماس؛ نیازمند مجوز فهرست تماس‌ها."},
            {"id": "calls:transcript:read", "label": "تحلیل متن مکالمه",
             "description": "دسترسی به متن مکالمه از طریق مسیر جداگانهٔ AI؛ نیازمند مجوز تماس‌ها و ثبت حسابرسی."},
        ),
    },
    {
        "id": "integrations",
        "label": "اتصال و یکپارچه‌سازی",
        "description": "دسترسی به ابزارهای بیرونی؛ می‌تواند دامنهٔ استفاده از داده‌ها را افزایش دهد.",
        "items": (
            {"id": "mcp:use", "label": "استفاده از MCP",
             "description": "اتصال به ابزارهای MCP با مجوزهای خود کاربر؛ نیازمند دسترسی تماس‌ها یا آمار."},
        ),
    },
    {
        "id": "administration",
        "label": "مدیریتی",
        "description": "اختیارات مدیریت کل سامانه؛ فقط برای نقش مدیر کل.",
        "items": (
            {"id": "tokens:manage", "label": "مدیریت توکن‌ها",
             "description": "صدور، مشاهدهٔ فراداده و ابطال توکن‌های دسترسی؛ مختص مدیر کل."},
            {"id": "users:manage", "label": "مدیریت کاربران و مجوزها",
             "description": "ایجاد و ویرایش کاربران و کنترل دسترسی‌ها؛ مختص مدیر کل."},
        ),
    },
)

# Groups are presets, NOT automatically inherited dynamic memberships.
# Defaults are deliberately non-privileged; confidential access is opt-in.
PERMISSION_GROUPS = (
    {
        "id": "metrics",
        "label": "فقط آمار",
        "description": "شاخص‌های تجمیعی، بدون دسترسی به تماس‌ها.",
        "grants": ("metrics:read",),
    },
    {
        "id": "reader",
        "label": "مشاهده تماس‌ها",
        "description": "فهرست و اطلاعات غیرحساس تماس‌ها.",
        "grants": ("calls:read",),
    },
    {
        "id": "analyst",
        "label": "تحلیل‌گر استاندارد",
        "description": "آمار و تماس‌ها به‌همراه اتصال MCP با مجوزهای محدود.",
        "grants": ("calls:read", "metrics:read", "mcp:use"),
    },
    {
        "id": "confidential",
        "label": "تحلیل‌گر محرمانه",
        "description": "آمار، تماس‌ها و جزئیات حساس؛ بدون اتصال MCP.",
        "grants": ("calls:read", "metrics:read", "calls:sensitive"),
    },
    {
        "id": "transcript",
        "label": "بررسی مکالمات",
        "description": "تحلیل‌گر مجاز به خواندن متن مکالمه؛ بدون جزئیات حساس دیگر.",
        "grants": ("calls:read", "metrics:read", "calls:transcript:read"),
    },
)

ROLE_RECOMMENDED_GROUP = {
    "analyst": "analyst",
    "reader": "reader",
    "metrics": "metrics",
}
ADMIN_ONLY = frozenset({"users:manage", "tokens:manage"})
CONFIDENTIAL = frozenset({"calls:sensitive", "calls:transcript:read"})


def matching_group(role: str, capabilities: set[str]) -> str:
    if role == "admin":
        return "admin"
    for group in PERMISSION_GROUPS:
        if capabilities == set(group["grants"]):
            return str(group["id"])
    return "custom"


def catalog_capabilities() -> set[str]:
    return {
        item["id"] for category in PERMISSION_CATEGORIES
        for item in category["items"]
    }


def group_options() -> list[dict]:
    """Send JSON-friendly fixed preset values to the admin-only template."""
    return [
        {"id": group["id"], "label": group["label"],
         "description": group["description"],
         "grants": list(group["grants"])}
        for group in PERMISSION_GROUPS
    ]

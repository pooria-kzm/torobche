from django import template

register = template.Library()


@register.filter
def price(value):
    """Render whole-number prices with western thousands separators."""
    if value in (None, ""):
        return ""
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return value

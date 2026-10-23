from django import template


register = template.Library()


@register.filter
def capitalize(value):
    if not value:
        return value
    name, separator, identifier = str(value).partition(" · ")
    capitalized_name = name.title()
    if separator:
        return f"{capitalized_name}{separator}{identifier.replace('Dni', 'DNI')}"
    return capitalized_name


@register.filter
def signed_class(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if number < 0:
        return "metric-negative"
    if number > 0:
        return "metric-positive"
    return ""

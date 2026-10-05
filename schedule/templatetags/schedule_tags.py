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

from functools import wraps

from django.http import HttpResponseForbidden

READONLY_GROUP = "Solo lectura"
READONLY_MESSAGE = "Tu cuenta es de solo lectura."


def user_can_edit(user):
    """Indica si la cuenta puede crear o modificar datos.

    El superusuario siempre puede. El resto de cuentas puede salvo que
    pertenezcan al grupo ``Solo lectura``.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    return not user.groups.filter(name=READONLY_GROUP).exists()


def edit_required(view):
    """Bloquea las acciones de escritura para las cuentas de solo lectura."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if user_can_edit(request.user):
            return view(request, *args, **kwargs)
        return HttpResponseForbidden(READONLY_MESSAGE)

    return wrapper

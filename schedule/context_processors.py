from .permissions import user_can_edit


def permissions(request):
    """Expone ``can_edit`` a las plantillas para ocultar los controles de edición."""
    return {"can_edit": user_can_edit(getattr(request, "user", None))}

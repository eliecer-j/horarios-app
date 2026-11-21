from functools import wraps
from urllib.parse import quote

from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse


def app_login_required(view):
    """Exige sesión iniciada y respeta las peticiones HTMX.

    En peticiones normales redirige a la página de login. En peticiones HTMX
    responde con el encabezado HX-Redirect para que el navegador haga un
    cambio de página completo, en vez de inyectar el login en #page-content.
    """

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated:
            return view(request, *args, **kwargs)
        target = f"{reverse('login')}?next={quote(request.get_full_path(), safe='')}"
        if request.headers.get("HX-Request") == "true":
            return HttpResponse(status=204, headers={"HX-Redirect": target})
        return redirect(target)

    return wrapper

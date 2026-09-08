from functools import wraps

from django.shortcuts import redirect
from django.contrib.auth import logout


def marketing_specialist_required(view_func):

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):

        if not request.user.is_authenticated:
            return redirect("/login/")

        if not hasattr(request.user, "profile"):
            logout(request)
            return redirect("/login/")

        if request.user.profile.role != "MARKETING_SPECIALIST":
            return redirect("/admin/")

        return view_func(request, *args, **kwargs)

    return wrapper
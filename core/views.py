from django.shortcuts import redirect


def home(request):
    if request.user.is_authenticated:
        if request.user.is_superuser:
            return redirect("/admin/")

        if (
            hasattr(request.user, "profile")
            and request.user.profile.role == "MARKETING_SPECIALIST"
        ):
            return redirect("/dashboard/")

    return redirect("/login/")

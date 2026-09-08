from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect


def login_view(request):

    if request.user.is_authenticated:

        if request.user.is_superuser:
            return redirect("/admin/")

        if hasattr(request.user, "profile"):
            if request.user.profile.role == "MARKETING_SPECIALIST":
                return redirect("/dashboard/")

    if request.method == "POST":

        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user is not None:

            login(request, user)

            if user.is_superuser:
                return redirect("/admin/")

            if hasattr(user, "profile"):

                if user.profile.role == "MARKETING_SPECIALIST":
                    return redirect("/dashboard/")

            logout(request)

            return render(
                request,
                "accounts/login.html",
                {
                    "error": "You do not have permission to access the dashboard."
                }
            )

        return render(
            request,
            "accounts/login.html",
            {
                "error": "Invalid username or password."
            }
        )

    return render(
        request,
        "accounts/login.html"
    )


def logout_view(request):

    logout(request)

    return redirect("/login/")
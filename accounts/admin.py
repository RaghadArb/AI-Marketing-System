from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin

from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "role",
    )

    list_filter = (
        "role",
    )


class UserProfileInline(admin.StackedInline):

    model = UserProfile
    extra = 0
    max_num = 1


class CustomUserAdmin(UserAdmin):

    inlines = [
        UserProfileInline,
    ]


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
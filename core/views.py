from django.shortcuts import render, redirect
from django.conf import settings
from django.utils import translation


def set_language(request, lang_code):
    # Only allow languages defined in your settings.LANGUAGES
    if any(lang_code == l[0] for l in settings.LANGUAGES):
        translation.activate(lang_code)
        next_url = request.META.get('HTTP_REFERER', '/')
        response = redirect(next_url)
        # Remember the language in a cookie
        response.set_cookie(settings.LANGUAGE_COOKIE_NAME, lang_code)
        return response
    return redirect('home')
"""
The built web app, served by the API, so one address holds the pages,
the API and the sign-in callback.
"""

from starlette.routing import Match, Mount
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from app.core.config import settings

WEB_APP_NAME = "web"


class WebAppMount(Mount):
    """
    Everything outside the API is the web app. A path under the API's
    prefix never reaches it, so to a script a wrong address stays a 404
    and a wrong method a 405, with or without a built web app.
    """

    def matches(self, scope: Scope) -> tuple[Match, Scope]:
        """
        Claim a request unless it is for the API.

        :param scope: The request.
        :type scope: Scope
        :return: Whether this route takes it, and what it adds to it.
        :rtype: tuple[Match, Scope]
        """
        if scope["path"].startswith(f"{settings.API_PREFIX}/"):
            return Match.NONE, {}
        return super().matches(scope)


def web_app_mount() -> WebAppMount:
    """
    The route serving the built files. A server without them (in
    development Vite serves the pages) answers 404 and still starts.

    :return: The route, to go after every other.
    :rtype: WebAppMount
    """
    files = StaticFiles(
        directory=settings.WEB_DIR,
        html=True,
        check_dir=False,
    )
    return WebAppMount("/", app=files, name=WEB_APP_NAME)

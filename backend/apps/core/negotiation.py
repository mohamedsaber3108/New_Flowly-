from rest_framework.negotiation import DefaultContentNegotiation


class IgnoreClientContentNegotiation(DefaultContentNegotiation):
    """Always use the view's first renderer. Used by endpoints that browsers open
    directly (emailed links, OAuth redirects) and answer with a redirect or JSON."""

    def select_renderer(self, request, renderers, format_suffix=None):
        return renderers[0], renderers[0].media_type

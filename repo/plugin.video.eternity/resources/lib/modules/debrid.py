# -*- coding: utf-8 -*-

"""
Debrid Services Integration for Eternity
Supports Real-Debrid, Premiumize, AllDebrid and other Universal resolvers
"""

try:
    import resolveurl
except:
    try:
        import urlresolver as resolveurl
    except:
        resolveurl = None

debrid_resolvers = []

# Initialize debrid resolvers if resolveurl/urlresolver is available
if resolveurl:
    try:
        debrid_resolvers = [
            resolver() for resolver in resolveurl.relevant_resolvers(order_matters=True)
            if hasattr(resolver, 'isUniversal') and resolver.isUniversal()
        ]
    except:
        debrid_resolvers = []


def status():
    """
    Check if any debrid service is available and configured

    Returns:
        bool: True if at least one debrid resolver is available, False otherwise
    """
    return debrid_resolvers != []


def resolver(url, debrid):
    """
    Resolve a URL using a specific debrid service

    Args:
        url (str): The URL to resolve
        debrid (str): Name of the debrid service to use (e.g., 'Real-Debrid')

    Returns:
        str: Direct stream URL from debrid service, or None if failed
    """
    try:
        debrid_resolver = [resolver for resolver in debrid_resolvers if resolver.name == debrid][0]
        debrid_resolver.login()
        _host, _media_id = debrid_resolver.get_host_and_id(url)
        stream_url = debrid_resolver.get_media_url(_host, _media_id)
        return stream_url
    except:
        return None

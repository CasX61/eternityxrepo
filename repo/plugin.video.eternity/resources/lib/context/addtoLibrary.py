# -*- coding: utf-8 -*-
"""
    Eternity Add-on - Library Context Menu
"""

import sys
import xbmc
from urllib.parse import parse_qsl, quote_plus

if __name__ == '__main__':
    item = sys.listitem
    path = item.getPath()
    plugin = 'plugin://plugin.video.eternity/'
    args = path.split(plugin, 1)

    # DEBUG
    xbmc.log('[Eternity Library Context] Full path: %s' % path, xbmc.LOGINFO)

    if len(args) < 2:
        xbmc.log('[Eternity] Invalid path for library context menu', xbmc.LOGERROR)
        sys.exit()

    params = dict(parse_qsl(args[1].replace('?', '')))

    # DEBUG
    xbmc.log('[Eternity Library Context] Parsed params: %s' % str(params), xbmc.LOGINFO)

    # Eternity uses 'sysmeta' JSON parameter for metadata
    sysmeta = params.get('sysmeta', '')
    if sysmeta:
        import json
        try:
            meta = json.loads(sysmeta)
            xbmc.log('[Eternity Library Context] Parsed sysmeta: %s' % str(meta), xbmc.LOGINFO)

            # Extract from sysmeta
            title = meta.get('title', meta.get('originaltitle', ''))
            year = str(meta.get('year', ''))
            imdb = meta.get('imdb_id', meta.get('imdbnumber', ''))
            tmdb = str(meta.get('tmdb_id', meta.get('tmdb', '')))
            tvdb = str(meta.get('tvdb_id', meta.get('tvdb', '')))
            mediatype = meta.get('mediatype', '')
            tvshowtitle = meta.get('tvshowtitle', title if mediatype == 'tvshow' else '')
            season = str(meta.get('season', ''))
            episode = str(meta.get('episode', ''))

            # If no TMDB ID but we have IMDb ID, fetch TMDB ID from API
            if not tmdb and imdb:
                xbmc.log('[Eternity Library Context] No TMDB ID, fetching via IMDb: %s' % imdb, xbmc.LOGINFO)
                try:
                    import requests
                    from resources.lib import control
                    api_key = control.getSetting('api.tmdb')
                    url = 'https://api.themoviedb.org/3/find/%s?api_key=%s&external_source=imdb_id' % (imdb, api_key)
                    response = requests.get(url, timeout=5)
                    data = response.json()

                    # Check if it's a movie or TV show
                    if data.get('movie_results'):
                        tmdb = str(data['movie_results'][0]['id'])
                        xbmc.log('[Eternity Library Context] Found TMDB ID (movie): %s' % tmdb, xbmc.LOGINFO)
                    elif data.get('tv_results'):
                        tmdb = str(data['tv_results'][0]['id'])
                        tvdb = str(data['tv_results'][0].get('id', ''))  # TV show might have tvdb
                        xbmc.log('[Eternity Library Context] Found TMDB ID (tv): %s' % tmdb, xbmc.LOGINFO)
                except:
                    import traceback
                    xbmc.log('[Eternity Library Context] Failed to fetch TMDB ID: %s' % traceback.format_exc(), xbmc.LOGERROR)

        except:
            import traceback
            xbmc.log('[Eternity Library Context] Failed to parse sysmeta: %s' % traceback.format_exc(), xbmc.LOGERROR)
            # Fallback: try to get from params directly
            imdb = params.get('imdb', '')
            tmdb = params.get('tmdb', '')
            tvdb = params.get('tvdb', '')
            season = params.get('season', '')
            episode = params.get('episode', '')
            tvshowtitle = params.get('tvshowtitle', '')
            title = params.get('title', '')
            year = params.get('year', '')
    else:
        # No sysmeta - use params directly (fallback)
        imdb = params.get('imdb', '')
        tmdb = params.get('tmdb', '')
        tvdb = params.get('tvdb', '')
        season = params.get('season', '')
        episode = params.get('episode', '')
        tvshowtitle = params.get('tvshowtitle', '')
        title = params.get('title', '')
        year = params.get('year', '')

    sysname = item.getLabel()

    # DEBUG
    xbmc.log('[Eternity Library Context] Extracted: title=%s, year=%s, imdb=%s, tmdb=%s, name=%s' % (title, year, imdb, tmdb, sysname), xbmc.LOGINFO)

    if tvshowtitle:
        systvshowtitle = quote_plus(tvshowtitle)
    else:
        systvshowtitle = ''

    if title:
        systitle = quote_plus(title)
    else:
        systitle = ''

    # Determine if it's a movie or TV show
    # Check if tvshowtitle variable has value (not params dict!)
    action = 'tvshows' if tvshowtitle else 'movies'

    if action == 'tvshows':
        xbmc.executebuiltin('RunPlugin(%s?action=library_tvshowToLibrary&tvshowtitle=%s&year=%s&imdb=%s&tmdb=%s&tvdb=%s)' % (plugin, systvshowtitle, year, imdb, tmdb, tvdb))
    elif action == 'movies':
        xbmc.executebuiltin('RunPlugin(%s?action=library_movieToLibrary&name=%s&title=%s&year=%s&imdb=%s&tmdb=%s)' % (plugin, sysname, systitle, year, imdb, tmdb))

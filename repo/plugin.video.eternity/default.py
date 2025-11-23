
# 2023-05-10
# edit 2025-06-12

import sys, json
from resources.lib import control

# DNS Bypass via cRequestHandler (bypass_dns=True)
# Nur für blockierte Seiten wie Filmpalast aktiviert
# Setting: bypassDNSlock

params = dict(control.parse_qsl(control.urlsplit(sys.argv[2]).query))

action = params.get('action')
name = params.get('name')
table = params.get('table')
title = params.get('title')
source = params.get('source')

# ------ navigator --------------
if action == None or action == 'root':
    from resources.lib.indexers import navigator
    navigator.navigator().root()

elif action == 'pluginInfo':
    from resources.lib import supportinfo
    supportinfo.pluginInfo()

elif action == 'movieNavigator':
    from resources.lib.indexers import navigator
    navigator.navigator().movies()

elif action == 'tvNavigator':
    from resources.lib.indexers import navigator
    navigator.navigator().tvshows()

elif action == 'myMoviesNavigator':
    from resources.lib.indexers import navigator
    navigator.navigator().myMovies()

elif action == 'myTVNavigator':
    from resources.lib.indexers import navigator
    navigator.navigator().myTV()

elif action == 'myListsNavigator':
    from resources.lib.indexers import navigator
    navigator.navigator().myLists()

elif action == 'traktUserlist':
    from resources.lib.indexers import navigator
    list_id = params.get('list_id')
    navigator.navigator().traktUserlist(list_id)

elif action == 'toolNavigator':
    from resources.lib.indexers import navigator
    navigator.navigator().tools()

elif action == 'downloadNavigator':
    from resources.lib.indexers import navigator
    navigator.navigator().downloads()

elif action == 'searchNavigator':
    from resources.lib.indexers import navigator
    navigator.navigator().search()

# -------------------------------------------
elif action == 'download':
    image = params.get('image')
    from resources.lib import downloader
    from resources.lib import sources
    try: downloader.download(name, image, sources.sources().sourcesResolve(json.loads(source)[0], True))
    except: pass

elif action == 'play_Item':
    # Library Integration - Play from .strm file
    import json
    if not control.visible(): control.busy()
    try:
        sysmeta = {}
        for key, value in params.items():
            if key == 'action': continue
            elif key == 'year' or key == 'season' or key == 'episode': value = int(value)
            if value == 0: continue
            sysmeta.update({key : value})
        # Determine mediatype
        if params.get('season') and int(params.get('season', 0)) > 0:
            mediatype = 'tvshow'
        else:
            mediatype = 'movie'
        sysmeta.update({'mediatype': mediatype})
        sysmeta.update({'select': control.getSetting('hosts.mode')})
        sysmeta = json.dumps(sysmeta)
        params.update({'sysmeta': sysmeta})
        from resources.lib import sources
        sources.sources().play(params)
    except:
        import traceback
        xbmc.log('[Eternity Library] Play failed: %s' % traceback.format_exc(), xbmc.LOGERROR)

elif action == 'playExtern':
    import json
    if not control.visible(): control.busy()
    try:
        sysmeta = {}
        for key, value in params.items():
            if key == 'action': continue
            elif key == 'year' or key == 'season' or key == 'episode': value = int(value)
            if value == 0: continue
            sysmeta.update({key : value})
        if int(params.get('season')) == 0:
            mediatype = 'movie'
        else:
            mediatype = 'tvshow'
        sysmeta.update({'mediatype': mediatype})
        # if control.getSetting('hosts.mode') == '2':
        #     sysmeta.update({'select': '2'})
        # else:
        #     sysmeta.update({'select': '1'})
        sysmeta.update({'select': control.getSetting('hosts.mode')})
        sysmeta = json.dumps(sysmeta)
        params.update({'sysmeta': sysmeta})
        from resources.lib import sources
        sources.sources().play(params)
    except:
        pass

elif action == 'playURL':
    try:
        import resolveurl
        import xbmcgui, xbmc
        #url = 'https://streamvid.net/embed-uhgo683xes41'
        #url = 'https://moflix-stream.click/v/gcd0aueegeia'
        url = xbmcgui.Dialog().input("URL Input")
        hmf = resolveurl.HostedMediaFile(url=url, include_disabled=True, include_universal=False)
        try:
            if hmf.valid_url(): url = hmf.resolve()
        except:
            pass
        item = xbmcgui.ListItem('URL-direkt')
        kodiver = int(xbmc.getInfoLabel("System.BuildVersion").split(".")[0])
        if ".m3u8" in url or '.mpd' in url:
            item.setProperty("inputstream", "inputstream.adaptive")
            if '.mpd' in url:
                if kodiver < 21: item.setProperty('inputstream.adaptive.manifest_type', 'mpd')
                item.setMimeType('application/dash+xml')
            else:
                if kodiver < 21: item.setProperty('inputstream.adaptive.manifest_type', 'hls')
                item.setMimeType("application/vnd.apple.mpegurl")
            item.setContentLookup(False)
            if '|' in url:
                stream_url, strhdr = url.split('|')
                item.setProperty('inputstream.adaptive.stream_headers', strhdr)
                if kodiver > 19: item.setProperty('inputstream.adaptive.manifest_headers', strhdr)
                # item.setPath(stream_url)
                url = stream_url
        item.setPath(url)
        xbmc.Player().play(url, item)
    except:
        #print('Kein Video Link gefunden')
        control.infoDialog("Keinen Video Link gefunden", sound=True, icon='WARNING', time=1000)

elif action == 'UpdatePlayCount':
    from resources.lib import playcountDB
    playcountDB.UpdatePlaycount(params)
    control.execute('Container.Refresh')

# listings -------------------------------
elif action == 'listings':
    from resources.lib.indexers import listings
    listings.listings().get(params)

elif action == 'movieYears':
    from resources.lib.indexers import listings
    listings.listings().movieYears()

elif action == 'movieGenres':
    from resources.lib.indexers import listings
    listings.listings().movieGenres()

elif action == 'tvGenres':
    from resources.lib.indexers import listings
    listings.listings().tvGenres()

# search ----------------------
elif action == 'searchNew':
    from resources.lib import searchDB
    searchDB.search_new(table)

elif action == 'searchClear':
    from resources.lib import searchDB
    searchDB.remove_all_query(table)
    # if len(searchDB.getSearchTerms()) == 0:
    #     control.execute('Action(ParentDir)')

elif action == 'searchDelTerm':
    from resources.lib import searchDB
    searchDB.remove_query(name, table)
    # if len(searchDB.getSearchTerms()) == 0:
    #     control.execute('Action(ParentDir)')

# person ----------------------
elif action == 'person':
    from resources.lib.indexers import person
    person.person().get(params)

elif action == 'personSearch':
    from resources.lib.indexers import person
    person.person().search()

elif action == 'personCreditsMenu':
    from resources.lib.indexers import person
    person.person().creditsMenu(params)

elif action == 'personCredits':
    from resources.lib.indexers import person
    person.person().getCredits(params)

elif action == 'playfromPerson':
    if not control.visible(): control.busy()
    sysmeta = json.loads(params['sysmeta'])
    if sysmeta['mediatype'] == 'movie':
        from resources.lib.indexers import movies
        sysmeta = movies.movies().super_meta('', id=sysmeta['tmdb_id'])
        sysmeta = json.dumps(sysmeta)
    else:
        from resources.lib.indexers import tvshows
        sysmeta = tvshows.tvshows().super_meta('', id=sysmeta['tmdb_id'])
        sysmeta = control.quote_plus(json.dumps(sysmeta))

    params.update({'sysmeta': sysmeta})
    from resources.lib import sources
    sources.sources().play(params)

# movies ----------------------
elif action == 'movies':
    from resources.lib.indexers import movies
    movies.movies().get(params)

elif action == 'moviesSearch':
    from resources.lib.indexers import movies
    movies.movies().search()

elif action == 'movieUserlists':
    from resources.lib.indexers import movies
    movies.movies().userlists()

# tvshows ---------------------------------
elif action == 'tvshows': # 'tvshowPage'
    from resources.lib.indexers import tvshows
    tvshows.tvshows().get(params)

elif action == 'tvshowsSearch':
    from resources.lib.indexers import tvshows
    tvshows.tvshows().search()

elif action == 'tvUserlists':
    from resources.lib.indexers import tvshows
    tvshows.tvshows().userlists()

# seasons ---------------------------------
elif action == 'seasons':
    from resources.lib.indexers import seasons
    seasons.seasons().get(params)  # params

# episodes ---------------------------------
elif action == 'episodes':
    from resources.lib.indexers import episodes
    # Check if this is a Trakt URL
    url = params.get('url')
    if url == 'trakt_unfinished':
        # Phase 1.6: Unfinished Episodes
        episodes.episodes().getTraktUnfinished()
    elif url == 'trakt_progress':
        # Phase 1.7: Next Episodes to Watch (Progress)
        episodes.episodes().getTraktProgress()
    else:
        episodes.episodes().get(params)

# sources ---------------------------------
elif action == 'play':
    if not control.visible(): control.busy()
    from resources.lib import sources
    sources.sources().play(params)

elif action == 'addItem':
    from resources.lib import sources
    sources.sources().addItem(title)

elif action == 'playItem':
    if not control.visible(): control.busy()
    from resources.lib import sources
    sources.sources().playItem(title, source)

# Trakt ------------------------------
elif action == 'authTrakt':
    from resources.lib.modules import trakt
    trakt.traktAuth(fromSettings=1)

elif action == 'revokeTrakt':
    from resources.lib.modules import trakt
    trakt.traktRevoke(fromSettings=1)

elif action == 'tools_traktManager' or action == 'traktManager':
    from resources.lib.modules import trakt
    name = params.get('name')
    imdb = params.get('imdb')
    tvdb = params.get('tvdb')
    season = params.get('season')
    episode = params.get('episode')
    watched = params.get('watched')
    unfinished = params.get('unfinished', 'false') == 'true'

    # Convert watched string to bool
    if watched == 'True' or watched == 'true':
        watched = True
    elif watched == 'False' or watched == 'false':
        watched = False
    else:
        watched = None

    trakt.manager(name=name, imdb=imdb, tvdb=tvdb, season=season, episode=episode, watched=watched, unfinished=unfinished)

# Library ------------------------------
elif action == 'library_movieToLibrary':
    from resources.lib.modules import library
    name = params.get('name')
    title = params.get('title')
    year = params.get('year')
    imdb = params.get('imdb')
    tmdb = params.get('tmdb')
    library.libmovies().add(name, title, year, imdb, tmdb)

elif action == 'library_tvshowToLibrary':
    from resources.lib.modules import library
    tvshowtitle = params.get('tvshowtitle')
    year = params.get('year')
    imdb = params.get('imdb')
    tmdb = params.get('tmdb')
    tvdb = params.get('tvdb')
    library.libtvshows().add(tvshowtitle, year, imdb, tmdb, tvdb)

elif action == 'library_moviesToLibrary':
    from resources.lib.modules import library
    url = params.get('url')
    list_name = params.get('list_name', 'Trakt List')
    library.libmovies().range(url, list_name)

elif action == 'library_tvshowsToLibrary':
    from resources.lib.modules import library
    url = params.get('url')
    list_name = params.get('list_name', 'Trakt List')
    library.libtvshows().range(url, list_name)

elif action == 'library_update':
    from resources.lib.modules import library
    control.infoDialog('Updating library...', heading='Library')
    library.lib_tools.update()
    control.infoDialog('Library updated', heading='Library')

elif action == 'library_clean':
    from resources.lib.modules import library
    if control.yesnoDialog('Clean library? This will remove invalid entries.', '', ''):
        control.infoDialog('Cleaning library...', heading='Library')
        library.lib_tools.clean()
        control.infoDialog('Library cleaned', heading='Library')

# ResolveURL Settings ------------------------------
elif action == 'openResolveURLSettings':
    try:
        import resolveurl
        resolveurl.display_settings()
    except:
        try:
            import urlresolver
            urlresolver.display_settings()
        except:
            control.infoDialog('ResolveURL/URLResolver nicht verfügbar', sound=True, icon='ERROR')

# Settings ------------------------------
elif action == "settings":  # alle Quellen aktivieren / deaktivieren
    from resources import settings
    settings.run(params)

elif action == 'addonSettings':
    # query = None
    query = params.get('query')
    control.openSettings(query)

elif action == 'resetSettings':
    status = control.resetSettings()
    if status:
        control.reload_profile()
        control.sleep(500)
        control.execute('RunAddon("%s")' % control.addonId)
        
elif action == 'resolverSettings':
    import resolveurl as resolver
    resolver.display_settings()

# try:
#     import pydevd
#     if pydevd.connected: pydevd.kill_all_pydev_threads()
# except:
#     pass
# finally:
#     exit()

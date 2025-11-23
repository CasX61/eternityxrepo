# -*- coding: utf-8 -*-

"""
Eternity Trakt Integration
Migrated from Infinity (Python 2 -> Python 3)
Device OAuth Flow for TV/Kodi Apps
"""

import json
import time
from urllib.parse import urljoin
import requests
import xbmc

from resources.lib import control

# Trakt API Configuration
BASE_URL = 'https://api.trakt.tv'
CLIENT_ID = '239a31316d98d8a9b6590a9a8204de30a5056fbeaa5a630b3c5539c06cd37179'
CLIENT_SECRET = '4e552b8c913ae5f739b2a49522db6d10243d4e1b0a2bbea896d7efa7a0d58ae0'
REDIRECT_URI = 'urn:ietf:wg:oauth:2.0:oob'


def _getTrakt(url, post=None):
    """
    Internal function to make Trakt API requests
    Handles authentication, token refresh, and error codes
    """
    try:
        url = urljoin(BASE_URL, url)
        headers = {
            'Content-Type': 'application/json',
            'trakt-api-key': CLIENT_ID,
            'trakt-api-version': '2'
        }

        # Add authorization if user is logged in
        if getTraktCredentialsInfo():
            headers['Authorization'] = 'Bearer %s' % control.getSetting('trakt.token')

        # Make request
        if post:
            response = requests.post(url, json=post, headers=headers, timeout=30)
        else:
            response = requests.get(url, headers=headers, timeout=30)

        # Handle error codes
        if response.status_code in [500, 502, 503, 504, 520, 521, 522, 524]:
            xbmc.log('[Eternity-Trakt] Temporary Error: %s' % response.status_code, xbmc.LOGWARNING)
            return None
        elif response.status_code == 404:
            xbmc.log('[Eternity-Trakt] Object Not Found (404)', xbmc.LOGWARNING)
            return None
        elif response.status_code == 429:
            xbmc.log('[Eternity-Trakt] Rate Limit Reached (429)', xbmc.LOGWARNING)
            return None
        elif response.status_code in [401, 405]:
            # Token expired - try to refresh
            return _refreshToken(url, post)

        # Success
        return response.text, response.headers

    except Exception as e:
        xbmc.log('[Eternity-Trakt] Error: %s' % str(e), xbmc.LOGERROR)
        return None


def _refreshToken(url, post=None):
    """
    Refresh expired OAuth token
    """
    try:
        oauth_url = urljoin(BASE_URL, '/oauth/token')
        oauth_post = {
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'redirect_uri': REDIRECT_URI,
            'grant_type': 'refresh_token',
            'refresh_token': control.getSetting('trakt.refresh')
        }

        headers = {
            'Content-Type': 'application/json',
            'trakt-api-key': CLIENT_ID,
            'trakt-api-version': '2'
        }

        response = requests.post(oauth_url, json=oauth_post, headers=headers, timeout=30)
        result = response.json()

        # Save new tokens
        token = result['access_token']
        refresh = result['refresh_token']

        control.setSetting(id='trakt.token', value=token)
        control.setSetting(id='trakt.refresh', value=refresh)

        # Retry original request with new token
        headers['Authorization'] = 'Bearer %s' % token
        if post:
            response = requests.post(url, json=post, headers=headers, timeout=30)
        else:
            response = requests.get(url, headers=headers, timeout=30)

        return response.text, response.headers

    except Exception as e:
        xbmc.log('[Eternity-Trakt] Token Refresh Error: %s' % str(e), xbmc.LOGERROR)
        return None


def getTraktAsJson(url, post=None):
    """
    Get Trakt API response as JSON
    """
    try:
        result = _getTrakt(url, post)
        if not result:
            return None

        response_text, response_headers = result
        data = json.loads(response_text)

        # Handle sorting headers
        if 'X-Sort-By' in response_headers and 'X-Sort-How' in response_headers:
            data = _sortList(response_headers['X-Sort-By'], response_headers['X-Sort-How'], data)

        return data
    except:
        return None


def _sortList(sort_key, sort_direction, list_data):
    """
    Sort list based on Trakt headers
    """
    try:
        reverse = False if sort_direction == 'asc' else True

        if sort_key == 'rank':
            return sorted(list_data, key=lambda x: x.get('rank', 0), reverse=reverse)
        elif sort_key == 'added':
            return sorted(list_data, key=lambda x: x.get('listed_at', ''), reverse=reverse)
        elif sort_key == 'title':
            return sorted(list_data, key=lambda x: x.get('title', ''), reverse=reverse)
        else:
            return list_data
    except:
        return list_data


def authTrakt():
    """
    Authenticate with Trakt using Device OAuth Flow
    Shows code to user, polls for authorization
    """
    try:
        # Check if already authenticated
        if getTraktCredentialsInfo():
            if control.yesnoDialog("Trakt Konto bereits vorhanden", "Möchten Sie das Konto zurücksetzen?", '', 'Trakt'):
                control.setSetting(id='trakt.user', value='')
                control.setSetting(id='trakt.token', value='')
                control.setSetting(id='trakt.refresh', value='')
            else:
                return

        # Step 1: Get device code
        result = getTraktAsJson('/oauth/device/code', {'client_id': CLIENT_ID})
        if not result:
            control.infoDialog('Trakt Fehler: Keine Verbindung', sound=True, icon='ERROR')
            return

        verification_url = result['verification_url']
        user_code = result['user_code']
        device_code = result['device_code']
        expires_in = int(result['expires_in'])
        interval = int(result['interval'])

        # Step 2: Show code to user
        # Format message for Kodi 20+ (single message parameter)
        message = 'Besuche: [COLOR skyblue]%s[/COLOR]\n\nCode eingeben: [COLOR skyblue]%s[/COLOR]' % (verification_url, user_code)

        progressDialog = control.progressDialog
        progressDialog.create('Trakt Autorisierung', message)

        # Step 3: Poll for authorization
        for i in range(0, expires_in):
            try:
                if progressDialog.iscanceled():
                    break

                time.sleep(1)

                # Only check every interval seconds
                if not float(i) % interval == 0:
                    continue

                # Try to get token
                token_result = getTraktAsJson('/oauth/device/token', {
                    'client_id': CLIENT_ID,
                    'client_secret': CLIENT_SECRET,
                    'code': device_code
                })

                if token_result and 'access_token' in token_result:
                    # Success!
                    token = token_result['access_token']
                    refresh = token_result['refresh_token']

                    # Get username
                    headers = {
                        'Content-Type': 'application/json',
                        'trakt-api-key': CLIENT_ID,
                        'trakt-api-version': '2',
                        'Authorization': 'Bearer %s' % token
                    }

                    user_response = requests.get(urljoin(BASE_URL, '/users/me'), headers=headers, timeout=30)
                    user_data = user_response.json()
                    username = user_data['username']

                    # Save credentials
                    control.setSetting(id='trakt.user', value=username)
                    control.setSetting(id='trakt.token', value=token)
                    control.setSetting(id='trakt.refresh', value=refresh)

                    progressDialog.close()
                    control.infoDialog('Trakt Autorisierung erfolgreich!', sound=False, icon='INFO')
                    return

            except:
                pass

        # Timeout or canceled
        try:
            progressDialog.close()
        except:
            pass

        control.infoDialog('Trakt Autorisierung abgebrochen', sound=True, icon='WARNING')

    except Exception as e:
        xbmc.log('[Eternity-Trakt] Auth Error: %s' % str(e), xbmc.LOGERROR)
        control.infoDialog('Trakt Fehler beim Autorisieren', sound=True, icon='ERROR')


def getTraktCredentialsInfo():
    """
    Check if user is authenticated with Trakt
    Returns True if all credentials are present
    """
    user = control.getSetting('trakt.user').strip()
    token = control.getSetting('trakt.token')
    refresh = control.getSetting('trakt.refresh')

    if user == '' or token == '' or refresh == '':
        return False
    return True


# ====================
# Trakt API Functions
# ====================

def getMovieCollection():
    """Get user's movie collection"""
    return getTraktAsJson('/users/me/collection/movies?extended=full')


def getTVCollection():
    """Get user's TV show collection"""
    return getTraktAsJson('/users/me/collection/shows?extended=full')


def getMovieWatchlist():
    """Get user's movie watchlist"""
    return getTraktAsJson('/users/me/watchlist/movies?extended=full')


def getTVWatchlist():
    """Get user's TV show watchlist"""
    return getTraktAsJson('/users/me/watchlist/shows?extended=full')


def getMovieHistory():
    """Get user's movie watch history (last 20)"""
    return getTraktAsJson('/users/me/history/movies?extended=full&limit=20&page=1')


def getTVHistory():
    """Get user's TV show watch history (last 20 episodes)"""
    return getTraktAsJson('/users/me/history/episodes?extended=full&limit=20&page=1')


def getRecommendedMovies():
    """Get recommended movies for user"""
    return getTraktAsJson('/recommendations/movies?limit=40')


def getRecommendedShows():
    """Get recommended TV shows for user"""
    return getTraktAsJson('/recommendations/shows?limit=40')


def getContinueWatching():
    """
    Get shows user is currently watching (Continue Watching / Up Next)
    Returns shows with next episode to watch
    """
    try:
        # Get all watched shows with full info
        items = getTraktAsJson('/users/me/watched/shows?extended=full')
        if not items:
            return None

        continue_watching = []

        for item in items:
            show_data = item.get('show', {})
            aired = show_data.get('aired_episodes', 0)

            # Count watched episodes from seasons
            watched = 0
            for season in item.get('seasons', []):
                watched += len(season.get('episodes', []))

            # Only include if not finished and has aired episodes
            if aired > watched and aired > 0 and watched > 0:
                # User started watching and hasn't finished
                continue_watching.append(item)

        # Limit to 40 most recent
        continue_watching = continue_watching[:40]

        return continue_watching if continue_watching else None
    except:
        return None


def getOnDeck():
    """Get next episodes to watch (on deck)"""
    # This requires custom logic - get shows in progress
    progress = getTraktAsJson('/sync/playback/episodes?limit=50')
    return progress


def getUserLists():
    """Get user's custom lists"""
    return getTraktAsJson('/users/me/lists')


def getListItems(username, list_id, list_type=None):
    """
    Get items from a specific list
    list_type: 'movies', 'shows', or None for all items (mixed)
    """
    if list_type:
        url = '/users/%s/lists/%s/items/%s' % (username, list_id, list_type)
    else:
        # Get all items (movies + shows)
        url = '/users/%s/lists/%s/items' % (username, list_id)
    return getTraktAsJson(url)


def addToCollection(imdb_id, content_type='movie'):
    """
    Add item to collection
    content_type: 'movie' or 'show'
    """
    if content_type == 'movie':
        post = {"movies": [{"ids": {"imdb": imdb_id}}]}
    else:
        post = {"shows": [{"ids": {"imdb": imdb_id}}]}

    return getTraktAsJson('/sync/collection', post)


def removeFromCollection(imdb_id, content_type='movie'):
    """Remove item from collection"""
    if content_type == 'movie':
        post = {"movies": [{"ids": {"imdb": imdb_id}}]}
    else:
        post = {"shows": [{"ids": {"imdb": imdb_id}}]}

    return getTraktAsJson('/sync/collection/remove', post)


def addToWatchlist(imdb_id, content_type='movie'):
    """Add item to watchlist"""
    if content_type == 'movie':
        post = {"movies": [{"ids": {"imdb": imdb_id}}]}
    else:
        post = {"shows": [{"ids": {"imdb": imdb_id}}]}

    return getTraktAsJson('/sync/watchlist', post)


def removeFromWatchlist(imdb_id, content_type='movie'):
    """Remove item from watchlist"""
    if content_type == 'movie':
        post = {"movies": [{"ids": {"imdb": imdb_id}}]}
    else:
        post = {"shows": [{"ids": {"imdb": imdb_id}}]}

    return getTraktAsJson('/sync/watchlist/remove', post)


def manager(name, imdb, tvdb, content):
    """
    Trakt Manager - Context Menu for Add/Remove items
    Ported from Infinity
    """
    try:
        # Build POST data
        if content == 'movie':
            post = {"movies": [{"ids": {"imdb": imdb}}]}
        else:
            post = {"shows": [{"ids": {"tvdb": tvdb}}]}

        # Build menu items
        items = []
        items.append(("Zur [B]Sammlung[/B] hinzufügen", '/sync/collection'))
        items.append(("Aus [B]Sammlung[/B] entfernen", '/sync/collection/remove'))
        items.append(("Zur [B]Merkliste[/B] hinzufügen", '/sync/watchlist'))
        items.append(("Aus [B]Merkliste[/B] entfernen", '/sync/watchlist/remove'))
        items.append(("Zu [B]neuer Liste[/B] hinzufügen", '/users/me/lists/%s/items'))

        # Get user's lists
        result = getUserLists()
        if result:
            lists = [(i['name'], i['ids']['slug']) for i in result]
            lists = [lists[i//2] for i in range(len(lists)*2)]
            for i in range(0, len(lists), 2):
                lists[i] = (("Zu [B]%s[/B] hinzufügen" % lists[i][0]), '/users/me/lists/%s/items' % lists[i][1])
            for i in range(1, len(lists), 2):
                lists[i] = (("Aus [B]%s[/B] entfernen" % lists[i][0]), '/users/me/lists/%s/items/remove' % lists[i][1])
            items += lists

        # Show selection dialog
        select = control.selectDialog([i[0] for i in items], "Trakt-Manager")

        if select == -1:
            return
        elif select == 4:
            # Create new list
            t = "Zu [B]neuer Liste[/B] hinzufügen"
            k = control.keyboard('', t)
            k.doModal()
            new = k.getText() if k.isConfirmed() else None
            if not new:
                return

            # Create the list
            result = _getTrakt('/users/me/lists', post={"name": new, "privacy": "private"})
            if not result:
                control.infoDialog("Trakt-Manager", heading=str(name), sound=True, icon='ERROR')
                return

            try:
                response_text, response_headers = result
                slug = json.loads(response_text)['ids']['slug']
            except:
                control.infoDialog("Trakt-Manager", heading=str(name), sound=True, icon='ERROR')
                return

            # Add to new list
            result = _getTrakt(items[select][1] % slug, post=post)
        else:
            # Execute selected action
            result = _getTrakt(items[select][1], post=post)

        # Show result
        icon = 'INFO' if result else 'ERROR'
        control.infoDialog("Trakt-Manager", heading=str(name), sound=True, icon=icon)

    except Exception as e:
        xbmc.log('[Eternity-Trakt] Manager Error: %s' % str(e), xbmc.LOGERROR)
        control.infoDialog("Trakt-Manager Fehler", sound=True, icon='ERROR')


# ====================
# History/Watched Sync
# ====================

def markMovieAsWatched(imdb):
    """
    Mark movie as watched in Trakt history
    Automatically adds to watch history
    """
    if not imdb.startswith('tt'):
        imdb = 'tt' + imdb
    post = {"movies": [{"ids": {"imdb": imdb}}]}
    return getTraktAsJson('/sync/history', post)


def markMovieAsNotWatched(imdb):
    """Remove movie from Trakt watch history"""
    if not imdb.startswith('tt'):
        imdb = 'tt' + imdb
    post = {"movies": [{"ids": {"imdb": imdb}}]}
    return getTraktAsJson('/sync/history/remove', post)


def markEpisodeAsWatched(tvdb, season, episode):
    """
    Mark episode as watched in Trakt history
    """
    season = int('%01d' % int(season))
    episode = int('%01d' % int(episode))
    post = {
        "shows": [{
            "ids": {"tvdb": tvdb},
            "seasons": [{
                "number": season,
                "episodes": [{"number": episode}]
            }]
        }]
    }
    return getTraktAsJson('/sync/history', post)


def markEpisodeAsNotWatched(tvdb, season, episode):
    """Remove episode from Trakt watch history"""
    season = int('%01d' % int(season))
    episode = int('%01d' % int(episode))
    post = {
        "shows": [{
            "ids": {"tvdb": tvdb},
            "seasons": [{
                "number": season,
                "episodes": [{"number": episode}]
            }]
        }]
    }
    return getTraktAsJson('/sync/history/remove', post)


# ====================
# Scrobble Functions
# ====================

def scrobbleStart(content_type, imdb=None, tvdb=None, season=None, episode=None, progress=0, duration=None):
    """
    Start scrobbling - notify Trakt playback has started
    progress: 0-100 percent
    duration: runtime in minutes
    """
    try:
        if content_type == 'movie':
            if not imdb.startswith('tt'):
                imdb = 'tt' + imdb
            post = {
                "movie": {"ids": {"imdb": imdb}},
                "progress": progress
            }
        else:  # episode
            season = int('%01d' % int(season))
            episode = int('%01d' % int(episode))
            post = {
                "show": {"ids": {"tvdb": tvdb}},
                "episode": {
                    "season": season,
                    "number": episode
                },
                "progress": progress
            }

        if duration:
            post["duration"] = duration

        return getTraktAsJson('/scrobble/start', post)
    except Exception as e:
        xbmc.log('[Eternity-Trakt] Scrobble Start Error: %s' % str(e), xbmc.LOGDEBUG)
        return None


def scrobblePause(content_type, imdb=None, tvdb=None, season=None, episode=None, progress=0, duration=None):
    """
    Pause scrobbling - notify Trakt playback was paused
    """
    try:
        if content_type == 'movie':
            if not imdb.startswith('tt'):
                imdb = 'tt' + imdb
            post = {
                "movie": {"ids": {"imdb": imdb}},
                "progress": progress
            }
        else:  # episode
            season = int('%01d' % int(season))
            episode = int('%01d' % int(episode))
            post = {
                "show": {"ids": {"tvdb": tvdb}},
                "episode": {
                    "season": season,
                    "number": episode
                },
                "progress": progress
            }

        if duration:
            post["duration"] = duration

        return getTraktAsJson('/scrobble/pause', post)
    except Exception as e:
        xbmc.log('[Eternity-Trakt] Scrobble Pause Error: %s' % str(e), xbmc.LOGDEBUG)
        return None


def scrobbleStop(content_type, imdb=None, tvdb=None, season=None, episode=None, progress=0, duration=None):
    """
    Stop scrobbling - notify Trakt playback has stopped
    If progress >= 80%, automatically marks as watched
    """
    try:
        if content_type == 'movie':
            if not imdb.startswith('tt'):
                imdb = 'tt' + imdb
            post = {
                "movie": {"ids": {"imdb": imdb}},
                "progress": progress
            }
        else:  # episode
            season = int('%01d' % int(season))
            episode = int('%01d' % int(episode))
            post = {
                "show": {"ids": {"tvdb": tvdb}},
                "episode": {
                    "season": season,
                    "number": episode
                },
                "progress": progress
            }

        if duration:
            post["duration"] = duration

        return getTraktAsJson('/scrobble/stop', post)
    except Exception as e:
        xbmc.log('[Eternity-Trakt] Scrobble Stop Error: %s' % str(e), xbmc.LOGDEBUG)
        return None

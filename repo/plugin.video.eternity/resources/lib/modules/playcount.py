# -*- coding: utf-8 -*-
"""
Eternity Playcount Module - Trakt Indicator Support
Based on Umbrella's playcount.py - Adapted for Eternity
"""

from resources.lib.modules import trakt
from resources.lib import playcountDB

# Check if Trakt is active as indicator source
traktIndicators = trakt.getTraktIndicatorsInfo()
traktCredentials = trakt.getTraktCredentialsInfo()


def getMovieIndicators(refresh=False):
	"""
	Get movie watched indicators from Trakt or local database
	Returns: List of IMDB IDs ['tt1234567', 'tt2345678', ...] OR playcountDB module
	"""
	try:
		if traktIndicators:
			# Fetch from Trakt with cache
			if not refresh:
				timeout = 720  # 12 hours cache
			else:
				timeout = 0  # Force refresh
			indicators = trakt.cachesyncMovies(timeout=timeout)
			return indicators
		else:
			# Fallback to local database
			return playcountDB
	except:
		import xbmc
		xbmc.log('[Eternity-Playcount] getMovieIndicators Error', xbmc.LOGERROR)
		return playcountDB


def getTVShowIndicators(refresh=False):
	"""
	Get TV show watched indicators from Trakt or local database
	Returns: List of tuples [(ids_dict, aired_episodes, watched_episodes), ...] OR playcountDB module
	Format: [({'imdb': 'tt123', 'tvdb': '456'}, 16, [(1,1), (1,2), ...]), ...]
	"""
	try:
		if traktIndicators:
			if not refresh:
				timeout = 720  # 12 hours cache
			else:
				timeout = 0  # Force refresh
			indicators = trakt.cachesyncTVShows(timeout=timeout)
			return indicators
		else:
			# Fallback to local database
			return playcountDB
	except:
		import xbmc
		xbmc.log('[Eternity-Playcount] getTVShowIndicators Error', xbmc.LOGERROR)
		return playcountDB


def getMovieOverlay(indicators, imdb):
	"""
	Check if movie is watched
	Returns: '7' (watched) or '6' (unwatched)
	"""
	if not indicators:
		return '6'
	try:
		if traktIndicators:
			# indicators is list of IMDB IDs from Trakt
			playcount = [i for i in indicators if i == imdb]
			return '7' if len(playcount) > 0 else '6'
		else:
			# Local database
			playcount = indicators.getPlaycount('movie', 'imdb_id', imdb)
			return '7' if playcount else '6'
	except:
		import xbmc
		xbmc.log('[Eternity-Playcount] getMovieOverlay Error for imdb=%s' % imdb, xbmc.LOGERROR)
		return '6'


def getTVShowOverlay(indicators, imdb, tvdb):
	"""
	Check if entire TV show is watched
	Returns: '7' (fully watched) or '6' (not fully watched)
	"""
	if not indicators:
		return '6'
	try:
		if traktIndicators:
			# indicators is list of (ids, aired, watched_episodes)
			# Find show by IMDB or TVDB
			show_data = [i for i in indicators if (i[0].get('imdb') == imdb or str(i[0].get('tvdb')) == str(tvdb))]
			if not show_data:
				return '6'

			# Check if all aired episodes are watched
			ids_dict, aired_episodes, watched_episodes = show_data[0]
			watched_count = len(watched_episodes)
			return '7' if watched_count >= aired_episodes else '6'
		else:
			# Local database
			playcount = indicators.getPlaycount('tvshow', 'imdb_id', imdb)
			return '7' if playcount else '6'
	except:
		import xbmc
		xbmc.log('[Eternity-Playcount] getTVShowOverlay Error for imdb=%s, tvdb=%s' % (imdb, tvdb), xbmc.LOGERROR)
		return '6'


def getEpisodeOverlay(indicators, imdb, tvdb, season, episode):
	"""
	Check if episode is watched
	Returns: '7' (watched) or '6' (unwatched)
	"""
	if not indicators:
		return '6'
	try:
		if traktIndicators:
			# indicators is list of (ids, aired, watched_episodes)
			# watched_episodes = [(season, episode), (season, episode), ...]
			playcount = [i[2] for i in indicators if (i[0].get('imdb') == imdb or str(i[0].get('tvdb')) == str(tvdb))]
			if len(playcount) == 0:
				return '6'

			playcount = playcount[0]  # Get watched episodes list
			# Check if (season, episode) in watched list
			is_watched = [i for i in playcount if int(season) == int(i[0]) and int(episode) == int(i[1])]
			return '7' if len(is_watched) > 0 else '6'
		else:
			# Local database - uses title instead of IDs
			# Note: This is a limitation - we need title for local DB
			# For now, return '6' (unwatched) if not Trakt
			# Real implementation would need to pass title
			return '6'
	except:
		import xbmc
		xbmc.log('[Eternity-Playcount] getEpisodeOverlay Error for imdb=%s, tvdb=%s, S%sE%s' % (imdb, tvdb, season, episode), xbmc.LOGERROR)
		return '6'


def movies(name, imdb, watched):
	"""
	Mark movie as watched/unwatched
	watched: 7 (watched) or 6 (unwatched)
	"""
	try:
		if traktCredentials:
			if int(watched) == 7:
				trakt.watch(content_type='movie', name=name, imdb=imdb, refresh=True)
			else:
				trakt.unwatch(content_type='movie', name=name, imdb=imdb, refresh=True)
		else:
			# Local database
			playcount = 1 if int(watched) == 7 else 0
			playcountDB.updatePlaycount('movie', name=name, id=imdb, playcount=playcount)
			from resources.lib import control
			control.refresh()
	except:
		import xbmc
		xbmc.log('[Eternity-Playcount] movies() Error', xbmc.LOGERROR)


def episodes(name, imdb, tvdb, season, episode, watched):
	"""
	Mark episode as watched/unwatched
	watched: 7 (watched) or 6 (unwatched)
	"""
	try:
		if traktCredentials:
			if int(watched) == 7:
				trakt.watch(content_type='episode', name=name, imdb=imdb, tvdb=tvdb, season=season, episode=episode, refresh=True)
			else:
				trakt.unwatch(content_type='episode', name=name, imdb=imdb, tvdb=tvdb, season=season, episode=episode, refresh=True)
		else:
			# Local database
			playcount = 1 if int(watched) == 7 else 0
			playcountDB.updatePlaycount('episode', title=name, season=season, episode=episode, playcount=playcount)
			from resources.lib import control
			control.refresh()
	except:
		import xbmc
		xbmc.log('[Eternity-Playcount] episodes() Error', xbmc.LOGERROR)

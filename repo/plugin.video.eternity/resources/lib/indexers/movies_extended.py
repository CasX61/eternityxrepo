# -*- coding: utf-8 -*-
"""
Eternity Movies Extended - Umbrella Trakt Methods
COMPLETE PORT - Proper trakt_list() implementation with ALL fields
"""

import sys
import xbmc
import json
from urllib.parse import parse_qsl, urlsplit, urlparse, urlencode, quote_plus
from resources.lib import control
from resources.lib.modules import trakt, cache
from datetime import datetime, timedelta


class MoviesExtended:
	"""Extended Movies class with Umbrella's Trakt methods"""

	def __init__(self, movies_instance):
		"""
		Initialize with reference to main Movies instance
		:param movies_instance: Instance of Movies class
		"""
		self.movies = movies_instance
		self.list = []
		self.trakt_user = control.getSetting('trakt.user.name')
		self.lang = 'de'
		self.today_date = datetime.today().strftime('%Y-%m-%d')
		self.date_time = datetime.today()

		# Trakt API links
		self.trakt_link = 'https://api.trakt.tv'
		self.traktunfinished_link = '/sync/playback/movies?limit=40'
		self.trakthistory_link = '/users/me/history/movies?page=1&limit=40'

	# =========================================
	# UMBRELLA trakt_list() - COMPLETE PORT
	# =========================================

	def trakt_list(self, url, user, folderName=''):
		"""
		Umbrella trakt_list() for MOVIES - Lines 1315-1351
		COMPLETE 1:1 PORT - Proper Trakt API response extraction
		Returns: List of movie dicts with ALL metadata including:
		  - paused_at (for unfinished)
		  - progress (for resume point)
		  - lastplayed/watched_at (for history)
		  - added/listed_at (when added to list)
		"""
		self.list = []
		try:
			# Remove ',return' suffix (Umbrella Line 1317)
			if ',return' in url:
				url = url.split(',return')[0]

			# Fetch from Trakt API
			items = trakt.getTraktAsJson(url)
			if not items:
				xbmc.log('[Eternity-MoviesExt] trakt_list: No items from Trakt', xbmc.LOGDEBUG)
				return []

			xbmc.log('[Eternity-MoviesExt] trakt_list fetched %d items from %s' % (len(items), url), xbmc.LOGDEBUG)

			# Calculate next page URL (Umbrella Lines 1320-1327)
			try:
				q = dict(parse_qsl(urlsplit(url).query))
				if int(q['limit']) != len(items):
					raise Exception()
				q.update({'page': str(int(q['page']) + 1)})
				q = (urlencode(q)).replace('%2C', ',')
				next = url.replace('?' + urlparse(url).query, '') + '?' + q
				next = next + '&folderName=%s' % quote_plus(folderName)
			except:
				next = ''

			# Process each item (Umbrella Lines 1328-1350)
			for item in items:
				try:
					values = {}
					values['next'] = next

					# KEY FIELDS from Umbrella! (Lines 1332-1337)
					values['added'] = item.get('listed_at', '')
					values['paused_at'] = item.get('paused_at', '')  # For unfinished!
					try:
						values['progress'] = item['progress']
					except:
						values['progress'] = ''
					try:
						values['lastplayed'] = item['watched_at']  # For history!
					except:
						values['lastplayed'] = ''

					# Movie data (Umbrella Lines 1338-1346)
					movie = item.get('movie') or item
					values['title'] = movie.get('title')
					values['originaltitle'] = values['title']
					values['year'] = str(movie.get('year', '')) if movie.get('year') else ''
					ids = movie.get('ids', {})
					values['imdb'] = str(ids.get('imdb', '')) if ids.get('imdb') else ''
					values['tmdb'] = str(ids.get('tmdb', '')) if ids.get('tmdb') else ''
					values['tvdb'] = ''
					values['mediatype'] = 'movies'

					self.list.append(values)

				except Exception as e:
					xbmc.log('[Eternity-MoviesExt] trakt_list item processing error: %s' % str(e), xbmc.LOGERROR)
					continue

			xbmc.log('[Eternity-MoviesExt] trakt_list processed %d movies' % len(self.list), xbmc.LOGDEBUG)
			return self.list

		except Exception as e:
			xbmc.log('[Eternity-MoviesExt] trakt_list ERROR: %s' % str(e), xbmc.LOGERROR)
			import traceback
			xbmc.log('[Eternity-MoviesExt] Traceback: %s' % traceback.format_exc(), xbmc.LOGERROR)
			return []

	# =========================================
	# UNFINISHED MOVIES - Uses trakt_list()
	# =========================================

	def unfinished(self, url):
		"""
		Umbrella unfinished() - Line 639
		Shows movies with playback progress (< 90%)
		EXACT UMBRELLA SORTING: paused_at DESC!
		"""
		try:
			xbmc.log('[Eternity-MoviesExt] unfinished called with url=%s' % url, xbmc.LOGDEBUG)

			# Check Trakt authentication
			traktCredentials = trakt.getTraktCredentialsInfo()
			if not traktCredentials:
				control.infoDialog('Bitte verbinde dich mit Trakt', time=2000)
				return

			# Resolve URL
			if url == 'traktunfinished':
				api_url = self.traktunfinished_link
			else:
				api_url = url

			xbmc.log('[Eternity-MoviesExt] Resolved API URL: %s' % api_url, xbmc.LOGDEBUG)

			# Use Umbrella's trakt_list() method!
			items = self.trakt_list(api_url, self.trakt_user)

			if not items:
				xbmc.log('[Eternity-MoviesExt] No items from trakt_list()', xbmc.LOGDEBUG)
				control.infoDialog('Keine Filme gefunden', time=2000)
				return

			# UMBRELLA EXACT SORT (Line 644): Sort by paused_at DESC
			items = sorted(items, key=lambda k: k.get('paused_at', ''), reverse=True)

			xbmc.log('[Eternity-MoviesExt] unfinished got %d movies (sorted by paused_at DESC)' % len(items), xbmc.LOGDEBUG)

			# PRESERVE SORT ORDER: Extract TMDB IDs in sorted order!
			tmdb_ids = []
			metadata_map = {}  # Store progress/paused_at by tmdb_id
			for item in items:
				tmdb_id = item.get('tmdb', '')
				if tmdb_id:
					tmdb_ids.append(tmdb_id)
					metadata_map[tmdb_id] = {
						'progress': item.get('progress', ''),
						'paused_at': item.get('paused_at', '')
					}

			if not tmdb_ids:
				control.infoDialog('Keine Filme gefunden', time=2000)
				return

			# CRITICAL: Pass sorted TMDB IDs to worker() - BUT worker() uses threading!
			self.movies.list = tmdb_ids
			self.movies.worker()  # Fetches TMDB metadata (but threading randomizes order!)

			# WORKER USES THREADING! Results come back in random order!
			# We MUST re-sort by the original tmdb_ids order!
			sorted_meta = []
			for tmdb_id in tmdb_ids:  # Loop through original sorted order
				# Find this movie in the metadata
				for movie_meta in self.movies.meta:
					if str(movie_meta.get('tmdb_id', '')) == tmdb_id:
						# Inject progress/paused_at
						if tmdb_id in metadata_map:
							movie_meta['progress'] = metadata_map[tmdb_id]['progress']
							movie_meta['paused_at'] = metadata_map[tmdb_id]['paused_at']
						sorted_meta.append(movie_meta)
						break

			# Display with Directory (NOW ACTUALLY SORTED!)
			self.movies.Directory(sorted_meta)

			xbmc.log('[Eternity-MoviesExt] unfinished displayed %d movies (sorted by paused_at DESC)' % len(self.movies.meta), xbmc.LOGDEBUG)

		except Exception as e:
			xbmc.log('[Eternity-MoviesExt] unfinished ERROR: %s' % str(e), xbmc.LOGERROR)
			import traceback
			xbmc.log('[Eternity-MoviesExt] Traceback: %s' % traceback.format_exc(), xbmc.LOGERROR)

	# =========================================
	# HISTORY - Uses trakt_list()
	# =========================================

	def history(self, url):
		"""
		Movie History with watched dates
		UMBRELLA: NO SORTING! Trakt API returns already sorted by watched_at DESC
		"""
		try:
			xbmc.log('[Eternity-MoviesExt] history called with url=%s' % url, xbmc.LOGDEBUG)

			# Check Trakt authentication
			traktCredentials = trakt.getTraktCredentialsInfo()
			if not traktCredentials:
				control.infoDialog('Bitte verbinde dich mit Trakt', time=2000)
				return

			# Resolve URL
			if url == 'trakthistory':
				api_url = self.trakthistory_link
			else:
				api_url = url

			xbmc.log('[Eternity-MoviesExt] Resolved API URL: %s' % api_url, xbmc.LOGDEBUG)

			# Use Umbrella's trakt_list() method!
			items = self.trakt_list(api_url, self.trakt_user)

			if not items:
				xbmc.log('[Eternity-MoviesExt] No items from trakt_list()', xbmc.LOGDEBUG)
				control.infoDialog('Keine Filme gefunden', time=2000)
				return

			# NO SORTING! Trakt /users/me/history already sorted by watched_at DESC!
			xbmc.log('[Eternity-MoviesExt] history got %d movies (NO sorting - Trakt pre-sorted)' % len(items), xbmc.LOGDEBUG)

			# PRESERVE TRAKT ORDER: Extract TMDB IDs in order!
			tmdb_ids = []
			metadata_map = {}  # Store lastplayed by tmdb_id
			for item in items:
				tmdb_id = item.get('tmdb', '')
				if tmdb_id:
					tmdb_ids.append(tmdb_id)
					metadata_map[tmdb_id] = {
						'lastplayed': item.get('lastplayed', '')
					}

			if not tmdb_ids:
				control.infoDialog('Keine Filme gefunden', time=2000)
				return

			# CRITICAL: Pass sorted TMDB IDs to worker() - BUT worker() uses threading!
			self.movies.list = tmdb_ids
			self.movies.worker()  # Fetches TMDB metadata (but threading randomizes order!)

			# WORKER USES THREADING! Results come back in random order!
			# We MUST re-sort by the original tmdb_ids order!
			sorted_meta = []
			for tmdb_id in tmdb_ids:  # Loop through original Trakt order
				# Find this movie in the metadata
				for movie_meta in self.movies.meta:
					if str(movie_meta.get('tmdb_id', '')) == tmdb_id:
						# Inject lastplayed
						if tmdb_id in metadata_map:
							movie_meta['lastplayed'] = metadata_map[tmdb_id]['lastplayed']
						sorted_meta.append(movie_meta)
						break

			# Display with Directory (NOW ACTUALLY SORTED by Trakt!)
			self.movies.Directory(sorted_meta)

			xbmc.log('[Eternity-MoviesExt] history displayed %d movies (preserving Trakt sort)' % len(self.movies.meta), xbmc.LOGDEBUG)

		except Exception as e:
			xbmc.log('[Eternity-MoviesExt] history ERROR: %s' % str(e), xbmc.LOGERROR)
			import traceback
			xbmc.log('[Eternity-MoviesExt] Traceback: %s' % traceback.format_exc(), xbmc.LOGERROR)

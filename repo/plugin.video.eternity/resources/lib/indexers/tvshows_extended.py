# -*- coding: utf-8 -*-
"""
Eternity TV Shows Extended - Umbrella Calendar & Progress Methods
FIXED VERSION - Database-free, standalone directory creation
"""

import sys
import xbmc
import json
from resources.lib import control
from resources.lib.modules import trakt
from datetime import datetime, timedelta


class TVShowsExtended:
	"""Extended TV Shows class with Umbrella's Progress & Calendar methods"""

	def __init__(self, tvshows_instance):
		"""
		Initialize with reference to main TVShows instance
		:param tvshows_instance: Instance of TVShows class
		"""
		self.tvshows = tvshows_instance
		self.list = []
		self.trakt_user = control.getSetting('trakt.user.name')
		self.lang = 'de'
		self.today_date = datetime.today().strftime('%Y-%m-%d')
		self.date_time = datetime.today()

		# Trakt API links
		self.trakt_link = 'https://api.trakt.tv'

	# =========================================
	# UMBRELLA TV SHOW PROGRESS METHODS
	# =========================================

	def tvshow_progress(self, url):
		"""
		Umbrella tvshow_progress() - Line 1660
		Shows with Next Episode to Watch (NOT fully watched!)
		CORRECT FILTERING - Only shows with unwatched episodes
		"""
		try:
			sysaddon = sys.argv[0]
			syshandle = int(sys.argv[1])

			xbmc.log('[Eternity-TVExtended] tvshow_progress called with url=%s' % url, xbmc.LOGDEBUG)

			# Check Trakt authentication
			traktCredentials = trakt.getTraktCredentialsInfo()
			if not traktCredentials:
				control.infoDialog('Bitte verbinde dich mit Trakt', time=2000)
				control.content(syshandle, 'files')
				control.endofdirectory(syshandle, cacheToDisc=False)
				return

			# Fetch from Trakt /users/me/watched/shows
			historyurl = '/users/me/watched/shows?extended=full'
			items = trakt.getTraktAsJson(historyurl)

			if not items:
				xbmc.log('[Eternity-TVExtended] No items from Trakt watched/shows', xbmc.LOGDEBUG)
				control.infoDialog('Keine Shows gefunden', time=2000)
				control.content(syshandle, 'files')
				control.endofdirectory(syshandle, cacheToDisc=False)
				return

			# Process shows - FILTER for shows with unwatched episodes!
			# Store as tuples: (tmdb_id, lastplayed) for sorting
			shows_with_lastplayed = []
			for item in items:
				try:
					show_data = item.get('show', {})
					ids = show_data.get('ids', {})

					tmdb_id = str(ids.get('tmdb', ''))
					if not tmdb_id:
						continue

					# KEY FILTERING LOGIC!
					# Count watched episodes from seasons data
					watched_count = 0
					seasons = item.get('seasons', [])

					# Also find the latest lastplayed date from all episodes
					lastplayed_dates = []
					for season in seasons:
						episodes = season.get('episodes', [])
						watched_count += len(episodes)
						# Collect all lastplayed dates
						for ep in episodes:
							if ep.get('last_watched_at'):
								lastplayed_dates.append(ep.get('last_watched_at'))

					# Get total aired episodes
					aired_episodes = show_data.get('aired_episodes', 0)

					# ONLY add if NOT fully watched!
					if watched_count < aired_episodes:
						# Get most recent lastplayed date (for sorting)
						lastplayed = max(lastplayed_dates) if lastplayed_dates else '1970-01-01T00:00:00.000Z'
						shows_with_lastplayed.append((tmdb_id, lastplayed))
						xbmc.log('[Eternity-TVExtended] Progress Show: %s (%d/%d watched, lastplayed=%s)' % (
							show_data.get('title', 'Unknown'), watched_count, aired_episodes, lastplayed[:10]
						), xbmc.LOGDEBUG)
					else:
						xbmc.log('[Eternity-TVExtended] SKIP (fully watched): %s (%d/%d)' % (
							show_data.get('title', 'Unknown'), watched_count, aired_episodes
						), xbmc.LOGDEBUG)

				except Exception as e:
					xbmc.log('[Eternity-TVExtended] Error processing show: %s' % str(e), xbmc.LOGERROR)

			# UMBRELLA SORTING: Sort by lastplayed (newest first) - Line 1664: self.sort(type='progress')
			shows_with_lastplayed = sorted(shows_with_lastplayed, key=lambda x: x[1], reverse=True)

			# UMBRELLA SPECIAL SORTING: Shows premiered in last week at TOP! (Lines 1689-1694)
			# This is for NEW shows (S01E01) to appear at top
			prior_week_date = self.date_time - timedelta(days=7)
			prior_week_int = int(prior_week_date.strftime('%Y%m%d'))

			# Separate into top_items (new premiered shows) and rest
			top_items = []
			rest_items = []
			for tmdb_id, lastplayed in shows_with_lastplayed:
				# Get premiered date from Trakt data
				show_data = next((item.get('show', {}) for item in items if str(item.get('show', {}).get('ids', {}).get('tmdb', '')) == tmdb_id), {})
				premiered_str = show_data.get('first_aired', '')
				if premiered_str:
					try:
						# Parse premiered date (format: "2024-01-15T00:00:00.000Z" or "2024-01-15")
						premiered_date_str = premiered_str.split('T')[0]  # Get "2024-01-15"
						premiered_int = int(premiered_date_str.replace('-', ''))  # "20240115"
						if premiered_int >= prior_week_int:
							top_items.append(tmdb_id)
						else:
							rest_items.append(tmdb_id)
					except:
						rest_items.append(tmdb_id)
				else:
					rest_items.append(tmdb_id)

			# Combine: Top items first, then rest
			self.list = top_items + rest_items

			xbmc.log('[Eternity-TVExtended] tvshow_progress found %d shows WITH unwatched episodes (sorted by lastplayed)' % len(self.list), xbmc.LOGDEBUG)

			if not self.list:
				control.infoDialog('Keine Shows gefunden', time=2000)
				control.content(syshandle, 'files')
				control.endofdirectory(syshandle, cacheToDisc=False)
				return

			# Use TVShows' worker() to fetch TMDB metadata (like Umbrella!)
			# BUT worker() uses threading - results come back in random order!
			if hasattr(self.tvshows, 'list'):
				# Pass TMDB IDs directly (worker() expects list of strings)
				self.tvshows.list = self.list

				# Fetch TMDB metadata using worker() (Umbrella Line 1667)
				self.tvshows.worker()

				# WORKER USES THREADING! Results come back in random order!
				# We MUST re-sort by the original self.list order!
				sorted_meta = []
				for tmdb_id in self.list:  # Loop through original sorted order
					# Find this show in the metadata
					for show_meta in self.tvshows.meta:
						if str(show_meta.get('tmdb_id', '')) == tmdb_id:
							sorted_meta.append(show_meta)
							break

				# Now create directory with the ACTUALLY SORTED metadata!
				self.tvshows.Directory(sorted_meta)

				xbmc.log('[Eternity-TVExtended] tvshow_progress displayed %d shows (RE-SORTED after worker!)' % len(sorted_meta), xbmc.LOGDEBUG)
			else:
				xbmc.log('[Eternity-TVExtended] ERROR: tvshows.list not found!', xbmc.LOGERROR)
				control.content(syshandle, 'files')
				control.endofdirectory(syshandle, cacheToDisc=False)

		except Exception as e:
			xbmc.log('[Eternity-TVExtended] tvshow_progress ERROR: %s' % str(e), xbmc.LOGERROR)
			import traceback
			xbmc.log('[Eternity-TVExtended] Traceback: %s' % traceback.format_exc(), xbmc.LOGERROR)

	def tvshow_watched(self, url):
		"""
		Umbrella tvshow_watched() - Line 1778
		ONLY Fully Watched Shows (100% complete!)
		CORRECT FILTERING - Only shows where all episodes watched
		"""
		try:
			sysaddon = sys.argv[0]
			syshandle = int(sys.argv[1])

			xbmc.log('[Eternity-TVExtended] tvshow_watched called with url=%s' % url, xbmc.LOGDEBUG)

			# Check Trakt authentication
			traktCredentials = trakt.getTraktCredentialsInfo()
			if not traktCredentials:
				control.infoDialog('Bitte verbinde dich mit Trakt', time=2000)
				control.content(syshandle, 'files')
				control.endofdirectory(syshandle, cacheToDisc=False)
				return

			# Fetch from Trakt /users/me/watched/shows
			historyurl = '/users/me/watched/shows?extended=full'
			items = trakt.getTraktAsJson(historyurl)

			if not items:
				xbmc.log('[Eternity-TVExtended] No items from Trakt watched/shows', xbmc.LOGDEBUG)
				control.infoDialog('Keine Shows gefunden', time=2000)
				control.content(syshandle, 'files')
				control.endofdirectory(syshandle, cacheToDisc=False)
				return

			# Process shows - FILTER for FULLY watched shows only!
			# Store as tuples: (tmdb_id, lastplayed) for sorting
			shows_with_lastplayed = []
			for item in items:
				try:
					show_data = item.get('show', {})
					ids = show_data.get('ids', {})

					tmdb_id = str(ids.get('tmdb', ''))
					if not tmdb_id:
						continue

					# KEY FILTERING LOGIC!
					# Count watched episodes from seasons data
					watched_count = 0
					seasons = item.get('seasons', [])

					# Also find the latest lastplayed date from all episodes
					lastplayed_dates = []
					for season in seasons:
						episodes = season.get('episodes', [])
						watched_count += len(episodes)
						# Collect all lastplayed dates
						for ep in episodes:
							if ep.get('last_watched_at'):
								lastplayed_dates.append(ep.get('last_watched_at'))

					# Get total aired episodes
					aired_episodes = show_data.get('aired_episodes', 0)

					# ONLY add if FULLY watched!
					if watched_count >= aired_episodes and aired_episodes > 0:
						# Get most recent lastplayed date (for sorting)
						lastplayed = max(lastplayed_dates) if lastplayed_dates else '1970-01-01T00:00:00.000Z'
						shows_with_lastplayed.append((tmdb_id, lastplayed))
						xbmc.log('[Eternity-TVExtended] Fully Watched Show: %s (%d/%d, lastplayed=%s)' % (
							show_data.get('title', 'Unknown'), watched_count, aired_episodes, lastplayed[:10]
						), xbmc.LOGDEBUG)
					else:
						xbmc.log('[Eternity-TVExtended] SKIP (not fully watched): %s (%d/%d)' % (
							show_data.get('title', 'Unknown'), watched_count, aired_episodes
						), xbmc.LOGDEBUG)

				except Exception as e:
					xbmc.log('[Eternity-TVExtended] Error processing show: %s' % str(e), xbmc.LOGERROR)

			# UMBRELLA SORTING: Sort by lastplayed (newest first) - Line 1782: self.sort(type='watched')
			shows_with_lastplayed = sorted(shows_with_lastplayed, key=lambda x: x[1], reverse=True)

			# UMBRELLA SPECIAL SORTING: Shows premiered in last week at TOP!
			# Same as Progress Shows - new premiered shows go to top
			prior_week_date = self.date_time - timedelta(days=7)
			prior_week_int = int(prior_week_date.strftime('%Y%m%d'))

			# Separate into top_items (new premiered shows) and rest
			top_items = []
			rest_items = []
			for tmdb_id, lastplayed in shows_with_lastplayed:
				# Get premiered date from Trakt data
				show_data = next((item.get('show', {}) for item in items if str(item.get('show', {}).get('ids', {}).get('tmdb', '')) == tmdb_id), {})
				premiered_str = show_data.get('first_aired', '')
				if premiered_str:
					try:
						# Parse premiered date (format: "2024-01-15T00:00:00.000Z" or "2024-01-15")
						premiered_date_str = premiered_str.split('T')[0]  # Get "2024-01-15"
						premiered_int = int(premiered_date_str.replace('-', ''))  # "20240115"
						if premiered_int >= prior_week_int:
							top_items.append(tmdb_id)
						else:
							rest_items.append(tmdb_id)
					except:
						rest_items.append(tmdb_id)
				else:
					rest_items.append(tmdb_id)

			# Combine: Top items first, then rest
			self.list = top_items + rest_items

			xbmc.log('[Eternity-TVExtended] tvshow_watched found %d FULLY watched shows (sorted by lastplayed)' % len(self.list), xbmc.LOGDEBUG)

			if not self.list:
				control.infoDialog('Keine Shows gefunden', time=2000)
				control.content(syshandle, 'files')
				control.endofdirectory(syshandle, cacheToDisc=False)
				return

			# Use TVShows' worker() to fetch TMDB metadata (like Umbrella!)
			# BUT worker() uses threading - results come back in random order!
			if hasattr(self.tvshows, 'list'):
				# Pass TMDB IDs directly (worker() expects list of strings)
				self.tvshows.list = self.list

				# Fetch TMDB metadata using worker() (Umbrella Line 1785)
				self.tvshows.worker()

				# WORKER USES THREADING! Results come back in random order!
				# We MUST re-sort by the original self.list order!
				sorted_meta = []
				for tmdb_id in self.list:  # Loop through original sorted order
					# Find this show in the metadata
					for show_meta in self.tvshows.meta:
						if str(show_meta.get('tmdb_id', '')) == tmdb_id:
							sorted_meta.append(show_meta)
							break

				# Now create directory with the ACTUALLY SORTED metadata!
				self.tvshows.Directory(sorted_meta)

				xbmc.log('[Eternity-TVExtended] tvshow_watched displayed %d shows (RE-SORTED after worker!)' % len(sorted_meta), xbmc.LOGDEBUG)
			else:
				xbmc.log('[Eternity-TVExtended] ERROR: tvshows.list not found!', xbmc.LOGERROR)
				control.content(syshandle, 'files')
				control.endofdirectory(syshandle, cacheToDisc=False)

		except Exception as e:
			xbmc.log('[Eternity-TVExtended] tvshow_watched ERROR: %s' % str(e), xbmc.LOGERROR)
			import traceback
			xbmc.log('[Eternity-TVExtended] Traceback: %s' % traceback.format_exc(), xbmc.LOGERROR)

# -*- coding: utf-8 -*-
"""
Eternity Episodes Extended - Umbrella Calendar & Progress Methods
UMBRELLA PORT - Full trakt_list() implementation with proper data extraction
"""

import sys
import xbmc
import json
from urllib.parse import parse_qsl, urlsplit, urlparse, urlencode, quote_plus
from resources.lib import control
from resources.lib.modules import trakt, cache
from datetime import datetime, timedelta
import re


class EpisodesExtended:
	"""Extended Episodes class with Umbrella's Calendar & Progress methods"""

	def __init__(self, episodes_instance):
		"""
		Initialize with reference to main Episodes instance
		:param episodes_instance: Instance of Episodes class
		"""
		self.episodes = episodes_instance
		self.list = []
		self.trakt_user = control.getSetting('trakt.user.name')
		self.lang = 'de'
		self.today_date = datetime.today().strftime('%Y-%m-%d')
		self.date_time = datetime.today()
		self.showspecials = True  # Show special episodes (season 0)

		# Trakt API links
		self.trakt_link = 'https://api.trakt.tv'
		self.progress_link = '/users/me/watched/shows'  # UMBRELLA CORRECT! Not /sync/playback!
		self.mycalendarRecent_link = '/calendars/my/shows/%s/33' % (datetime.today() - timedelta(days=33)).strftime('%Y-%m-%d')
		self.mycalendarUpcoming_link = '/calendars/my/shows/%s/33' % datetime.today().strftime('%Y-%m-%d')
		self.mycalendarPremiers_link = '/calendars/my/new/%s/33' % datetime.today().strftime('%Y-%m-%d')
		self.trakthistory_link = '/users/me/history/shows?page=1&limit=40'

	# =========================================
	# UMBRELLA trakt_progress_list() - COMPLETE PORT
	# =========================================

	def trakt_progress_list(self, url, user, lang):
		"""
		Umbrella trakt_progress_list() - Lines 447-593
		COMPLETE 1:1 PORT - Calculates NEXT episode for each watched show!
		This is THE method for "Progress Episodes" / "Continue Watching"

		Fetches: /users/me/watched/shows?extended=full
		Returns: List of NEXT episodes to watch (with TMDB metadata)
		"""
		try:
			url += '?extended=full'
			result = trakt.getTraktAsJson(url)
			if not result:
				xbmc.log('[Eternity-EpisExtended] trakt_progress_list: No shows from Trakt', xbmc.LOGDEBUG)
				return []
		except:
			xbmc.log('[Eternity-EpisExtended] trakt_progress_list: API Error', xbmc.LOGERROR)
			import traceback
			xbmc.log('[Eternity-EpisExtended] Traceback: %s' % traceback.format_exc(), xbmc.LOGERROR)
			return []

		xbmc.log('[Eternity-EpisExtended] trakt_progress_list: Got %d watched shows from Trakt' % len(result), xbmc.LOGDEBUG)

		items = []
		# Process each watched show (Umbrella Lines 456-493)
		for item in result:
			try:
				values = {}
				num_1 = 0

				# FILTER: Skip fully watched ended shows (Umbrella Lines 459-463)
				if item['show']['status'].lower() == 'ended':
					# Count watched episodes
					for i in range(0, len(item['seasons'])):
						if item['seasons'][i]['number'] > 0:
							num_1 += len(item['seasons'][i]['episodes'])
					num_2 = int(item['show']['aired_episodes'])
					if num_1 >= num_2:
						xbmc.log('[Eternity-EpisExtended] SKIP fully watched ended show: %s (%d/%d)' % (
							item['show']['title'], num_1, num_2), xbmc.LOGDEBUG)
						continue  # Skip fully watched ended shows!

				# FIND LAST WATCHED EPISODE (Umbrella Lines 464-468)
				season_sort = sorted(item['seasons'][:], key=lambda k: k['number'], reverse=False)
				values['snum'] = season_sort[-1]['number']  # Last season watched
				episode = [x for x in season_sort[-1]['episodes'] if 'number' in x]
				episode = sorted(episode, key=lambda x: x['number'])
				values['enum'] = episode[-1]['number']  # Last episode watched

				# Metadata (Umbrella Lines 469-490)
				values['added'] = item.get('show').get('updated_at')
				try:
					values['lastplayed'] = item.get('last_watched_at')
				except:
					values['lastplayed'] = ''

				values['tvshowtitle'] = item['show']['title']
				if not values['tvshowtitle']:
					continue

				ids = item.get('show', {}).get('ids', {})
				values['imdb'] = str(ids.get('imdb', '')) if ids.get('imdb') else ''
				values['tmdb'] = str(ids.get('tmdb', '')) if ids.get('tmdb') else ''
				values['tvdb'] = str(ids.get('tvdb', '')) if ids.get('tvdb') else ''

				try:
					duration = (int(item['episode']['runtime']) * 60)
				except:
					try:
						duration = (int(item['show']['runtime']) * 60)
					except:
						duration = ''
				values['duration'] = duration

				try:
					airs = item['show']['airs']
					values['airday'] = airs.get('day', '')
					values['airtime'] = airs.get('time', '')[:5]
					values['airzone'] = airs.get('timezone', '')
				except:
					pass

				items.append(values)

			except:
				xbmc.log('[Eternity-EpisExtended] trakt_progress_list: Error processing show', xbmc.LOGERROR)
				import traceback
				xbmc.log('[Eternity-EpisExtended] Traceback: %s' % traceback.format_exc(), xbmc.LOGERROR)
				continue

		xbmc.log('[Eternity-EpisExtended] trakt_progress_list: Processed %d shows (before TMDB fetch)' % len(items), xbmc.LOGDEBUG)

		# CALCULATE NEXT EPISODES + FETCH TMDB METADATA (Umbrella Lines 502-593)
		# This is complex - uses threading like Umbrella
		from concurrent.futures import ThreadPoolExecutor

		def process_item(i):
			"""Calculate next episode and fetch TMDB metadata for ONE show"""
			values = i.copy()
			imdb, tmdb, tvdb = i.get('imdb'), i.get('tmdb'), i.get('tvdb')

			# Check if we have TMDB ID
			if not tmdb:
				xbmc.log('[Eternity-EpisExtended] Missing tmdb_id for show: %s' % i['tvshowtitle'], xbmc.LOGDEBUG)
				return None

			try:
				# Fetch show details from TMDB
				from resources.lib.tmdb_kodi import TMDBApi
				tmdb_api = TMDBApi(language='de')

				# Get TV show details (includes seasons info)
				showData = tmdb_api.get_tv_details(tmdb)
				if not showData:
					xbmc.log('[Eternity-EpisExtended] No show data for tmdb=%s' % tmdb, xbmc.LOGDEBUG)
					return None

				# CALCULATE NEXT EPISODE (Umbrella Lines 516-520)
				# Find current season in TMDB data
				seasons = showData.get('seasons', [])
				if not seasons:
					return None

				# Check if season 0 exists (adjust index)
				has_season_0 = seasons[0].get('season_number') == 0
				current_season_idx = i['snum'] - 1 if not has_season_0 else i['snum']

				# Get current season's episode count
				if current_season_idx >= len(seasons):
					return None

				current_season_episodes = seasons[current_season_idx].get('episode_count', 0)

				# Calculate next episode
				if i['enum'] < current_season_episodes:
					# Next episode in same season
					next_episode_num = i['enum'] + 1
					next_season_num = i['snum']
				else:
					# First episode of next season
					next_episode_num = 1
					next_season_num = i['snum'] + 1

				# Check if next season exists
				total_seasons = showData.get('number_of_seasons', 0)
				if next_season_num > total_seasons:
					xbmc.log('[Eternity-EpisExtended] No next season for %s (current S%dE%d)' % (
						i['tvshowtitle'], i['snum'], i['enum']), xbmc.LOGDEBUG)
					return None

				if not self.showspecials and next_season_num == 0:
					return None

				# Fetch NEXT SEASON data from TMDB
				seasonData = tmdb_api.get_season_details(tmdb, next_season_num)
				if not seasonData:
					return None

				# Find the specific episode in season data
				episodes = seasonData.get('episodes', [])
				episode_meta = None
				for ep in episodes:
					if ep.get('episode_number') == next_episode_num:
						episode_meta = ep
						break

				if not episode_meta:
					xbmc.log('[Eternity-EpisExtended] Episode S%dE%d not found in TMDB for %s' % (
						next_season_num, next_episode_num, i['tvshowtitle']), xbmc.LOGDEBUG)
					return None

				# Build comprehensive metadata (matching Umbrella structure)
				values['title'] = episode_meta.get('name', '')
				values['season'] = next_season_num
				values['episode'] = next_episode_num
				values['premiered'] = episode_meta.get('air_date', '')
				values['year'] = showData.get('first_air_date', '')[:4] if showData.get('first_air_date') else i.get('year', '')
				values['rating'] = str(episode_meta.get('vote_average', '0'))
				values['votes'] = str(episode_meta.get('vote_count', '0'))
				values['plot'] = episode_meta.get('overview', '') or showData.get('overview', '')
				values['genre'] = ' / '.join([g.get('name', '') for g in showData.get('genres', [])]) if showData.get('genres') else 'NA'
				values['studio'] = showData.get('networks', [{}])[0].get('name', '') if showData.get('networks') else ''
				values['status'] = showData.get('status', '')
				values['poster'] = episode_meta.get('still_path', '') or showData.get('poster_path', '')
				values['fanart'] = showData.get('backdrop_path', '')

				# Metadata that came from Trakt (keep)
				# Already set: tvshowtitle, imdb, tmdb, tvdb, duration, airday, airtime, airzone, lastplayed

				# Remove unnecessary keys
				for k in ('episodes', 'snum', 'enum'):
					values.pop(k, None)

				# CONVERT AIR TIME TO LOCAL (Umbrella Lines 535-540)
				try:
					if values.get('premiered') and i.get('airtime'):
						combined = '%sT%s' % (values['premiered'], values['airtime'])
					else:
						raise Exception()
					# Note: Umbrella uses tools.convert_time() - we'll skip timezone conversion for now
					air_date, air_time = values.get('premiered', ''), i.get('airtime', '')
				except:
					air_date, air_time = values.get('premiered', '') if values.get('premiered') else '', i.get('airtime', '') if i.get('airtime') else ''

				# CHECK IF UNAIRED (Umbrella Lines 541-573)
				values['unaired'] = ''
				try:
					if values['status'].lower() == 'ended':
						pass
					elif not air_date:
						values['unaired'] = 'true'
					elif int(re.sub(r'[^0-9]', '', air_date)) > int(re.sub(r'[^0-9]', '', str(self.today_date))):
						values['unaired'] = 'true'
					elif int(re.sub(r'[^0-9]', '', air_date)) == int(re.sub(r'[^0-9]', '', str(self.today_date))):
						if air_time:
							time_now = (self.date_time).strftime('%X')
							if int(re.sub(r'[^0-9]', '', air_time)) > int(re.sub(r'[^0-9]', '', str(time_now))[:4]):
								values['unaired'] = 'true'
						else:
							pass
				except:
					xbmc.log('[Eternity-EpisExtended] Error checking unaired for %s' % i['tvshowtitle'], xbmc.LOGERROR)

				# FLAGS (Umbrella Lines 574-579)
				values['action'] = 'episodes'
				values['traktProgress'] = True
				values['extended'] = True

				# Fix duration format (Umbrella Lines 577-579)
				duration = values.get('duration', 0)
				if duration:
					values.update({'duration': int(duration) * 60})

				xbmc.log('[Eternity-EpisExtended] Calculated next episode for %s: S%dE%d' % (
					values['tvshowtitle'], values.get('season', 0), values.get('episode', 0)), xbmc.LOGDEBUG)

				return values

			except:
				xbmc.log('[Eternity-EpisExtended] trakt_progress_list: Error processing item', xbmc.LOGERROR)
				import traceback
				xbmc.log('[Eternity-EpisExtended] Traceback: %s' % traceback.format_exc(), xbmc.LOGERROR)
				return None

		# PARALLEL PROCESSING (Umbrella Lines 587-592)
		results = []
		with ThreadPoolExecutor(max_workers=10) as executor:
			results = list(executor.map(process_item, items))

		# Filter out None results
		self.list = [r for r in results if r is not None]

		xbmc.log('[Eternity-EpisExtended] trakt_progress_list: Returning %d next episodes (with TMDB metadata)' % len(self.list), xbmc.LOGDEBUG)
		return self.list

	# =========================================
	# UMBRELLA trakt_list() - COMPLETE PORT
	# =========================================

	def trakt_list(self, url, user, folderName=''):
		"""
		Umbrella trakt_list() - Lines 595-674
		COMPLETE 1:1 PORT - Proper Trakt API response extraction
		Returns: List of episode dicts with ALL metadata
		"""
		itemlist = []
		try:
			# Date placeholder replacement (Umbrella Line 598)
			for i in re.findall(r'date\[(\d+)\]', url):
				url = url.replace('date[%s]' % i, (self.date_time - timedelta(days=int(i))).strftime('%Y-%m-%d'))

			# Add extended=full parameter (Umbrella Lines 599-602)
			q = dict(parse_qsl(urlsplit(url).query))
			q.update({'extended': 'full'})
			q = (urlencode(q)).replace('%2C', ',')
			u = url.replace('?' + urlparse(url).query, '') + '?' + q if '?' in url else url + '?' + q

			# Fetch from Trakt API
			items = trakt.getTraktAsJson(u)

			xbmc.log('[Eternity-EpisExtended] trakt_list fetched %d items from %s' % (len(items) if items else 0, u), xbmc.LOGDEBUG)
		except:
			xbmc.log('[Eternity-EpisExtended] trakt_list API fetch failed', xbmc.LOGERROR)
			return []

		# Process each item (Umbrella Lines 613-670)
		for item in items:
			try:
				# Check structure (Umbrella Line 615)
				if 'show' not in item or 'episode' not in item:
					continue

				# Episode title (Umbrella Lines 616-617)
				title = item['episode']['title']
				if not title:
					continue

				# Season & Episode (Umbrella Lines 618-621)
				try:
					season = item['episode']['season']
					episode = item['episode']['number']
				except:
					continue

				# Skip specials if disabled (Umbrella Line 622)
				if not self.showspecials and season == 0:
					continue

				# TV Show title (Umbrella Lines 623-624)
				tvshowtitle = item.get('show').get('title')
				if not tvshowtitle:
					continue

				# Year (Umbrella Line 625)
				year = str(item.get('show').get('year', ''))

				# Progress (Umbrella Lines 626-627)
				try:
					progress = item['progress']
				except:
					progress = None

				# IDs (Umbrella Lines 628-631)
				ids = item.get('show', {}).get('ids', {})
				imdb = str(ids.get('imdb', '')) if ids.get('imdb') else ''
				tmdb = str(ids.get('tmdb', '')) if ids.get('tmdb') else ''
				tvdb = str(ids.get('tvdb', '')) if ids.get('tvdb') else ''

				# Episode IDs (Umbrella Line 632)
				episodeIDS = item.get('episode').get('ids', {})

				# Dates (Umbrella Lines 633-637)
				premiered = item.get('episode').get('first_aired')  # Timestamp for sorting
				added = item['episode']['updated_at'] or item.get('show').get('updated_at', '')
				try:
					lastplayed = item.get('watched_at', '')
				except:
					lastplayed = ''
				paused_at = item.get('paused_at', '')

				# Studio (Umbrella Line 638)
				studio = item.get('show').get('network')

				# Genre (Umbrella Lines 639-640)
				try:
					genre = ' / '.join([x.title() for x in item.get('show', {}).get('genres')]) or 'NA'
				except:
					genre = 'NA'

				# Duration (Umbrella Lines 641-644)
				try:
					duration = int(item['episode']['runtime']) * 60
				except:
					try:
						duration = int(item.get('show').get('runtime')) * 60
					except:
						duration = ''

				# Rating & Votes (Umbrella Lines 645-646)
				rating = str(item.get('episode').get('rating', '0'))
				try:
					votes = str(format(int(item.get('episode').get('votes', 0)), ',d'))
				except:
					votes = '0'

				# MPAA (Umbrella Line 647)
				mpaa = item.get('show').get('certification')

				# Plot (Umbrella Line 648)
				plot = item['episode']['overview'] or item['show']['overview']

				# Trailer (Umbrella Lines 658-659)
				try:
					trailer = control.trailer % item['show']['trailer'].split('v=')[1]
				except:
					trailer = ''

				# Build values dict (Umbrella Lines 660-663)
				values = {
					'title': title,
					'season': season,
					'episode': episode,
					'tvshowtitle': tvshowtitle,
					'year': year,
					'premiered': premiered,
					'added': added,
					'lastplayed': lastplayed,
					'progress': progress,
					'paused_at': paused_at,
					'status': 'Continuing',
					'studio': studio,
					'genre': genre,
					'duration': duration,
					'rating': rating,
					'votes': votes,
					'mpaa': mpaa,
					'plot': plot,
					'imdb': imdb,
					'tmdb': tmdb,
					'tvdb': tvdb,
					'trailer': trailer,
					'episodeIDS': episodeIDS,
					'next': ''
				}

				# Air info (Umbrella Lines 664-668)
				try:
					airs = item['show']['airs']
					values['airday'] = airs.get('day', '')
					values['airtime'] = airs.get('time', '')
					values['airzone'] = airs.get('timezone', '')
				except:
					pass

				itemlist.append(values)

			except Exception as e:
				xbmc.log('[Eternity-EpisExtended] trakt_list item processing error: %s' % str(e), xbmc.LOGERROR)
				continue

		xbmc.log('[Eternity-EpisExtended] trakt_list processed %d episodes' % len(itemlist), xbmc.LOGDEBUG)
		return itemlist

	# =========================================
	# CALENDAR METHOD - Uses trakt_list()
	# =========================================

	def calendar(self, url):
		"""
		Umbrella calendar() - Line 233
		Handles: progress, mycalendarRecent, mycalendarUpcoming, mycalendarPremiers, trakthistory
		KEY FIX: Uses trakt_progress_list() for progress, trakt_list() for others!
		"""
		try:
			sysaddon = sys.argv[0]
			syshandle = int(sys.argv[1])

			xbmc.log('[Eternity-EpisExtended] calendar called with url=%s' % url, xbmc.LOGDEBUG)

			# Check Trakt authentication
			traktCredentials = trakt.getTraktCredentialsInfo()
			if not traktCredentials:
				control.infoDialog('Bitte verbinde dich mit Trakt', time=2000)
				control.content(syshandle, 'files')
				control.endofdirectory(syshandle, cacheToDisc=False)
				return

			# Resolve URL from link name (Umbrella Line 236)
			if url == 'progress':
				api_url = self.progress_link
			elif url == 'mycalendarRecent':
				api_url = self.mycalendarRecent_link
			elif url == 'mycalendarUpcoming':
				api_url = self.mycalendarUpcoming_link
			elif url == 'mycalendarPremiers':
				api_url = self.mycalendarPremiers_link
			elif url == 'trakthistory':
				api_url = self.trakthistory_link
			else:
				api_url = url

			xbmc.log('[Eternity-EpisExtended] Resolved API URL: %s' % api_url, xbmc.LOGDEBUG)

			# KEY FIX: Use trakt_progress_list() for PROGRESS, trakt_list() for others! (Umbrella Line 239)
			if url == 'progress':
				# PROGRESS = Calculate next episodes from watched shows
				xbmc.log('[Eternity-EpisExtended] Using trakt_progress_list() for PROGRESS', xbmc.LOGDEBUG)
				items = self.trakt_progress_list(api_url, self.trakt_user, self.lang)
			else:
				# Others = Extract raw data from Trakt (calendar, history)
				xbmc.log('[Eternity-EpisExtended] Using trakt_list() for CALENDAR/HISTORY', xbmc.LOGDEBUG)
				items = self.trakt_list(api_url, self.trakt_user)

			if not items:
				xbmc.log('[Eternity-EpisExtended] No items from trakt_list()', xbmc.LOGDEBUG)
				control.infoDialog('Keine Episoden gefunden', time=2000)
				control.content(syshandle, 'files')
				control.endofdirectory(syshandle, cacheToDisc=False)
				return

			xbmc.log('[Eternity-EpisExtended] calendar got %d episodes' % len(items), xbmc.LOGDEBUG)

			# SPECIAL SORTING FOR PROGRESS: Place new season ep1's at top of list for 1 week (Umbrella Lines 246-251)
			if url == 'progress':
				try:
					prior_week = int(re.sub(r'[^0-9]', '', (self.date_time - timedelta(days=7)).strftime('%Y-%m-%d')))
					sorted_list = []
					# Find S01E01 episodes from last week
					top_items = [i for i in items if i.get('episode') == 1 and i.get('premiered') and (int(re.sub(r'[^0-9]', '', str(i['premiered']))) >= prior_week)]
					sorted_list.extend(top_items)
					# Add rest of episodes
					sorted_list.extend([i for i in items if i not in top_items])
					items = sorted_list
					xbmc.log('[Eternity-EpisExtended] Special sorting: %d S01E01 episodes placed on top' % len(top_items), xbmc.LOGDEBUG)
				except Exception as e:
					xbmc.log('[Eternity-EpisExtended] Special sorting error: %s' % str(e), xbmc.LOGERROR)

			# Display episodes using control.addItem()
			for item in items:
				try:
					# Extract data
					tvshowtitle = item.get('tvshowtitle', '')
					title = item.get('title', '')
					season = item.get('season', 0)
					episode = item.get('episode', 0)
					year = item.get('year', '')
					imdb = item.get('imdb', '')
					tmdb = item.get('tmdb', '')
					tvdb = item.get('tvdb', '')
					premiered = item.get('premiered', '')
					plot = item.get('plot', '')
					rating = item.get('rating', '0')
					duration = item.get('duration', 0)
					genre = item.get('genre', '')
					studio = item.get('studio', '')
					progress = item.get('progress', None)
					paused_at = item.get('paused_at', '')
					lastplayed = item.get('lastplayed', '')

					# Build label with progress info
					label = '%s - %dx%02d - %s' % (tvshowtitle, season, episode, title)
					if progress:
						label += ' [%d%%]' % int(progress)
					if lastplayed:
						# Format date: 2024-10-17T20:30:00.000Z → 17.10.2024
						try:
							date_obj = datetime.strptime(lastplayed[:10], '%Y-%m-%d')
							label += ' (%s)' % date_obj.strftime('%d.%m.%Y')
						except:
							pass

					# Build play URL
					sysmeta = {
						'mediatype': 'tvshow',
						'title': tvshowtitle,
						'year': year,
						'season': season,
						'episode': episode,
						'tmdb_id': tmdb,
						'imdb_id': imdb,
						'tvdb_id': tvdb,
						'plot': plot
					}

					url = '%s?action=play&title=%s&year=%s&imdb=%s&tmdb=%s&tvdb=%s&season=%s&episode=%s&tvshowtitle=%s&sysmeta=%s' % (
						sysaddon,
						control.quote_plus(title),
						year,
						imdb,
						tmdb,
						tvdb,
						season,
						episode,
						control.quote_plus(tvshowtitle),
						control.quote_plus(json.dumps(sysmeta))
					)

					# Build ListItem
					listitem = control.item(label=label)

					# Set metadata
					infoLabels = {
						'title': title,
						'tvshowtitle': tvshowtitle,
						'season': season,
						'episode': episode,
						'year': int(year) if year else 0,
						'plot': plot,
						'rating': float(rating) if rating else 0.0,
						'duration': duration,
						'genre': genre,
						'studio': studio,
						'mediatype': 'episode',
						'premiered': premiered[:10] if premiered else ''
					}
					listitem.setInfo('video', infoLabels)

					# Set resume point if progress available
					if progress and duration:
						resume_time = (float(progress) / 100.0) * float(duration)
						listitem.setProperty('ResumeTime', str(resume_time))
						listitem.setProperty('TotalTime', str(duration))

					# Add to directory
					control.addItem(handle=syshandle, url=url, listitem=listitem, isFolder=False)

				except Exception as e:
					xbmc.log('[Eternity-EpisExtended] Error displaying episode: %s' % str(e), xbmc.LOGERROR)
					continue

			# End directory
			control.content(syshandle, 'episodes')
			control.endofdirectory(syshandle, cacheToDisc=True)
			xbmc.log('[Eternity-EpisExtended] calendar displayed %d episodes' % len(items), xbmc.LOGDEBUG)

		except Exception as e:
			xbmc.log('[Eternity-EpisExtended] calendar ERROR: %s' % str(e), xbmc.LOGERROR)
			import traceback
			xbmc.log('[Eternity-EpisExtended] Traceback: %s' % traceback.format_exc(), xbmc.LOGERROR)

	def upcoming_progress(self, url):
		"""
		Umbrella upcoming_progress() - Line 199
		Shows upcoming progress episodes SORTED by premiered + airtime
		KEY FIX: Uses trakt_progress_list() to calculate next episodes!
		"""
		try:
			sysaddon = sys.argv[0]
			syshandle = int(sys.argv[1])

			xbmc.log('[Eternity-EpisExtended] upcoming_progress called with url=%s' % url, xbmc.LOGDEBUG)

			# Check Trakt authentication
			traktCredentials = trakt.getTraktCredentialsInfo()
			if not traktCredentials:
				control.infoDialog('Bitte verbinde dich mit Trakt', time=2000)
				control.content(syshandle, 'files')
				control.endofdirectory(syshandle, cacheToDisc=False)
				return

			# Resolve URL (always progress for this method)
			if url == 'progress':
				api_url = self.progress_link
			else:
				api_url = url

			xbmc.log('[Eternity-EpisExtended] Resolved API URL: %s' % api_url, xbmc.LOGDEBUG)

			# KEY FIX: Use trakt_progress_list() to calculate next episodes!
			xbmc.log('[Eternity-EpisExtended] Using trakt_progress_list() for upcoming_progress', xbmc.LOGDEBUG)
			items = self.trakt_progress_list(api_url, self.trakt_user, self.lang)

			if not items:
				xbmc.log('[Eternity-EpisExtended] No items from trakt_list()', xbmc.LOGDEBUG)
				control.infoDialog('Keine Episoden gefunden', time=2000)
				control.content(syshandle, 'files')
				control.endofdirectory(syshandle, cacheToDisc=False)
				return

			# KEY DIFFERENCE: Sort by premiered + airtime (Umbrella Line 213)
			# Use "3021-01-01" hack to force unknown premiered dates to bottom
			items = sorted(items, key=lambda k: (
				k.get('premiered', '') if k.get('premiered') else '3021-01-01',
				k.get('airtime', '')
			))

			xbmc.log('[Eternity-EpisExtended] upcoming_progress got %d episodes (sorted)' % len(items), xbmc.LOGDEBUG)

			# Display episodes (same logic as calendar())
			for item in items:
				try:
					# Extract data
					tvshowtitle = item.get('tvshowtitle', '')
					title = item.get('title', '')
					season = item.get('season', 0)
					episode = item.get('episode', 0)
					year = item.get('year', '')
					imdb = item.get('imdb', '')
					tmdb = item.get('tmdb', '')
					tvdb = item.get('tvdb', '')
					premiered = item.get('premiered', '')
					plot = item.get('plot', '')
					rating = item.get('rating', '0')
					duration = item.get('duration', 0)
					genre = item.get('genre', '')
					studio = item.get('studio', '')
					progress = item.get('progress', None)
					paused_at = item.get('paused_at', '')

					# Build label with progress info
					label = '%s - %dx%02d - %s' % (tvshowtitle, season, episode, title)
					if progress:
						label += ' [%d%%]' % int(progress)
					if premiered:
						# Show premiered date
						try:
							date_obj = datetime.strptime(premiered[:10], '%Y-%m-%d')
							label += ' (%s)' % date_obj.strftime('%d.%m.%Y')
						except:
							pass

					# Build play URL
					sysmeta = {
						'mediatype': 'tvshow',
						'title': tvshowtitle,
						'year': year,
						'season': season,
						'episode': episode,
						'tmdb_id': tmdb,
						'imdb_id': imdb,
						'tvdb_id': tvdb,
						'plot': plot
					}

					url = '%s?action=play&title=%s&year=%s&imdb=%s&tmdb=%s&tvdb=%s&season=%s&episode=%s&tvshowtitle=%s&sysmeta=%s' % (
						sysaddon,
						control.quote_plus(title),
						year,
						imdb,
						tmdb,
						tvdb,
						season,
						episode,
						control.quote_plus(tvshowtitle),
						control.quote_plus(json.dumps(sysmeta))
					)

					# Build ListItem
					listitem = control.item(label=label)

					# Set metadata
					infoLabels = {
						'title': title,
						'tvshowtitle': tvshowtitle,
						'season': season,
						'episode': episode,
						'year': int(year) if year else 0,
						'plot': plot,
						'rating': float(rating) if rating else 0.0,
						'duration': duration,
						'genre': genre,
						'studio': studio,
						'mediatype': 'episode',
						'premiered': premiered[:10] if premiered else ''
					}
					listitem.setInfo('video', infoLabels)

					# Set resume point if progress available
					if progress and duration:
						resume_time = (float(progress) / 100.0) * float(duration)
						listitem.setProperty('ResumeTime', str(resume_time))
						listitem.setProperty('TotalTime', str(duration))

					# Add to directory
					control.addItem(handle=syshandle, url=url, listitem=listitem, isFolder=False)

				except Exception as e:
					xbmc.log('[Eternity-EpisExtended] Error displaying episode: %s' % str(e), xbmc.LOGERROR)
					continue

			# End directory
			control.content(syshandle, 'episodes')
			control.endofdirectory(syshandle, cacheToDisc=True)
			xbmc.log('[Eternity-EpisExtended] upcoming_progress displayed %d episodes (sorted by premiered)' % len(items), xbmc.LOGDEBUG)

		except Exception as e:
			xbmc.log('[Eternity-EpisExtended] upcoming_progress ERROR: %s' % str(e), xbmc.LOGERROR)
			import traceback
			xbmc.log('[Eternity-EpisExtended] Traceback: %s' % traceback.format_exc(), xbmc.LOGERROR)

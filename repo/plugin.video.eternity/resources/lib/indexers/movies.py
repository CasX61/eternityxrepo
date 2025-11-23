

#2021-07-15
# edit 2025-08-02 switch from treads to concurrent.futures 

import sys
import datetime, time, json
from concurrent.futures import ThreadPoolExecutor
from resources.lib.tmdb_old import cTMDB
from resources.lib.tmdb_kodi import TMDBApi
from resources.lib.indexers import navigator
from resources.lib import searchDB, playcountDB, art, control, log_utils
from resources.lib.control import getKodiVersion, iteritems

if int(getKodiVersion()) >= 20: from infotagger.listitem import ListItemInfoTag

_params = dict(control.parse_qsl(sys.argv[2].replace('?',''))) if len(sys.argv) > 1 else dict()

class movies:
	def __init__(self):
		self.list = []
		self.meta = []
		self.total_pages = 0
		self.next_pages = 0
		self.query = ''
		self.activeSearchDB = 'TMDB'
		#self.setSearchDB() # TODO different search providers
		self.playcount = 0
		self.search_direct = False

		# Initialize new Kodi-based TMDB API
		self.tmdb_api = TMDBApi(language='de')

		self.datetime = (datetime.datetime.utcnow() - datetime.timedelta(hours=5))
		self.systime = (self.datetime).strftime('%Y%m%d%H%M%S%f')

	def get(self, params):
		try:
			# Check if this is a Trakt URL
			url = params.get('url')
			if url and url.startswith('trakt_'):
				list_id = params.get('list_id')
				list_owner = params.get('list_owner')
				self.getTraktMovies(url, list_id, list_owner)
				# Skip "nothing found" check for trakt_liked_lists (already shows menu)
				if url != 'trakt_liked_lists':
					if self.list == None or len(self.list) == 0:
						return control.infoDialog("Nichts gefunden", time=2000)
					self.getDirectory(params)
				return

			# Regular TMDB search using new Kodi API
			self.next_pages = int(params.get('page'))
			self.query = params.get('query')

			# Use new TMDB API with advanced search
			search_results = self.tmdb_api.search_movie_advanced(params.get('query'))

			if search_results and len(search_results) > 0:
				# Convert to old format for compatibility
				self.list = self._convert_kodi_results(search_results)
				self.total_pages = 1  # Advanced search returns best results in one go
			else:
				# Fallback to old API if new one fails
				try:
					self.list, self.total_pages = cTMDB().search_term('movie', params.get('query'), params.get('page'))
				except:
					self.list = []
					self.total_pages = 0

			if self.list == None or len(self.list) == 0:  # nichts gefunden
				return control.infoDialog("Nichts gefunden", time=2000)

			self.search_direct = True
			self.getDirectory(params)
			searchDB.save_query(params.get('query'), params.get('action'))
		except:
			return

	def getDirectory(self, params):
		try:
			if params.get('next_pages'): self.next_pages = params.get('next_pages')
			if params.get('total_pages'): self.total_pages = params.get('total_pages')
			if params.get('list'): self.list = params.get('list')

			# Skip worker if we already have full metadata from Kodi API
			if not self.search_direct:
				self.worker()

			if self.list == None or len(self.list) == 0:	#nichts gefunden
				return control.infoDialog("Nichts gefunden", time=2000)
			self.Directory(self.list)
			return self.list
		except:
			return


	def search(self):
		# TODO different search providers
		#navigator.navigator().addDirectoryItem("DB für Suche auswählen", 'movieChangeSearchDB', self.activeSearchDB + '.png', 'DefaultMovies.png', isFolder=False)
		navigator.navigator().addDirectoryItem("[B]Filme - neue Suche %s[/B]" % self.activeSearchDB , 'searchNew&table=movies', self.activeSearchDB + '_search.png', 'DefaultAddonsSearch.png',
											   isFolder=False, context=('Einstellungen', 'addonSettings'))
		match = searchDB.getSearchTerms('movies')
		lst = []
		delete_option = False
		#for i in match:
		for index, i in enumerate(match):
			term = control.py2_encode(i['query'])
			if term not in lst:
				delete_option = True
				navigator.navigator().addDirectoryItem(term, 'movies&page=1&query=%s' % term, '_search.png',
													   'DefaultAddonsSearch.png', isFolder=True,
													   context=("Suchanfrage löschen", 'searchDelTerm&table=movies&name=%s' % index))
				lst += [(term)]

		if delete_option:
			navigator.navigator().addDirectoryItem("[B]Suchverlauf löschen[/B]", 'searchClear&table=movies', 'tools.png', 'DefaultAddonProgram.png', isFolder=False)
		navigator.navigator()._endDirectory('', False) # addons  videos  files


#TODO https://forum.kodi.tv/showthread.php?tid=199579
	# def setSearchDB(self, new=''):
	#	 if control.getSetting('active.SearchDB.movie'):
	#		 _searchDB = control.getSetting('active.SearchDB.movie')
	#		 if new != '':
	#			 control.setSetting('active.SearchDB.movie', new)
	#			 _searchDB = new
	#		 self.activeSearchDB  = _searchDB
	#	 else:
	#		 control.setSetting('active.SearchDB.movie', 'tmdb')
	#		 self.activeSearchDB = 'tmdb'
	#
	# def changeSearchDB(self):
	#	 active = control.getSetting('active.SearchDB.movie')
	#	 data = []
	#	 for i in ['tmdb', 'trakt']:
	#		 if i == active: continue
	#		 data.append('wechseln zu ' + i.upper())
	#	 index = control.dialog.contextmenu(data)
	#	 if index == -1:
	#		 return
	#	 term = data[index].lower().split()[-1]
	#	 self.setSearchDB(term)
	#	 url = '%s?action=movieSearch' % sys.argv[0]
	#	 control.execute('Container.Update(%s)' % url)


	def worker(self):
		try:
			self.meta = []
			with ThreadPoolExecutor() as executor:
				executor.map(self.super_meta, self.list)
			self.meta = sorted(self.meta, key=lambda k: k['title'])
			#self.list = [i for i in self.meta if i['votes'] > 10 and i['rating'] > 4]
			self.list = []
			for i in self.meta:
				if self.search_direct:
					self.list.append(i)
				else:
					if 'votes' in i and i['votes'] > 10 and 'rating' in i and i['rating'] > 4: self.list.append(i)
					if not 'votes' in i: self.list.append(i)
		except:
			log_utils.error()

	def super_meta(self, id, **kwargs):
		try:
			# Extract tmdb_id if we received a dict from new Kodi API
			if isinstance(id, dict):
				tmdb_id = id.get('tmdb_id', id)
			else:
				tmdb_id = id

			# TODO different search providers
			meta = cTMDB().get_meta('movie', '', '', tmdb_id, advanced='true')
			try:
				playcount = playcountDB.getPlaycount('movie', 'imdb_id', meta['imdb_id']) # mediatype, column_names, column_value, season=0, episode=0
				playcount = playcount if playcount else 0
				meta.update({'playcount': playcount})
			except:
				pass
			if not 'poster' in meta or meta['poster'] == '':
				poster = art.getMovie_art(meta['tmdb_id'], meta['imdbnumber'])
				meta.update({'poster': poster})
			#meta.update({'mediatype': 'movie'})
			self.meta.append(meta)
			return meta
		except:
			pass

	def getTraktMovies(self, url, list_id=None, list_owner=None):
		"""
		Get movies from Trakt API
		Converts Trakt data to TMDB IDs for metadata lookup
		"""
		try:
			from resources.lib.modules import trakt
			import xbmc

			# Map URL to Trakt function
			if url == 'trakt_collection':
				items = trakt.getMovieCollection()
			elif url == 'trakt_watchlist':
				items = trakt.getMovieWatchlist()
			elif url == 'trakt_history':
				items = trakt.getMovieHistory()
			elif url == 'trakt_unfinished':
				# Phase 1.6: Unfinished Movies
				items = trakt.getUnfinishedMovies()
			elif url == 'trakt_recommendations':
				# Phase 1.8: Recommendations
				items = trakt.getRecommendedMovies()
			elif url == 'trakt_liked_lists':
				# Phase 1.9: Liked Lists - Show list selection first
				self._showLikedListsMenu('movie')
				return
			elif url == 'trakt_userlist' and list_id:
				# Get items from specific user list
				# list_owner is passed from _showLikedListsMenu
				if not list_owner:
					xbmc.log('[Eternity] getTraktMovies: No list_owner provided, using current user', xbmc.LOGWARNING)
					list_owner = control.getSetting('trakt.user.name')
				xbmc.log('[Eternity] getTraktMovies: Fetching list %s from owner %s' % (list_id, list_owner), xbmc.LOGINFO)
				items = trakt.getListItems(list_owner, list_id, 'movies')
			else:
				items = None

			if not items:
				xbmc.log('[Eternity] getTraktMovies: No items returned from Trakt for url=%s' % url, xbmc.LOGWARNING)
				self.list = []
				return

			xbmc.log('[Eternity] getTraktMovies: Got %d items from Trakt for url=%s' % (len(items), url), xbmc.LOGINFO)

			# Convert Trakt items to TMDB IDs
			self.list = []
			for item in items:
				try:
					# Handle different response structures
					if 'movie' in item:
						# Direct from API: {'movie': {'ids': {...}}}
						movie = item['movie']
						imdb_id = movie['ids'].get('imdb')
						tmdb_id = movie['ids'].get('tmdb')
					elif 'ids' in item:
						# Old structure: {'ids': {'imdb': '...', 'tmdb': '...'}}
						imdb_id = item['ids'].get('imdb')
						tmdb_id = item['ids'].get('tmdb')
					else:
						# New simplified structure: {'imdb': '...', 'tmdb': '...'}
						imdb_id = item.get('imdb')
						tmdb_id = item.get('tmdb')

					# Prefer TMDB ID, fallback to IMDB
					if tmdb_id:
						self.list.append(str(tmdb_id))
						xbmc.log('[Eternity] Added TMDB ID: %s' % tmdb_id, xbmc.LOGDEBUG)
					elif imdb_id:
						# Try to get TMDB ID from IMDB
						xbmc.log('[Eternity] No TMDB ID, trying to lookup from IMDB: %s' % imdb_id, xbmc.LOGDEBUG)
						# For now just skip items without TMDB ID
						pass
				except Exception as e:
					xbmc.log('[Eternity] Error processing Trakt item: %s' % str(e), xbmc.LOGWARNING)
					pass

			xbmc.log('[Eternity] getTraktMovies: Converted to %d TMDB IDs' % len(self.list), xbmc.LOGINFO)
			# IMPORTANT: search_direct = False so worker() will fetch metadata from TMDB!
			self.search_direct = False
		except Exception as e:
			import xbmc
			xbmc.log('[Eternity] getTraktMovies ERROR: %s' % str(e), xbmc.LOGERROR)
			log_utils.error()
			self.list = []

	def userlists(self):
		"""
		Get and display Trakt user lists for movies
		"""
		try:
			from resources.lib.modules import trakt

			if not trakt.getTraktCredentialsInfo():
				control.infoDialog('Trakt Konto erforderlich', sound=True, icon='INFO')
				control.content(int(sys.argv[1]), 'files')
				control.directory(int(sys.argv[1]), cacheToDisc=False)
				return

			# Get user's lists from Trakt
			lists = trakt.getUserLists()

			if not lists:
				control.infoDialog('Keine Listen gefunden', time=2000)
				control.content(int(sys.argv[1]), 'files')
				control.directory(int(sys.argv[1]), cacheToDisc=False)
				return

			# Display lists
			for list_item in lists:
				try:
					name = list_item.get('name', 'Unbekannte Liste')
					list_id = list_item['ids']['slug']
					item_count = list_item.get('item_count', 0)

					# Format display name with item count
					label = '%s (%d)' % (name, item_count)

					# Create URL for list items
					url = '%s?action=movies&url=trakt_userlist&list_id=%s' % (sys.argv[0], list_id)

					# Create list item
					listitem = control.item(label=label, offscreen=True)
					listitem.setArt({'icon': 'DefaultMovies.png', 'poster': 'DefaultMovies.png'})
					listitem.setInfo('video', {'title': label, 'plot': name})

					control.addItem(handle=int(sys.argv[1]), url=url, listitem=listitem, isFolder=True)
				except:
					log_utils.error()

			control.content(int(sys.argv[1]), 'files')
			control.directory(int(sys.argv[1]), cacheToDisc=True)

		except Exception as e:
			log_utils.error('Movie Userlists Error: %s' % str(e))
			control.content(int(sys.argv[1]), 'files')
			control.directory(int(sys.argv[1]), cacheToDisc=False)

	def _convert_kodi_results(self, kodi_results):
		"""
		Convert Kodi TMDB API results to old format for compatibility

		Args:
			kodi_results (list): Results from tmdb_kodi.TMDBApi

		Returns:
			list: Results in old format
		"""
		converted = []
		for item in kodi_results:
			# Extract year from release_date
			year = ''
			if item.get('release_date'):
				year = item['release_date'][:4]

			converted_item = {
				'tmdb_id': str(item.get('id', '')),
				'title': item.get('title', ''),
				'originaltitle': item.get('original_title', ''),
				'year': year,
				'premiered': item.get('release_date', ''),
				'rating': str(item.get('vote_average', '0')),
				'votes': str(item.get('vote_count', '0')),
				'plot': item.get('overview', ''),
				'poster': self.tmdb_api.get_poster_url(item.get('poster_path')),
				'fanart': self.tmdb_api.get_fanart_url(item.get('backdrop_path')),
				'mediatype': 'movie'
			}

			# Add to list
			converted.append(converted_item)

		return converted

	def Directory(self, items):
		if items == None or len(items) == 0:
			control.idle()
			sys.exit()
		sysaddon = sys.argv[0]
		syshandle = int(sys.argv[1])

		addonPoster, addonBanner = control.addonPoster(), control.addonBanner()
		addonFanart, settingFanart = control.addonFanart(), control.getSetting('fanart')

		# Check if Trakt is authenticated
		from resources.lib.modules import trakt
		traktCredentials = trakt.getTraktCredentialsInfo()

		watchedMenu = "In %s [I]Gesehen[/I]" % control.addonName
		unwatchedMenu = "In %s [I]Ungesehen[/I]" % control.addonName
		traktManagerMenu = "[B]Trakt-Manager[/B]"
		for i in items:
			try:
				title = i['title'] if 'title' in i else i['originaltitle']
				# Allow non-ASCII titles (anime, foreign films, etc.)
				# if not title.isascii(): continue
				try:
					label = '%s (%s)' % (title, i['year'])  # show in list
				except:
					label = title

				sysname = label

				if 'premiered' in i:
					if datetime.datetime(*(time.strptime(i['premiered'], "%Y-%m-%d")[0:6])) > datetime.datetime.now():
						label = '[COLOR=red][I]{}[/I][/COLOR]'.format(label) # ffcc0000
				else:
					label = '[COLOR=red][I]{}[/I][/COLOR]'.format(label)

				meta = dict((k, v) for k, v in iteritems(i))
				if not 'duration' in i or i['duration'] == 0: meta.update({'duration': str(120 * 60)})

				poster = i['poster'] if 'poster' in i and 'http' in i['poster'] else addonPoster
				fanart = i['fanart'] if 'fanart' in i and 'http' in i['fanart'] else addonFanart
				meta.update({'poster': poster})
				meta.update({'fanart': fanart})
				meta.update({'systitle': title})
				meta.update({'sysname': sysname})

				_sysmeta = control.quote_plus(json.dumps(meta))

				item = control.item(label=label, offscreen=True)
				item.setArt({'poster': poster, 'banner': addonBanner})
				if settingFanart == 'true': item.setProperty('Fanart_Image', fanart)

				cm = []
				try:
					playcount = i['playcount'] if 'playcount' in i else 0
					if playcount == 1:
						cm.append((unwatchedMenu, 'RunPlugin(%s?action=UpdatePlayCount&meta=%s&playCount=0)' % (sysaddon, _sysmeta)))
						meta.update({'playcount': 1, 'overlay': 7})
					else:
						cm.append((watchedMenu, 'RunPlugin(%s?action=UpdatePlayCount&meta=%s&playCount=1)' % (sysaddon, _sysmeta)))
						meta.update({'playcount': 0, 'overlay': 6})
				except:
					pass

				# Add Trakt Manager if user is authenticated
				if traktCredentials:
					try:
						# Get IMDB ID for Trakt
						imdb_id = i.get('imdb', '') or i.get('imdb_id', '')
						if imdb_id and not imdb_id.startswith('tt'):
							imdb_id = 'tt' + imdb_id

						if imdb_id:
							cm.append((traktManagerMenu, 'RunPlugin(%s?action=traktManager&name=%s&imdb=%s&content=movie)' % (
								sysaddon,
								control.quote_plus(title.encode('utf-8')),
								imdb_id
							)))
					except:
						pass

				cm.append(('Einstellungen', 'RunPlugin(%s?action=addonSettings)' % sysaddon))
				item.addContextMenuItems(cm)

				if 'plot' in i:
					plot = i['plot']
				else:
					plot = ''

				votes = ''
				if 'rating' in i and i['rating'] != '':
					if 'votes' in i: votes = '(%s)' % str(i['votes']).replace(',', '')
					plot = '[COLOR blue]Bewertung :  %.1f  %s[/COLOR]%s%s' % (float(i['rating']), votes, "\n\n", plot)
				meta.update({'plot': plot})
				aActors = []
				if 'cast' in i and i['cast']: aActors = i['cast']

				 ## supported infolabels: https://codedocs.xyz/AlwinEsch/kodi/group__python__xbmcgui__listitem.html#ga0b71166869bda87ad744942888fb5f14
				# remove unsupported infolabels
				meta.pop('cast', None)  # ersetzt durch item.setCast(i['cast'])
				meta.pop('fanart', None)
				meta.pop('tmdb_id', None)
				meta.pop('originallanguage', None)
				meta.pop('budget', None)
				meta.pop('revenue', None)
				meta.pop('sysname', None)
				meta.pop('systitle', None)

				sysmeta = control.quote_plus(json.dumps(meta))
				url = '%s?action=play&sysmeta=%s' % (sysaddon, sysmeta)

				meta.pop('poster', None)
				meta.pop('imdb_id', None)
				meta.pop('aliases', None)
				meta.pop('backdrop_url', None)
				meta.pop('cover_url', None)
# TODO
				# gefakte Video/Audio Infos
				# video_streaminfo = {'codec': 'h264', "width": 1920, "height": 1080}
				# audio_streaminfo = {'codec': 'dts', 'channels': 6, 'language': 'de'}
				video_streaminfo = {}
				audio_streaminfo = {}

				if int(getKodiVersion()) <= 19:
					if aActors: item.setCast(aActors)
					item.setInfo(type='Video', infoLabels=meta)
					item.addStreamInfo('video', video_streaminfo)
					item.addStreamInfo('audio', audio_streaminfo)
				else:
					info_tag = ListItemInfoTag(item, 'video')
					info_tag.set_info(meta)
					"""
					stream_details = {
							'video': [{videostream_1_values}, {videostream_2_values} ...],
							'audio': [{audiostream_1_values}, {audiostream_2_values} ...],
							'subtitle': [{subtitlestream_1_values}, {subtitlestream_2_values} ...]}
					"""
					stream_details = {
						'video': [video_streaminfo],
						'audio': [audio_streaminfo]}

					info_tag.set_stream_details(stream_details)
					info_tag.set_cast(aActors)

				control.addItem(handle=syshandle, url=url, listitem=item, isFolder=False)
			except Exception as e:
				print(e)
				pass

		# nächste Seite
		try:
			self.next_pages = self.next_pages + 1
			if self.next_pages <= self.total_pages:
				if self.query:
					url = '%s?action=movies&url=&page=%s&query=%s' % (sys.argv[0], self.next_pages, self.query )
				else:
					url = '%s?action=listings' % sys.argv[0]
					url += '&media_type=%s' % _params.get('media_type')
					url += '&next_pages=%s' % self.next_pages
					url += '&url=%s' % control.quote_plus(_params.get('url'))
				item = control.item(label="Nächste Seite")
				icon = control.addonNext()
				item.setArt({'icon': icon, 'thumb': icon, 'poster': icon, 'banner': icon})
				if not addonFanart == None: item.setProperty('Fanart_Image', addonFanart)
				
				#  -> gesehen/ungesehen im cm und "Keine Informationen verfügbar" ausblenden (abhängig von control.content() )
				video_streaminfo = {'overlay': 4, 'plot': 'Â '}  # alt255

				if int(getKodiVersion()) <= 19:
					item.setInfo('video', video_streaminfo)
				else:
					stream_details = {'video': [video_streaminfo]}
					info_tag = ListItemInfoTag(item, 'video')
					info_tag.set_stream_details(stream_details)
				control.addItem(handle=syshandle, url=url, listitem=item, isFolder=True)
		except:
			pass

		control.content(syshandle, 'movies')
		control.plugincategory(syshandle, control.addonVersion)
		control.endofdirectory(syshandle, cacheToDisc=True)

	def _showLikedListsMenu(self, content_type='movie'):
		"""
		Phase 1.9: Show menu of liked lists for movies
		"""
		try:
			from resources.lib.modules import trakt
			from resources.lib.indexers import navigator
			import sys
			import xbmc

			# Get syshandle from Kodi plugin args
			syshandle = int(sys.argv[1])

			# Get liked lists from Trakt
			liked_lists = trakt.getLikedLists()

			if not liked_lists:
				xbmc.log('[Eternity] No liked lists found', xbmc.LOGINFO)
				control.infoDialog('Keine gelikten Listen gefunden', time=2000)
				self.list = []
				return

			# Display each liked list as a menu item
			for list_item in liked_lists:
				try:
					list_name = list_item['list']['name']
					list_owner = list_item['list']['user']['ids']['slug']
					list_id = list_item['list']['ids']['slug']
					item_count = list_item['list'].get('item_count', 0)

					# Create directory item for this list
					label = '[%s] %s (%d)' % (list_owner, list_name, item_count)
					navigator.navigator().addDirectoryItem(
						label,
						'movies&url=trakt_userlist&list_id=%s&list_owner=%s' % (list_id, list_owner),
						'trakt.png',
						'DefaultMovies.png'
					)
				except Exception as e:
					xbmc.log('[Eternity] Error processing liked list: %s' % str(e), xbmc.LOGERROR)
					pass

			# End directory
			control.content(syshandle, 'files')
			control.endofdirectory(syshandle, cacheToDisc=True)

		except Exception as e:
			import xbmc
			xbmc.log('[Eternity] _showLikedListsMenu error: %s' % str(e), xbmc.LOGERROR)
			self.list = []


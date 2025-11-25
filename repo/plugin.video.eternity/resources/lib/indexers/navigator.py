

#2021-07-14
# edit 2025-06-12

import sys
from os import path
import xbmcvfs, xbmc
from resources.lib import control
from resources.lib.tools import cParser

sysaddon = sys.argv[0]
syshandle = int(sys.argv[1]) if len(sys.argv) > 1 else ''
artPath = control.artPath()
addonFanart = control.addonFanart()
addonPath = control.addonPath

# TODO https://kodi.wiki/view/Default_Icons
class navigator:
	def root(self):
		self.addDirectoryItem("Suche", 'searchNavigator', 'search.png', 'DefaultAddonsSearch.png')
		self.addDirectoryItem("Filme", 'movieNavigator', 'movies.png', 'DefaultMovies.png')
		self.addDirectoryItem("TV-Serien", 'tvNavigator', 'tvshows.png', 'DefaultTVShows.png')

		# Show Trakt menus ALWAYS (show notification if not authenticated)
		self.addDirectoryItem("Meine Filme", 'myMoviesNavigator', 'movies.png', 'DefaultMovies.png')
		self.addDirectoryItem("Meine TV-Serien", 'myTVNavigator', 'tvshows.png', 'DefaultTVShows.png')
		self.addDirectoryItem("Meine Listen", 'myListsNavigator', 'genres.png', 'DefaultFolder.png')

		downloads = True if control.getSetting('downloads') == 'true' and (
				len(control.listDir(control.getSetting('download.movie.path'))[0]) > 0 or len(
			control.listDir(control.getSetting('download.tv.path'))[0]) > 0) else False
		if downloads:
			self.addDirectoryItem("Downloads", 'downloadNavigator', 'downloads.png', 'DefaultFolder.png')
		self.addDirectoryItem("Werkzeuge", 'toolNavigator', 'tools.png', 'DefaultAddonProgram.png')
		if xbmc.getCondVisibility('system.platform.windows'): self.addDirectoryItem("Stream-URL abspielen", 'playURL', 'url.png', 'DefaultAddonWebSkin.png', isFolder=False)
		self._endDirectory(content='',cache=False)  # addons  videos  files

# TODO vote_count vote_average popularity revenue
	def movies(self):
		self.addDirectoryItem("[B]Filme[/B] - Neu", 'listings&media_type=movie&url=kino', 'in-theaters.png', 'DefaultRecentlyAddedMovies.png')
		self.addDirectoryItem("[B]Filme[/B] - Jahr", 'movieYears', 'years.png', 'DefaultMovies.png')
		self.addDirectoryItem("[B]Filme[/B] - Genres", 'movieGenres', 'genres.png', 'DefaultMovies.png')
		self.addDirectoryItem("[B]Filme[/B] - Am populärsten", 'listings&media_type=movie&url=production_status=released%26sort_by=popularity.desc', 'most-popular.png', 'DefaultMovies.png')
		self.addDirectoryItem("[B]Filme[/B] - Am besten bewertet", 'listings&media_type=movie&url=production_status=released%26sort_by=vote_average.desc', 'highly-rated.png', 'DefaultMovies.png')
		self.addDirectoryItem("[B]Filme[/B] - Meist bewertet", 'listings&media_type=movie&url=production_status=released%26sort_by=vote_count.desc', 'most-voted.png', 'DefaultMovies.png')
		self.addDirectoryItem("[B]Filme[/B] - Bestes Einspielergebnis", 'listings&media_type=movie&url=production_status=released%26sort_by=revenue.desc', 'box-office.png', 'DefaultMovies.png')
		self.addDirectoryItem("[B]Filme[/B] - Personen", 'personSearch', '_people-search.png', 'DefaultActor.png')
		self._endDirectory()

	def tvshows(self):
		self.addDirectoryItem("[B]Serien[/B] - Genres", 'tvGenres', 'genres.png', 'DefaultTVShows.png')
		self.addDirectoryItem("[B]Serien[/B] - Am populärsten", 'listings&media_type=tv&url=sort_by=popularity.desc', 'most-popular.png', 'DefaultTVShows.png')
		self.addDirectoryItem("[B]Serien[/B] - Am besten bewertet", 'listings&media_type=tv&url=sort_by=vote_average.desc', 'highly-rated.png', 'DefaultTVShows.png')
		self.addDirectoryItem("[B]Serien[/B] - Meist bewertet", 'listings&media_type=tv&url=sort_by=vote_count.desc', 'most-voted.png', 'DefaultTVShows.png')
		self.addDirectoryItem("[B]Serien[/B] - Personen", 'personSearch', '_people-search.png', 'DefaultActor.png')
		self._endDirectory()

	def tools(self):
		self.addDirectoryItem("[B]Trakt[/B]: Konto autorisieren", 'authTrakt', 'trakt.png', 'DefaultAddonProgram.png', isFolder=False)
		self.addDirectoryItem("[B]Support[/B]: Information anzeigen", 'pluginInfo', 'plugin-info.png', 'DefaultAddonProgram.png', isFolder=False)
		self.addDirectoryItem(control.addonName +": EINSTELLUNGEN", 'addonSettings', 'tools.png', 'DefaultAddonProgram.png', isFolder=False)
		# self.addDirectoryItem("[B]"+control.addonName.upper()+"[/B]: Reset Settings (außer Konten)", 'resetSettings', 'nightly_update.png', 'DefaultAddonProgram.png', isFolder=False)
		self.addDirectoryItem("[B]Resolver[/B]: EINSTELLUNGEN", 'resolverSettings', 'resolveurl.png', 'DefaultAddonProgram.png', isFolder=False)
		self._endDirectory()	# addons  videos  files

	def downloads(self):
		movie_downloads = control.getSetting('download.movie.path')
		tv_downloads = control.getSetting('download.tv.path')
		if len(control.listDir(movie_downloads)[0]) > 0:
			self.addDirectoryItem("Filme", movie_downloads, 'movies.png', 'DefaultMovies.png', isAction=False)
		if len(control.listDir(tv_downloads)[0]) > 0:
			self.addDirectoryItem("TV-Serien", tv_downloads, 'tvshows.png', 'DefaultTVShows.png', isAction=False)
		self._endDirectory()

	def search(self):
		self.addDirectoryItem("Filme", 'searchNew&table=movies', '_movies-search.png', 'DefaultMovies.png', isFolder=False)
		self.addDirectoryItem("TV-Serien", 'searchNew&table=tvshows', '_series-search.png', 'DefaultTVShows.png', isFolder=False)
		self.addDirectoryItem("Darsteller/Crew (Filme)", 'personSearch&media_type=movie', '_people-search.png', 'DefaultMovies.png', isFolder=False)
		self.addDirectoryItem("Darsteller/Crew (TV-Serien)", 'personSearch&media_type=tv', '_people-search.png', 'DefaultTVShows.png', isFolder=False)
		self._endDirectory()

	def myMovies(self, lite=False):
		"""Meine Filme - 1:1 Umbrella Implementation (Lines 155-183)"""
		from resources.lib.modules import trakt

		# Umbrella Line 156: accountCheck
		if not trakt.getTraktCredentialsInfo():
			control.infoDialog('Bitte verbinde dich mit Trakt um diese Funktion zu nutzen', heading='Trakt', sound=True, icon='INFO')
			self.addDirectoryItem("[COLOR skyblue][B]Trakt Konto verbinden[/B][/COLOR]", 'authTrakt', 'trakt.png', 'DefaultAddonProgram.png', isFolder=False)
			self._endDirectory()
			return

		# Umbrella Lines 169-175: TRAKT Section
		traktCredentials = trakt.getTraktCredentialsInfo()
		traktIndicators = trakt.getTraktIndicatorsInfo()

		if traktCredentials:
			if traktIndicators:
				# Umbrella Line 171: Unfinished Movies (NO underscore: traktunfinished!)
				self.addDirectoryItem('Angefangene Filme', 'moviesUnfinished&url=traktunfinished', 'movies.png', 'DefaultInProgressShows.png', queue=True)
				# Umbrella Line 172: History (NO underscore: trakthistory!)
				self.addDirectoryItem('Verlauf', 'moviesHistory&url=trakthistory', 'movies.png', 'DefaultMovies.png', queue=True)

			# Umbrella Line 173: Watchlist (NO underscore: traktwatchlist!)
			self.addDirectoryItem('Watchlist', 'movies&url=traktwatchlist', 'movies.png', 'DefaultMovies.png', queue=False)
			# Umbrella Line 174: Collection (NO underscore: traktcollection!)
			self.addDirectoryItem('Collection', 'movies&url=traktcollection', 'movies.png', 'DefaultMovies.png', queue=False)
			# Umbrella Line 175: Liked Lists
			self.addDirectoryItem('Gelikte Listen', 'movies_LikedLists', 'movies.png', 'DefaultMovies.png', queue=True)

		# Umbrella Line 177: Normal movie navigation (ONLY "Filme" - redundant items removed!)
		if not lite:
			self.addDirectoryItem('Entdecken', 'movieNavigator', 'movies.png', 'DefaultMovies.png')

		self._endDirectory()

	def myTV(self, lite=False):
		"""Meine TV-Serien - 1:1 Umbrella Implementation (Lines 255-296)"""
		from resources.lib.modules import trakt

		# Umbrella Line 256: accountCheck
		if not trakt.getTraktCredentialsInfo():
			control.infoDialog('Bitte verbinde dich mit Trakt um diese Funktion zu nutzen', heading='Trakt', sound=True, icon='INFO')
			self.addDirectoryItem("[COLOR skyblue][B]Trakt Konto verbinden[/B][/COLOR]", 'authTrakt', 'trakt.png', 'DefaultAddonProgram.png', isFolder=False)
			self._endDirectory()
			return

		# Umbrella Lines 275-290: TRAKT Section
		traktCredentials = trakt.getTraktCredentialsInfo()
		traktIndicators = trakt.getTraktIndicatorsInfo()

		if traktCredentials:
			if traktIndicators:
				# Umbrella Line 277: (35308 = "Finish Watching" → "Anschauen beenden")
				self.addDirectoryItem('Angefangene Episoden', 'episodesUnfinished&url=traktunfinished', 'tvshows.png', 'DefaultInProgressShows.png', queue=True)
				# Umbrella Line 278: (32037 = "Progress" → "Progress Episodes")
				self.addDirectoryItem('Nächste Episoden', 'calendar&url=progress', 'tvshows.png', 'DefaultRecentlyAddedEpisodes.png', queue=True)
				# Umbrella Line 279: (40401 = "Progress Shows")
				self.addDirectoryItem('Serien-Fortschritt', 'shows_progress&url=progresstv', 'tvshows.png', 'DefaultTVShows.png', queue=True)
				# Umbrella Line 280: (40433 = "Watched Shows")
				self.addDirectoryItem('Gesehene Serien', 'shows_watched&url=watchedtv', 'tvshows.png', 'DefaultTVShows.png', queue=True)
				# Umbrella Line 281: (32019 = "Upcoming Progress" → "Kommende Fortschritte")
				self.addDirectoryItem('Noch nicht ausgestrahlt', 'upcomingProgress&url=progress', 'tvshows.png', 'DefaultTVShows.png', queue=True)
				# Umbrella Line 282: (32202 = "Recent Episodes" → "Aktuelle Folgen")
				self.addDirectoryItem('Kürzlich ausgestrahlt', 'calendar&url=mycalendarRecent', 'tvshows.png', 'DefaultRecentlyAddedEpisodes.png', queue=True)
				# Umbrella Line 283: (32203 = "Upcoming Episodes" → "Kommende Folgen")
				self.addDirectoryItem('Demnächst im TV', 'calendar&url=mycalendarUpcoming', 'tvshows.png', 'DefaultRecentlyAddedEpisodes.png', queue=True)
				# Umbrella Line 284: (32204 = "Season Premieres" → "Saisonpremieren")
				self.addDirectoryItem('Staffel-Premieren', 'calendar&url=mycalendarPremiers', 'tvshows.png', 'DefaultTVShows.png', queue=True)
				# Umbrella Line 285: (32036 = "History" → "Verlauf")
				self.addDirectoryItem('Verlauf', 'calendar&url=trakthistory', 'tvshows.png', 'DefaultTVShows.png', queue=True)

			# Umbrella Line 288: (32683 = "Trakt Watchlist" → "Trakt-Watchlist")
			self.addDirectoryItem('Watchlist', 'tvshows&url=traktwatchlist', 'tvshows.png', 'DefaultTVShows.png', queue=False)
			# Umbrella Line 289: (32032 = "Collection" → "Sammlung")
			self.addDirectoryItem('Collection', 'tvshows&url=traktcollection', 'tvshows.png', 'DefaultTVShows.png', queue=False)
			# Umbrella Line 290: "My Liked Lists" → "Gelikte Listen"
			self.addDirectoryItem('Gelikte Listen', 'shows_LikedLists', 'tvshows.png', 'DefaultTVShows.png', queue=True)

		# Umbrella Line 293: "Discover" → "Entdecken" (only this one!)
		if not lite:
			self.addDirectoryItem('Entdecken', 'tvNavigator', 'tvshows.png', 'DefaultTVShows.png')

		self._endDirectory()

	def myLists(self):
		"""Meine Listen - Trakt Integration"""
		from resources.lib.modules import trakt

		# Check if user is authenticated
		if not trakt.getTraktCredentialsInfo():
			# Show notification and offer to authenticate
			control.infoDialog('Bitte verbinde dich mit Trakt um diese Funktion zu nutzen', heading='Trakt', sound=True, icon='INFO')
			# Add button to authenticate
			self.addDirectoryItem("[COLOR skyblue][B]Trakt Konto verbinden[/B][/COLOR]", 'authTrakt', 'trakt.png', 'DefaultAddonProgram.png', isFolder=False)
			self._endDirectory()
			return

		# Get user's lists from Trakt
		lists = trakt.lists()

		if not lists:
			control.infoDialog('Keine Listen gefunden', time=2000)
			self._endDirectory()
			return

		# Display each list with both Movies and TV Shows as separate items
		for list_item in lists:
			try:
				name = list_item.get('name', 'Unbekannte Liste')
				list_id = list_item['ids']['slug']
				item_count = list_item.get('item_count', 0)

				# Add Movies entry for this list
				label_movies = '[Filme] %s' % name
				self.addDirectoryItem(label_movies, 'movies&url=trakt_userlist&list_id=%s' % list_id, 'trakt.png', 'DefaultMovies.png')

				# Add TV Shows entry for this list
				label_tv = '[Serien] %s' % name
				self.addDirectoryItem(label_tv, 'tvshows&url=trakt_userlist&list_id=%s' % list_id, 'trakt.png', 'DefaultTVShows.png')
			except:
				pass

		self._endDirectory()

	def traktUserlist(self, list_id):
		"""Display mixed content from a Trakt list (movies + shows)"""
		try:
			from resources.lib.modules import trakt

			if not trakt.getTraktCredentialsInfo():
				control.infoDialog('Trakt Konto erforderlich', sound=True, icon='INFO')
				self._endDirectory()
				return

			username = control.getSetting('trakt.user.name')

			# Get ALL items from list (mixed - no type filter)
			items = trakt.getTraktAsJson('/users/%s/lists/%s/items' % (username, list_id))

			if not items:
				control.infoDialog('Liste ist leer', time=2000)
				self._endDirectory()
				return

			# Group by type and create category folders
			movie_count = 0
			show_count = 0

			for item in items:
				item_type = item.get('type')
				if item_type == 'movie':
					movie_count += 1
				elif item_type == 'show':
					show_count += 1

			# Add Movies folder if there are movies
			if movie_count > 0:
				self.addDirectoryItem(
					'[Filme] (%d)' % movie_count,
					'movies&url=trakt_userlist&list_id=%s' % list_id,
					'trakt.png',
					'DefaultMovies.png'
				)

			# Add Shows folder if there are shows
			if show_count > 0:
				self.addDirectoryItem(
					'[Serien] (%d)' % show_count,
					'tvshows&url=trakt_userlist&list_id=%s' % list_id,
					'trakt.png',
					'DefaultTVShows.png'
				)

			self._endDirectory()

		except Exception as e:
			import xbmc
			xbmc.log('[Eternity-Trakt] TraktUserlist Error: %s' % str(e), xbmc.LOGERROR)
			self._endDirectory()

#TODO
	def addDirectoryItem(self, name, query, thumb, icon, context=None, queue=False, isAction=True, isFolder=True):
		url = '%s?action=%s' % (sysaddon, query) if isAction == True else query
		thumb = self.getMedia(thumb, icon)
		#laut kodi doku - ListItem([label, label2, path, offscreen])
		listitem = control.item(name, offscreen=True) # Removed iconImage and thumbnailImage
		# Set both thumb (small icon) and icon (fallback) to the same value for consistency
		listitem.setArt({'poster': thumb, 'icon': icon})
		if not context == None:
			cm = []
			cm.append((context[0], 'RunPlugin(%s?action=%s)' % (sysaddon, context[1])))
			listitem.addContextMenuItems(cm)

		isMatch, sPlot = cParser.parseSingleResult(query, "plot'.*?'([^']+)")
		if not isMatch: sPlot = '[COLOR blue]{0}[/COLOR]'.format(name)
		if isFolder:
			listitem.setInfo('video', {'overlay': 4, 'plot': control.unquote_plus(sPlot)})
			listitem.setIsFolder(True)
		else:
			listitem.setProperty('IsPlayable', 'false')
		self.addFanart(listitem, query)
		control.addItem(syshandle, url, listitem, isFolder)

	def _endDirectory(self, content='', cache=True ): # addons  videos  files
		# https://romanvm.github.io/Kodistubs/_autosummary/xbmcplugin.html#xbmcplugin.setContent
		control.content(syshandle, content)
		control.plugincategory(syshandle, control.addonName + ' / '+ control.addonVersion)
		control.endofdirectory(syshandle, succeeded=True, cacheToDisc=cache)

# ------- ergänzt für xStream V2 -----------
	def addFanart(self, listitem, query):
		if control.getSetting('fanart')=='true':
			isMatch, sFanart = cParser.parseSingleResult(query, "fanart'.*?'([^']+)")
			if isMatch:
				sFanart = self.getMedia(sFanart)
				listitem.setProperty('fanart_image', sFanart)
			else:
				listitem.setProperty('fanart_image', addonFanart)

	def getMedia(self,mediaFile=None, icon=None):
		if xbmcvfs.exists(path.join(artPath, mediaFile)): mediaFile = path.join(artPath, mediaFile)
		elif xbmcvfs.exists(path.join(artPath, 'sites', mediaFile)): mediaFile = path.join(artPath, 'sites', mediaFile)
		elif mediaFile.startswith('http'): return mediaFile
		else: mediaFile = icon
		return mediaFile
	


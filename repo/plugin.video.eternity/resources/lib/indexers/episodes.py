

#2021-07-15
# edit 2025-08-02 switch from treads to concurrent.futures 

import sys, re
import datetime, json, time
from resources.lib import control, playcountDB
from resources.lib.tmdb_old import cTMDB
from concurrent.futures import ThreadPoolExecutor
from resources.lib.control import getKodiVersion
if int(getKodiVersion()) >= 20: from infotagger.listitem import ListItemInfoTag

_params = dict(control.parse_qsl(sys.argv[2].replace('?',''))) if len(sys.argv) > 1 else dict()

class episodes:
	def __init__(self):
		self.list = []
		self.lang = "de"
		self.datetime = (datetime.datetime.utcnow() - datetime.timedelta(hours=5))
		self.systime = (self.datetime).strftime('%Y%m%d%H%M%S%f')
		# sysmeta is optional - only needed for regular episode listings
		self.sysmeta = _params.get('sysmeta', '')

		self.ePosition = 0

	def get(self, params):
		try:
			data = json.loads(params['sysmeta'])
			self.title = data['title']
			#number_of_episodes = data['number_of_episodes']

			if not 'number_of_episodes' in data or not data['number_of_episodes']: return
			#tmdb_id = data['tmdb_id']
			#tvdb_id = data['tvdb_id'] if 'tvdb_id' in data else None
			season = data['season']
			episodes = data['episodes']
			playcount = playcountDB.getPlaycount('season', 'title', self.title, season, None)
			if playcount is None:
				#playcountDB.createEntry('season', self.title, self.title + ' S%02d' % season, None, None, season, number_of_episodes, None)
				playcount = 0
			self.sysmeta = re.sub('"playcount": \d', '"playcount": %s' % playcount, self.sysmeta)

			for i in episodes:
				self.list.append(i)

			# for i in range(1, number_of_episodes+1):
			#	 self.list.append({'tmdb_id': tmdb_id, 'tvdb_id': tvdb_id, 'season': season, 'episode': i})
			self.worker()
			self.Directory(self.list)
			return  self.list
		except:
			return


	def worker(self):
		try:
			self.meta = []
			#much faster
			with ThreadPoolExecutor() as executor:
				executor.map(self.super_meta, self.list)

			self.meta = sorted(self.meta, key=lambda k: k['episode'])
			self.list = [i for i in self.meta] # falls noch eine Filterfunktion kommt
			# self.list = [i for i in self.list if not i['plot'].strip() == '' and not i['poster'] == control.addonPoster()]  # - Filter
		except:
			return


	def super_meta(self, i):
		try:
			#meta = cTMDB().get_meta_episode('episode', '', self.list[i]['tmdb_id'] , self.list[i]['season'], self.list[i]['episode'], advanced='true')
			meta = cTMDB()._format_episodes(i, self.title)
			try:
				playcount = playcountDB.getPlaycount('episode', 'title', self.title, meta['season'], meta['episode']) # mediatype, column_names, column_value, season=0, episode=0
				playcount = playcount if playcount else 0
				overlay = 7 if playcount > 0 else 6
				meta.update({'playcount': playcount, 'overlay': overlay})
			except:
				pass
			self.meta.append(meta)
		except:
			pass


	def Directory(self, items):
		# if xbmc.getInfoLabel("Container.Viewmode") != 55: xbmc.executebuiltin( "Container.SetViewMode(%i)" % 55 )
		if items == None or len(items) == 0:
			control.idle()
			sys.exit()

		sysaddon = sys.argv[0]
		syshandle = int(sys.argv[1])

		addonPoster, addonBanner = control.addonPoster(), control.addonBanner()
		addonFanart, settingFanart = control.addonFanart(), control.getSetting('fanart')

		watchedMenu = "In %s [I]Gesehen[/I]" % control.addonName
		unwatchedMenu = "In %s [I]Ungesehen[/I]" % control.addonName
		traktManagerMenu = "[B]Trakt-Manager[/B]"

		# Check if Trakt is authenticated
		from resources.lib.modules import trakt
		traktCredentials = trakt.getTraktCredentialsInfo()
		pos = 0
		for i in items:
			try:
				meta = json.loads(self.sysmeta)
				meta.pop('episodes', None)
				sysmeta = json.loads(self.sysmeta)
				sysmeta.pop('episodes', None)
				season = i['season']
				episode = i['episode']

				systitle = sysmeta['title']
				sysname = systitle + ' S%02dE%02d' % (season, episode)
				sysmeta.update({'episode': episode})
				sysmeta.update({'sysname': sysname})

				_sysmeta = control.quote_plus(json.dumps(sysmeta))

				if 'title' in i and i['title']: label = '%sx%02d  %s' % (season, episode, i['title'])
				else: label = '%sx%02d  Episode %s' % (season, episode,  episode)
				if datetime.datetime(*(time.strptime(i['premiered'], "%Y-%m-%d")[0:6])) > datetime.datetime.now():
					label = '[COLOR=red][I]{}[/I][/COLOR]'.format(label)  # ffcc0000

				poster = i['poster'] if 'poster' in i and 'http' in i['poster'] else sysmeta['poster']
				fanart = sysmeta['fanart'] if 'fanart' in sysmeta else addonFanart
				plot = ''
				if 'plot' in i and len(i['plot']) > 50:
					plot = i['plot']
					sysmeta.update({'plot': plot})

				#plot = i['plot'] if 'plot' in i and len(i['plot']) > 50 else ''  #sysmeta['plot']
				plot = '[COLOR blue]%s%sStaffel: %s   Episode: %s[/COLOR]%s%s' % (meta['title'], "\n",i['season'], i['episode'], "\n\n", plot)

				meta.update({'poster': poster})
				meta.update({'fanart': fanart})
				meta.update({'plot': plot})
				if 'premiered' in i and i['premiered']: meta.update({'premiered': i['premiered']})

				item = control.item(label=label, offscreen=True)
				item.setArt({'poster': poster, 'banner': addonBanner})
				if settingFanart == 'true': item.setProperty('Fanart_Image', fanart)

				cm = []
				try:
					playcount = i['playcount'] if sysmeta['playcount'] == 0 else 1
					if playcount == 1:
						cm.append((unwatchedMenu, 'RunPlugin(%s?action=UpdatePlayCount&meta=%s&playCount=0)' % (sysaddon, _sysmeta)))
						meta.update({'playcount': 1, 'overlay': 7})
						sysmeta.update({'playcount': 1, 'overlay': 7})
						pos = episode + 1
						if len(items) == episode: pos = episode
					else:
						cm.append((watchedMenu, 'RunPlugin(%s?action=UpdatePlayCount&meta=%s&playCount=1)' % (sysaddon, _sysmeta)))
						meta.update({'playcount': 0, 'overlay': 6})
						sysmeta.update({'playcount': 0, 'overlay': 6})
				except:
					pass

				# Add Trakt Manager if user is authenticated
				if traktCredentials:
					try:
						# Get IDs for Trakt
						imdb_id = sysmeta.get('imdb', '') or sysmeta.get('imdb_id', '')
						tvdb_id = sysmeta.get('tvdb', '') or sysmeta.get('tvdb_id', '')
						season_num = sysmeta.get('season', '')
						episode_num = sysmeta.get('episode', '')
						tvshowtitle = sysmeta.get('title', '')

						# Normalize IMDB ID
						if imdb_id and not imdb_id.startswith('tt'):
							imdb_id = 'tt' + imdb_id

						# Determine watched status
						watched = (playcount == 1)

						# Determine unfinished status (if progress exists and < 90%)
						unfinished = False
						try:
							if 'progress' in i and i['progress']:
								progress = float(i['progress'])
								unfinished = (progress > 0 and progress < 90)
						except:
							pass

						if tvdb_id and season_num and episode_num:
							cm.append((traktManagerMenu, 'RunPlugin(%s?action=traktManager&name=%s&imdb=%s&tvdb=%s&season=%s&episode=%s&watched=%s&unfinished=%s)' % (
								sysaddon,
								control.quote_plus(tvshowtitle.encode('utf-8')),
								imdb_id,
								tvdb_id,
								season_num,
								episode_num,
								watched,
								unfinished
							)))
					except:
						pass

				cm.append(('Einstellungen', 'RunPlugin(%s?action=addonSettings)' % sysaddon))
				item.addContextMenuItems(cm)

				sysmeta = control.quote_plus(json.dumps(sysmeta))
				url = '%s?action=play&sysmeta=%s' % (sysaddon, sysmeta)

				aActors = []
				if 'cast' in meta and meta['cast']: aActors = meta['cast']

				# # # remove unsupported InfoLabels
				meta.pop('cast', None)
				meta.pop('fanart', None)
				meta.pop('poster', None)
				meta.pop('imdb_id', None)
				meta.pop('tvdb_id', None)
				meta.pop('tmdb_id', None)
				meta.pop('number_of_seasons', None)
				meta.pop('number_of_episodes', None)
				meta.pop('originallanguage', None)
				meta.pop('sysname', None)
				meta.pop('systitle', None)
				meta.pop('year', None)
				meta.pop('aliases', None)
				meta.pop('backdrop_url', None)
				meta.pop('cover_url', None)

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
					stream_details = {
						'video': [video_streaminfo],
						'audio': [audio_streaminfo]}
					info_tag.set_stream_details(stream_details)
					info_tag.set_cast(aActors)

				control.addItem(handle=syshandle, url=url, listitem=item, isFolder=False)
			except:
				pass

		control.content(syshandle, 'movies')	# 'episodes' cpu last sehr hoch / movies
		if control.skin == 'skin.estuary':
			control.execute('Container.SetViewMode(%s)' % str(55))

		control.plugincategory(syshandle, control.addonVersion)
		control.endofdirectory(syshandle, cacheToDisc=True)
		control.sleep(200)

		# setzt Auswahl nach letzte als gesehen markierte Episode
		if control.getSetting('status.position')== 'true':
			from resources.lib.utils import setPosition
			setPosition(pos, __name__)

	def getTraktUnfinished(self):
		"""
		Phase 1.6: Display unfinished episodes from Trakt playback progress
		Shows episodes that were started but not finished (< 90%)
		WITH TRAKT MANAGER CONTEXT MENU
		"""
		try:
			from resources.lib.modules import trakt
			import xbmc
			import json

			sysaddon = sys.argv[0]
			syshandle = int(sys.argv[1])

			# Check if Trakt is authenticated
			traktCredentials = trakt.getTraktCredentialsInfo()
			if not traktCredentials:
				control.infoDialog('Bitte verbinde dich mit Trakt', time=2000)
				control.content(syshandle, 'files')
				control.endofdirectory(syshandle, cacheToDisc=False)
				return

			# Get unfinished episodes from Trakt
			items = trakt.getUnfinishedEpisodes()

			if not items:
				xbmc.log('[Eternity] No unfinished episodes found', xbmc.LOGINFO)
				control.infoDialog('Keine angefangenen Episoden gefunden', time=2000)
				control.content(syshandle, 'files')
				control.endofdirectory(syshandle, cacheToDisc=False)
				return

			addonPoster = control.addonPoster()
			watchedMenu = "In %s [I]Gesehen[/I]" % control.addonName
			unwatchedMenu = "In %s [I]Ungesehen[/I]" % control.addonName
			traktManagerMenu = "[B]Trakt-Manager[/B]"

			# Display each unfinished episode
			for item_data in items:
				try:
					# Extract episode data
					episode_data = item_data.get('episode', {})
					show_data = item_data.get('show', {})
					progress = item_data.get('progress', 0)

					show_title = show_data.get('title', 'Unknown Show')
					season = episode_data.get('season', 0)
					episode = episode_data.get('number', 0)
					episode_title = episode_data.get('title', 'Episode %d' % episode)
					tmdb_id = show_data.get('ids', {}).get('tmdb')

					if not tmdb_id or not season or not episode:
						continue

					# Format label with progress
					label = '%s - S%02dE%02d - %s [%d%%]' % (
						show_title, season, episode, episode_title, progress
					)

					# Build sysmeta for play action
					show_ids = show_data.get('ids', {})
					imdb_id = show_ids.get('imdb', '')
					tvdb_id = show_ids.get('tvdb', '')

					sysmeta = {
						'mediatype': 'tvshow',
						'title': show_title,
						'year': show_data.get('year', ''),
						'season': season,
						'episode': episode,
						'tmdb_id': tmdb_id,
						'imdb_id': imdb_id,
						'tvdb_id': tvdb_id,
						'plot': episode_data.get('overview', ''),
						'progress': progress
					}

					sysmeta_str = control.quote_plus(json.dumps(sysmeta))
					url = '%s?action=play&sysmeta=%s' % (sysaddon, sysmeta_str)

					# Create ListItem
					listitem = control.item(label=label, offscreen=True)
					listitem.setArt({'poster': addonPoster, 'icon': addonPoster})
					listitem.setProperty('IsPlayable', 'true')

					# Build Context Menu
					cm = []

					# Mark as watched/unwatched
					watched = (progress >= 90)
					if watched:
						cm.append((unwatchedMenu, 'RunPlugin(%s?action=UpdatePlayCount&meta=%s&playCount=0)' % (sysaddon, sysmeta_str)))
					else:
						cm.append((watchedMenu, 'RunPlugin(%s?action=UpdatePlayCount&meta=%s&playCount=1)' % (sysaddon, sysmeta_str)))

					# Trakt Manager
					if tvdb_id:
						# Normalize IMDB ID
						if imdb_id and not imdb_id.startswith('tt'):
							imdb_id = 'tt' + imdb_id

						cm.append((traktManagerMenu, 'RunPlugin(%s?action=traktManager&name=%s&imdb=%s&tvdb=%s&season=%s&episode=%s&watched=%s&unfinished=true)' % (
							sysaddon,
							control.quote_plus(show_title.encode('utf-8')),
							imdb_id,
							tvdb_id,
							season,
							episode,
							watched
						)))

					cm.append(('Einstellungen', 'RunPlugin(%s?action=addonSettings)' % sysaddon))
					listitem.addContextMenuItems(cm)

					# Set info
					meta_info = {
						'title': episode_title,
						'tvshowtitle': show_title,
						'season': season,
						'episode': episode,
						'plot': sysmeta.get('plot', ''),
						'mediatype': 'episode',
						'playcount': 1 if watched else 0
					}
					listitem.setInfo(type='Video', infoLabels=meta_info)

					control.addItem(handle=syshandle, url=url, listitem=listitem, isFolder=False)

				except Exception as e:
					xbmc.log('[Eternity] Error processing unfinished episode: %s' % str(e), xbmc.LOGERROR)
					pass

			# End directory
			control.content(syshandle, 'episodes')
			control.endofdirectory(syshandle, cacheToDisc=True)

		except Exception as e:
			import xbmc
			xbmc.log('[Eternity] getTraktUnfinished error: %s' % str(e), xbmc.LOGERROR)

	def getTraktProgress(self):
		"""
		Phase 1.7: Display next episodes to watch (with TMDB metadata)
		Shows calculated next episode per show with full metadata
		UMBRELLA EQUIVALENT - Shows directly playable episodes!
		WITH TRAKT MANAGER CONTEXT MENU
		"""
		try:
			from resources.lib.modules import trakt
			import xbmc
			import json

			sysaddon = sys.argv[0]
			syshandle = int(sys.argv[1])

			# Check if Trakt is authenticated
			traktCredentials = trakt.getTraktCredentialsInfo()
			if not traktCredentials:
				control.infoDialog('Bitte verbinde dich mit Trakt', time=2000)
				control.content(syshandle, 'files')
				control.endofdirectory(syshandle, cacheToDisc=False)
				return

			# Get progress watching (next episodes) from Trakt + TMDB
			items = trakt.getProgressWatching()

			if not items:
				xbmc.log('[Eternity] No progress items found', xbmc.LOGINFO)
				control.infoDialog('Keine Serien im Fortschritt gefunden', time=2000)
				control.content(syshandle, 'files')
				control.endofdirectory(syshandle, cacheToDisc=False)
				return

			addonPoster = control.addonPoster()
			watchedMenu = "In %s [I]Gesehen[/I]" % control.addonName
			unwatchedMenu = "In %s [I]Ungesehen[/I]" % control.addonName
			traktManagerMenu = "[B]Trakt-Manager[/B]"

			# Display each next episode
			for item_data in items:
				try:
					show_title = item_data.get('tvshowtitle', 'Unknown Show')
					season = item_data.get('season', 0)
					episode = item_data.get('episode', 0)
					episode_title = item_data.get('title', 'Episode %d' % episode)
					tmdb_id = item_data.get('tmdb')
					imdb_id = item_data.get('imdb', '')
					tvdb_id = item_data.get('tvdb', '')
					plot = item_data.get('plot', '')
					premiered = item_data.get('premiered', '')
					rating = item_data.get('rating', 0)
					unaired = item_data.get('unaired', '')

					if not tmdb_id or not season or not episode:
						continue

					# Format label
					if unaired:
						label = '%s - S%02dE%02d - %s [Noch nicht ausgestrahlt]' % (
							show_title, season, episode, episode_title
						)
					else:
						label = '%s - S%02dE%02d - %s' % (
							show_title, season, episode, episode_title
						)

					# Add premiere date if available
					if premiered:
						label += ' (%s)' % premiered

					# Build sysmeta for play action
					sysmeta = {
						'mediatype': 'tvshow',
						'title': show_title,
						'year': item_data.get('year', ''),
						'season': season,
						'episode': episode,
						'tmdb_id': tmdb_id,
						'imdb_id': imdb_id,
						'tvdb_id': tvdb_id,
						'plot': plot,
						'premiered': premiered
					}

					sysmeta_str = control.quote_plus(json.dumps(sysmeta))
					url = '%s?action=play&sysmeta=%s' % (sysaddon, sysmeta_str)

					# Create ListItem
					listitem = control.item(label=label, offscreen=True)
					listitem.setArt({'poster': addonPoster, 'icon': addonPoster})
					listitem.setProperty('IsPlayable', 'true')

					# Build Context Menu
					cm = []

					# Mark as watched/unwatched (next episodes are unwatched by default)
					watched = False
					cm.append((watchedMenu, 'RunPlugin(%s?action=UpdatePlayCount&meta=%s&playCount=1)' % (sysaddon, sysmeta_str)))

					# Trakt Manager
					if tvdb_id:
						# Normalize IMDB ID
						if imdb_id and not imdb_id.startswith('tt'):
							imdb_id = 'tt' + imdb_id

						cm.append((traktManagerMenu, 'RunPlugin(%s?action=traktManager&name=%s&imdb=%s&tvdb=%s&season=%s&episode=%s&watched=%s&unfinished=false)' % (
							sysaddon,
							control.quote_plus(show_title.encode('utf-8')),
							imdb_id,
							tvdb_id,
							season,
							episode,
							watched
						)))

					cm.append(('Einstellungen', 'RunPlugin(%s?action=addonSettings)' % sysaddon))
					listitem.addContextMenuItems(cm)

					# Set info
					meta_info = {
						'title': episode_title,
						'tvshowtitle': show_title,
						'season': season,
						'episode': episode,
						'plot': plot,
						'premiered': premiered,
						'rating': rating,
						'mediatype': 'episode',
						'playcount': 0
					}
					listitem.setInfo(type='Video', infoLabels=meta_info)

					control.addItem(handle=syshandle, url=url, listitem=listitem, isFolder=False)

				except Exception as e:
					xbmc.log('[Eternity] Error processing progress episode: %s' % str(e), xbmc.LOGERROR)
					pass

			# End directory
			control.content(syshandle, 'episodes')
			control.endofdirectory(syshandle, cacheToDisc=True)

		except Exception as e:
			import xbmc
			xbmc.log('[Eternity] getTraktProgress error: %s' % str(e), xbmc.LOGERROR)


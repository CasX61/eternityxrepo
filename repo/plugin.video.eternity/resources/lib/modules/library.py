# -*- coding: utf-8 -*-
"""
    Eternity Add-on - Library Module

    Manages Kodi library integration:
    - Creates .strm files for movies and TV shows
    - Creates .nfo files for metadata
    - Batch imports from Trakt (Collection, Watchlist, Lists)
    - Duplicate checking via Kodi JSONRPC

    NOTE: NO library database cache - uses Kodi's native database
    NOTE: NO auto-update service - can be added later
"""

from datetime import datetime, timedelta
from json import loads as jsloads
import re
from urllib.parse import quote_plus
from resources.lib import control
from scrapers.modules import cleantitle
import xbmc


class lib_tools:
    """Helper functions for library operations"""

    @staticmethod
    def service():
        """
        Background service for library auto-update

        Checks for new episodes every X hours (configurable)
        NO database cache - reads .strm files directly
        """
        property_name = 'eternity_library_service'

        try:
            # Create library folders
            lib_tools.create_folder(control.joinPath(control.transPath(control.getSetting('library.movie')), ''))
            lib_tools.create_folder(control.joinPath(control.transPath(control.getSetting('library.tv')), ''))
        except:
            pass

        # Get last run time from Kodi property (NOT database!)
        try:
            last_service = control.homeWindow.getProperty(property_name)
            if not last_service:
                last_service = "1970-01-01 23:59:00.000000"
                control.homeWindow.setProperty(property_name, last_service)
        except:
            import traceback
            xbmc.log('[Eternity Library Service] Failed to get last run: %s' % traceback.format_exc(), xbmc.LOGERROR)
            return

        # Main service loop
        while not control.monitor.abortRequested():
            try:
                # Check if service is enabled
                service_enabled = control.getSetting('library.service.update') == 'true'
                if not service_enabled:
                    if control.monitor.waitForAbort(60):
                        break
                    continue

                # Get update interval (hours)
                try:
                    update_hours = float(control.getSetting('library.service.hours'))
                except:
                    update_hours = 6  # Default: 6 hours

                # Check if enough time has passed
                last_service = control.homeWindow.getProperty(property_name)
                if last_service:
                    try:
                        t2 = datetime.strptime(last_service, '%Y-%m-%d %H:%M:%S.%f')
                        t3 = datetime.now()
                        check = abs(t3 - t2) >= timedelta(hours=update_hours)
                    except:
                        check = True  # Parse error, force update
                else:
                    check = True

                if not check:
                    # Not time yet, wait 10 seconds
                    if control.monitor.waitForAbort(10):
                        break
                    continue

                # Don't update while playing or scanning
                if control.player.isPlaying() or control.condVisibility('Library.IsScanningVideo'):
                    if control.monitor.waitForAbort(60):
                        break
                    continue

                # Update timestamp
                last_service = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
                control.homeWindow.setProperty(property_name, last_service)

                xbmc.log('[Eternity Library Service] Starting library update', xbmc.LOGINFO)

                # Update episodes (new episodes for existing shows)
                libepisodes().update()

                xbmc.log('[Eternity Library Service] Update completed', xbmc.LOGINFO)

                # Wait 15 minutes before next check
                if control.monitor.waitForAbort(60*15):
                    break

            except:
                import traceback
                xbmc.log('[Eternity Library Service] Error: %s' % traceback.format_exc(), xbmc.LOGERROR)
                if control.monitor.waitForAbort(60):
                    break

    @staticmethod
    def create_folder(folder):
        """Create folder (including parent directories)"""
        try:
            control.makeFile(folder)
        except:
            import traceback
            xbmc.log('[Eternity Library] Failed to create folder: %s\n%s' % (folder, traceback.format_exc()), xbmc.LOGERROR)

    @staticmethod
    def write_file(path, content):
        """Write content to file"""
        try:
            if not isinstance(content, str):
                content = str(content)
            file = control.openFile(path, 'w')
            file.write(str(content))
            file.close()
        except:
            import traceback
            xbmc.log('[Eternity Library] Failed to write file: %s\n%s' % (path, traceback.format_exc()), xbmc.LOGERROR)

    @staticmethod
    def nfo_url(media_string, ids):
        """Generate NFO URL for Kodi scrapers"""
        tvdb_url = 'https://thetvdb.com/?tab=series&id=%s'
        imdb_url = 'https://www.imdb.com/title/%s/'
        tmdb_url = 'https://www.themoviedb.org/%s/%s'

        if 'tvdb' in ids:
            return tvdb_url % (str(ids['tvdb']))
        elif 'imdb' in ids:
            return imdb_url % (str(ids['imdb']))
        elif 'tmdb' in ids:
            return tmdb_url % (media_string, str(ids['tmdb']))
        else:
            return ''

    @staticmethod
    def legal_filename(filename):
        """Make filename legal for all OS"""
        try:
            filename = filename.strip().replace("'", '').replace('&', 'and')
            filename = re.sub(r'[^\w\-_\. ]', '_', filename)
            filename = re.sub(r'\.+', '.', filename)
            filename = re.sub(re.compile(r'(CON|PRN|AUX|NUL|COM\d|LPT\d)\.', re.I), '\\1_', filename)
            filename = filename.lstrip('.')
            return filename
        except:
            return filename

    @staticmethod
    def make_path(base_path, title, year='', season=''):
        """Create folder path: base_path/Title (Year)/Season X"""
        try:
            foldername = title.strip().replace("'", '').replace('&', 'and')
            foldername = re.sub(r'[^\w\-_\. ]', '_', foldername)
            foldername = '%s (%s)' % (foldername, year) if year else foldername
            path = control.joinPath(base_path, foldername)
            if season:
                path = control.joinPath(path, 'Season %s' % season)
            return path
        except:
            import traceback
            xbmc.log('[Eternity Library] Failed to make path: %s' % traceback.format_exc(), xbmc.LOGERROR)
            return base_path

    @staticmethod
    def clean():
        """Clean Kodi library"""
        control.execute('CleanLibrary(video)')

    @staticmethod
    def update():
        """Update Kodi library"""
        control.execute('UpdateLibrary(video)')


class libmovies:
    """Movie library manager"""

    def __init__(self):
        self.library_folder = control.joinPath(control.transPath(control.getSetting('library.movie')), '')
        self.library_update = control.getSetting('library.update') == 'true'
        self.dupe_chk = control.getSetting('library.check') == 'true'

    def add(self, name, title, year, imdb, tmdb, range=False):
        """
        Add single movie to library

        Args:
            name: Display name (e.g. "Matrix (1999)")
            title: Movie title
            year: Release year
            imdb: IMDb ID
            tmdb: TMDb ID
            range: If True, return files_added count (for batch operations)

        Returns:
            int: Number of files added (if range=True)
        """
        try:
            if (control.getSetting('library.notifications') == 'true') and not range:
                control.infoDialog('%s' % name, heading='Adding to Library')

            # Duplicate check via Kodi JSONRPC
            try:
                if not self.dupe_chk:
                    raise Exception('Dupe check disabled')

                id = [imdb, tmdb] if tmdb else [imdb]
                lib = control.jsonrpc('{"jsonrpc": "2.0", "method": "VideoLibrary.GetMovies", "params": {"filter":{"or": [{"field": "year", "operator": "is", "value": "%s"}, {"field": "year", "operator": "is", "value": "%s"}, {"field": "year", "operator": "is", "value": "%s"}]}, "properties" : ["imdbnumber", "title", "originaltitle", "year"]}, "id": 1}' % (year, str(int(year)+1), str(int(year)-1)))
                lib = jsloads(lib)['result']['movies']
                lib = [i for i in lib if str(i['imdbnumber']) in id or (cleantitle.get(title) in (cleantitle.get(i['title']), cleantitle.get(i['originaltitle'])) and str(i['year']) == year)]
            except:
                lib = []

            files_added = 0
            try:
                if lib != []:
                    xbmc.log('[Eternity Library] Movie already in library: %s' % name, xbmc.LOGINFO)
                    raise Exception('Already in library')

                self.strmFile({'name': name, 'title': title, 'year': year, 'imdb': imdb, 'tmdb': tmdb})
                files_added += 1
                xbmc.log('[Eternity Library] Added movie: %s' % name, xbmc.LOGINFO)
            except:
                pass

            if files_added == 0 and (control.getSetting('library.notifications') == 'true') and not range:
                control.infoDialog('Already in library', heading=name)

            if range:
                return files_added

            # Single add - update library immediately
            if self.library_update and not control.condVisibility('Library.IsScanningVideo') and files_added > 0:
                if (control.getSetting('library.notifications') == 'true'):
                    control.infoDialog('Added to library', heading=name)
                control.sleep(10000)
                control.execute('UpdateLibrary(video)')

        except:
            import traceback
            xbmc.log('[Eternity Library] Failed to add movie: %s\n%s' % (name, traceback.format_exc()), xbmc.LOGERROR)
            if not range:
                control.infoDialog('Failed to add', heading=name)

    def strmFile(self, i):
        """Create .strm and .nfo files for movie"""
        try:
            # Extract data
            title = i.get('title', '')
            year = i.get('year', '')
            imdb = i.get('imdb', '')
            tmdb = i.get('tmdb', '')

            # DEBUG LOG
            xbmc.log('[Eternity Library] strmFile input: title=%s, year=%s, imdb=%s, tmdb=%s' % (title, year, imdb, tmdb), xbmc.LOGINFO)

            if not title:
                xbmc.log('[Eternity Library] ERROR: Title is empty!', xbmc.LOGERROR)
                return

            # URL encode title for plugin URL
            systitle = quote_plus(title)

            # Make filename legal (remove illegal chars)
            transtitle = title.translate(title.maketrans('', '', '\/:*?"<>|'))

            # .strm content points to Eternity play action
            content = 'plugin://plugin.video.eternity/?action=play_Item&title=%s&year=%s&imdb=%s&tmdb=%s' % (systitle, year, imdb, tmdb)

            # Create folder: Movies/Title (Year)/
            folder = lib_tools.make_path(self.library_folder, transtitle, year)
            xbmc.log('[Eternity Library] Creating folder: %s' % folder, xbmc.LOGINFO)
            lib_tools.create_folder(folder)

            # Write .strm file
            strm_path = control.joinPath(folder, lib_tools.legal_filename(transtitle) + '.' + year + '.strm')
            xbmc.log('[Eternity Library] Writing strm: %s' % strm_path, xbmc.LOGINFO)
            lib_tools.write_file(strm_path, content)

            # Write .nfo file (for Kodi scrapers)
            nfo_path = control.joinPath(folder, lib_tools.legal_filename(transtitle) + '.' + year + '.nfo')
            xbmc.log('[Eternity Library] Writing nfo: %s' % nfo_path, xbmc.LOGINFO)
            lib_tools.write_file(nfo_path, lib_tools.nfo_url('movie', i))

            xbmc.log('[Eternity Library] SUCCESS: Created strm for: %s' % title, xbmc.LOGINFO)

        except Exception as e:
            import traceback
            xbmc.log('[Eternity Library] EXCEPTION in strmFile: %s' % str(e), xbmc.LOGERROR)
            xbmc.log('[Eternity Library] Full traceback: %s' % traceback.format_exc(), xbmc.LOGERROR)

    def range(self, url, list_name):
        """
        Batch import movies from URL (Trakt Collection, Watchlist, etc.)

        Args:
            url: Trakt API URL
            list_name: Name for notifications (e.g. "Trakt Collection")
        """
        try:
            if (control.getSetting('library.notifications') == 'true'):
                control.infoDialog('Starting import from %s' % list_name, heading='Library Import')

            items = []

            # Fetch items from Trakt
            if 'trakt' in url:
                from resources.lib.indexers import movies
                items = movies.Movies().trakt_list(url, control.getSetting('trakt.user.name').strip())

            if not items:
                if (control.getSetting('library.notifications') == 'true'):
                    control.infoDialog('No items found', heading=list_name)
                return

            total_added = 0
            numitems = len(items)

            # Confirmation dialog
            if not control.yesnoDialog('Import %d movies from %s?' % (numitems, list_name), '', ''):
                return

            control.infoDialog('Importing %d movies...' % numitems, heading=list_name)

            for i in items:
                if control.monitor.abortRequested():
                    break

                try:
                    files_added = self.add('%s (%s)' % (i['title'], i['year']), i['title'], i['year'], i['imdb'], i['tmdb'], range=True)
                    if files_added > 0:
                        total_added += 1
                except:
                    import traceback
                    xbmc.log('[Eternity Library] Failed to add: %s\n%s' % (i['title'], traceback.format_exc()), xbmc.LOGERROR)

            # Update library after batch
            if self.library_update and not control.condVisibility('Library.IsScanningVideo') and total_added > 0:
                control.sleep(10000)
                control.execute('UpdateLibrary(video)')
                if (control.getSetting('library.notifications') == 'true'):
                    control.infoDialog('Imported %d of %d movies' % (total_added, numitems), heading=list_name)
            elif total_added == 0:
                if (control.getSetting('library.notifications') == 'true'):
                    control.infoDialog('All movies already in library', heading=list_name)

        except:
            import traceback
            xbmc.log('[Eternity Library] Range import failed: %s' % traceback.format_exc(), xbmc.LOGERROR)
            if (control.getSetting('library.notifications') == 'true'):
                control.infoDialog('Import failed', heading=list_name)


class libtvshows:
    """TV Show library manager"""

    def __init__(self):
        self.library_folder = control.joinPath(control.transPath(control.getSetting('library.tv')), '')
        self.library_update = control.getSetting('library.update') == 'true'
        self.dupe_chk = control.getSetting('library.check') == 'true'
        self.date_time = datetime.utcnow()
        self.date = self.date_time.strftime('%Y%m%d')

    def add(self, tvshowtitle, year, imdb, tmdb, tvdb, range=False):
        """
        Add TV show to library (all seasons/episodes)

        Args:
            tvshowtitle: Show title
            year: First aired year
            imdb: IMDb ID
            tmdb: TMDb ID
            tvdb: TVDb ID
            range: If True, return files_added count

        Returns:
            int: Number of files added (if range=True)
        """
        try:
            if (control.getSetting('library.notifications') == 'true') and not range:
                control.infoDialog('%s (%s)' % (tvshowtitle, year), heading='Adding to Library')

            # Duplicate check via Kodi JSONRPC
            try:
                if not self.dupe_chk:
                    raise Exception('Dupe check disabled')

                lib = control.jsonrpc('{"jsonrpc": "2.0", "method": "VideoLibrary.GetTVShows", "params": {"filter":{"or": [{"field": "year", "operator": "is", "value": "%s"}, {"field": "year", "operator": "is", "value": "%s"}, {"field": "year", "operator": "is", "value": "%s"}]}, "properties" : ["imdbnumber", "title", "year"]}, "id": 1}' % (year, str(int(year)+1), str(int(year)-1)))
                lib = jsloads(lib)['result']['tvshows']
                lib = [i for i in lib if str(i['imdbnumber']) in [imdb, tmdb, tvdb] or cleantitle.get(tvshowtitle) == cleantitle.get(i['title'])]
            except:
                lib = []

            if lib != []:
                xbmc.log('[Eternity Library] TV show already in library: %s' % tvshowtitle, xbmc.LOGINFO)
                if (control.getSetting('library.notifications') == 'true') and not range:
                    control.infoDialog('Already in library', heading=tvshowtitle)
                return 0 if range else None

            # Fetch episodes from TMDB API
            import requests
            api_key = control.getSetting('api.tmdb')

            # Get all seasons
            try:
                url = 'https://api.themoviedb.org/3/tv/%s?api_key=%s&language=de' % (tmdb, api_key)
                response = requests.get(url, timeout=10)
                show_data = response.json()

                if 'seasons' not in show_data:
                    xbmc.log('[Eternity Library] No seasons found for: %s' % tvshowtitle, xbmc.LOGWARNING)
                    if (control.getSetting('library.notifications') == 'true') and not range:
                        control.infoDialog('No seasons found', heading=tvshowtitle)
                    return 0 if range else None

                seasons = show_data['seasons']
            except:
                import traceback
                xbmc.log('[Eternity Library] Failed to fetch show data: %s\n%s' % (tvshowtitle, traceback.format_exc()), xbmc.LOGERROR)
                if (control.getSetting('library.notifications') == 'true') and not range:
                    control.infoDialog('Failed to fetch episodes', heading=tvshowtitle)
                return 0 if range else None

            files_added = 0

            # Process each season
            for season_data in seasons:
                season_num = season_data.get('season_number', 0)

                # Skip specials (Season 0)
                if season_num == 0:
                    continue

                try:
                    # Get episodes for this season
                    season_url = 'https://api.themoviedb.org/3/tv/%s/season/%s?api_key=%s&language=de' % (tmdb, season_num, api_key)
                    season_response = requests.get(season_url, timeout=10)
                    season_info = season_response.json()

                    if 'episodes' not in season_info:
                        continue

                    for episode in season_info['episodes']:
                        try:
                            ep_num = episode.get('episode_number', 0)
                            ep_title = episode.get('name', 'Episode %s' % ep_num)

                            self.strmFile({
                                'tvshowtitle': tvshowtitle,
                                'year': year,
                                'season': season_num,
                                'episode': ep_num,
                                'title': ep_title,
                                'imdb': imdb,
                                'tmdb': tmdb,
                                'tvdb': tvdb
                            })
                            files_added += 1

                        except:
                            import traceback
                            xbmc.log('[Eternity Library] Failed to create episode strm: S%02dE%02d\n%s' % (season_num, ep_num, traceback.format_exc()), xbmc.LOGERROR)

                except:
                    import traceback
                    xbmc.log('[Eternity Library] Failed to fetch season %d: %s' % (season_num, traceback.format_exc()), xbmc.LOGWARNING)

            xbmc.log('[Eternity Library] Added %d episodes for: %s' % (files_added, tvshowtitle), xbmc.LOGINFO)

            if range:
                return files_added

            # Single add - update library immediately
            if self.library_update and not control.condVisibility('Library.IsScanningVideo') and files_added > 0:
                if (control.getSetting('library.notifications') == 'true'):
                    control.infoDialog('Added %d episodes' % files_added, heading=tvshowtitle)
                control.sleep(10000)
                control.execute('UpdateLibrary(video)')

        except:
            import traceback
            xbmc.log('[Eternity Library] Failed to add TV show: %s\n%s' % (tvshowtitle, traceback.format_exc()), xbmc.LOGERROR)
            if not range:
                control.infoDialog('Failed to add', heading=tvshowtitle)
            return 0 if range else None

    def strmFile(self, i):
        """Create .strm and .nfo files for episode"""
        try:
            tvshowtitle = i['tvshowtitle']
            year = i['year']
            season = i['season']
            episode = i['episode']
            title = i['title']
            imdb = i['imdb']
            tmdb = i['tmdb']
            tvdb = i['tvdb']

            systitle = quote_plus(tvshowtitle)

            # Make filename legal
            transtitle = tvshowtitle.translate(tvshowtitle.maketrans('', '', '\/:*?"<>|'))

            # .strm content points to Eternity play action
            content = 'plugin://plugin.video.eternity/?action=play_Item&title=%s&year=%s&imdb=%s&tmdb=%s&tvdb=%s&season=%s&episode=%s&tvshowtitle=%s' % (
                quote_plus(title), year, imdb, tmdb, tvdb, season, episode, systitle
            )

            # Create folder: TV Shows/Show (Year)/Season X/
            folder = lib_tools.make_path(self.library_folder, transtitle, year, season)
            lib_tools.create_folder(folder)

            # Write .strm file: S01E05.strm
            ep_filename = 'S%02dE%02d' % (int(season), int(episode))
            strm_path = control.joinPath(folder, ep_filename + '.strm')
            lib_tools.write_file(strm_path, content)

            # Write .nfo file (only once per show)
            show_folder = lib_tools.make_path(self.library_folder, transtitle, year)
            nfo_path = control.joinPath(show_folder, 'tvshow.nfo')
            if not control.existsPath(nfo_path):
                lib_tools.write_file(nfo_path, lib_tools.nfo_url('tv', {'tvdb': tvdb, 'imdb': imdb, 'tmdb': tmdb}))

        except:
            import traceback
            xbmc.log('[Eternity Library] Failed to create episode strm: %s' % traceback.format_exc(), xbmc.LOGERROR)

    def range(self, url, list_name):
        """
        Batch import TV shows from URL (Trakt Collection, Watchlist, etc.)

        Args:
            url: Trakt API URL
            list_name: Name for notifications
        """
        try:
            if (control.getSetting('library.notifications') == 'true'):
                control.infoDialog('Starting import from %s' % list_name, heading='Library Import')

            items = []

            # Fetch items from Trakt
            if 'trakt' in url:
                from resources.lib.indexers import tvshows
                items = tvshows.TVshows().trakt_list(url, control.getSetting('trakt.user.name').strip())

            if not items:
                if (control.getSetting('library.notifications') == 'true'):
                    control.infoDialog('No items found', heading=list_name)
                return

            total_added = 0
            numitems = len(items)

            # Confirmation dialog
            if not control.yesnoDialog('Import %d shows from %s?' % (numitems, list_name), '', ''):
                return

            control.infoDialog('Importing %d shows...' % numitems, heading=list_name)

            for i in items:
                if control.monitor.abortRequested():
                    break

                try:
                    files_added = self.add(i['title'], i['year'], i['imdb'], i['tmdb'], i['tvdb'], range=True)
                    if files_added > 0:
                        total_added += 1
                except:
                    import traceback
                    xbmc.log('[Eternity Library] Failed to add: %s\n%s' % (i['title'], traceback.format_exc()), xbmc.LOGERROR)

            # Update library after batch
            if self.library_update and not control.condVisibility('Library.IsScanningVideo') and total_added > 0:
                control.sleep(10000)
                control.execute('UpdateLibrary(video)')
                if (control.getSetting('library.notifications') == 'true'):
                    control.infoDialog('Imported %d of %d shows' % (total_added, numitems), heading=list_name)
            elif total_added == 0:
                if (control.getSetting('library.notifications') == 'true'):
                    control.infoDialog('All shows already in library', heading=list_name)

        except:
            import traceback
            xbmc.log('[Eternity Library] Range import failed: %s' % traceback.format_exc(), xbmc.LOGERROR)
            if (control.getSetting('library.notifications') == 'true'):
                control.infoDialog('Import failed', heading=list_name)


class libepisodes:
    """Episode updater for background service"""

    def __init__(self):
        self.library_folder = control.joinPath(control.transPath(control.getSetting('library.tv')), '')
        self.library_update = control.getSetting('library.update') == 'true'
        self.date_time = datetime.utcnow()
        self.date = self.date_time.strftime('%Y%m%d')

    def update(self):
        """
        Check all TV shows in library for new episodes

        NO database cache - reads .strm files directly!
        """
        try:
            xbmc.log('[Eternity Library Service] Checking for new episodes', xbmc.LOGINFO)

            # Get all shows from library folder
            items = []
            try:
                shows = [control.joinPath(self.library_folder, i) for i in control.listDir(self.library_folder)[0]]
                if not shows:
                    xbmc.log('[Eternity Library Service] No shows in library', xbmc.LOGINFO)
                    return

                # Find all seasons
                seasons = []
                for show in shows:
                    try:
                        seasons += [control.joinPath(show, i) for i in control.listDir(show)[0]]
                    except:
                        pass

                # Find all episodes (.strm files)
                episodes = []
                for season in seasons:
                    try:
                        # Get last episode in season
                        ep_files = [control.joinPath(season, i) for i in control.listDir(season)[1] if i.endswith('.strm')]
                        if ep_files:
                            episodes.append(ep_files[-1])  # Last episode (highest number)
                    except:
                        pass

                # Parse .strm files to get show metadata
                for file_path in episodes:
                    try:
                        file = control.openFile(file_path)
                        read = file.read()
                        file.close()

                        if not read.startswith('plugin://plugin.video.eternity'):
                            continue

                        # Parse URL parameters
                        from urllib.parse import parse_qsl
                        params = dict(parse_qsl(read.replace('?', '')))

                        tvshowtitle = params.get('tvshowtitle', '')
                        if not tvshowtitle:
                            continue

                        year = params.get('year', '')
                        imdb = params.get('imdb', '')
                        tmdb = params.get('tmdb', '')
                        tvdb = params.get('tvdb', '')

                        items.append({
                            'tvshowtitle': tvshowtitle,
                            'year': year,
                            'imdb': imdb,
                            'tmdb': tmdb,
                            'tvdb': tvdb
                        })

                    except:
                        import traceback
                        xbmc.log('[Eternity Library Service] Failed to parse strm: %s' % traceback.format_exc(), xbmc.LOGERROR)

                # Remove duplicates
                items = [i for x, i in enumerate(items) if i not in items[x + 1:]]

                if len(items) == 0:
                    xbmc.log('[Eternity Library Service] No shows in .strm files', xbmc.LOGINFO)
                    return

                xbmc.log('[Eternity Library Service] Found %d shows to check' % len(items), xbmc.LOGINFO)

            except:
                import traceback
                xbmc.log('[Eternity Library Service] Failed to scan library: %s' % traceback.format_exc(), xbmc.LOGERROR)
                return

            # Get Kodi library shows (for comparison)
            try:
                lib = control.jsonrpc('{"jsonrpc": "2.0", "method": "VideoLibrary.GetTVShows", "params": {"properties": ["imdbnumber", "title", "year"]}, "id": 1 }')
                lib = jsloads(lib)['result']['tvshows']
            except:
                import traceback
                xbmc.log('[Eternity Library Service] Failed to get Kodi library: %s' % traceback.format_exc(), xbmc.LOGERROR)
                return

            files_added = 0

            # Check each show for new episodes
            for item in items:
                if control.monitor.abortRequested():
                    break

                try:
                    # Get all episodes from TMDB
                    import requests
                    api_key = control.getSetting('api.tmdb')
                    tmdb = item['tmdb']

                    # Get show data
                    url = 'https://api.themoviedb.org/3/tv/%s?api_key=%s&language=de' % (tmdb, api_key)
                    response = requests.get(url, timeout=10)
                    show_data = response.json()

                    if 'seasons' not in show_data:
                        continue

                    seasons = show_data['seasons']

                    # Get last episode in Kodi library
                    try:
                        id = [item['imdb'], item['tvdb']]
                        if item['tmdb']:
                            id += [item['tmdb']]

                        ep = [x['title'] for x in lib if str(x['imdbnumber']) in id or (x['title'] == item['tvshowtitle'] and str(x['year']) == item['year'])][0]
                        ep = control.jsonrpc('{"jsonrpc": "2.0", "method": "VideoLibrary.GetEpisodes", "params": {"filter":{"and": [{"field": "tvshow", "operator": "is", "value": "%s"}]}, "properties": ["season", "episode"]}, "id": 1}' % ep)
                        ep = jsloads(ep).get('result', {}).get('episodes', {})
                        ep = [{'season': int(i['season']), 'episode': int(i['episode'])} for i in ep]
                        ep = sorted(ep, key=lambda x: (x['season'], x['episode']))[-1]

                        last_season = ep['season']
                        last_episode = ep['episode']
                    except:
                        # No episodes in library yet, start from beginning
                        last_season = 0
                        last_episode = 0

                    # Check all seasons for new episodes
                    for season_data in seasons:
                        season_num = season_data.get('season_number', 0)

                        # Skip specials
                        if season_num == 0:
                            continue

                        try:
                            # Get episodes for this season
                            season_url = 'https://api.themoviedb.org/3/tv/%s/season/%s?api_key=%s&language=de' % (tmdb, season_num, api_key)
                            season_response = requests.get(season_url, timeout=10)
                            season_info = season_response.json()

                            if 'episodes' not in season_info:
                                continue

                            for episode in season_info['episodes']:
                                try:
                                    ep_num = episode.get('episode_number', 0)
                                    ep_title = episode.get('name', 'Episode %s' % ep_num)
                                    premiered = episode.get('air_date', '')

                                    # Skip if already in library
                                    if season_num < last_season or (season_num == last_season and ep_num <= last_episode):
                                        continue

                                    # Skip if not aired yet
                                    if premiered and int(re.sub('[^0-9]', '', str(premiered))) > int(re.sub(r'[^0-9]', '', str(self.date))):
                                        continue

                                    # Add new episode
                                    libtvshows().strmFile({
                                        'tvshowtitle': item['tvshowtitle'],
                                        'year': item['year'],
                                        'season': season_num,
                                        'episode': ep_num,
                                        'title': ep_title,
                                        'imdb': item['imdb'],
                                        'tmdb': item['tmdb'],
                                        'tvdb': item['tvdb']
                                    })
                                    files_added += 1

                                    xbmc.log('[Eternity Library Service] Added: %s S%02dE%02d' % (item['tvshowtitle'], season_num, ep_num), xbmc.LOGINFO)

                                except:
                                    import traceback
                                    xbmc.log('[Eternity Library Service] Failed to add episode: %s' % traceback.format_exc(), xbmc.LOGERROR)

                        except:
                            import traceback
                            xbmc.log('[Eternity Library Service] Failed to fetch season: %s' % traceback.format_exc(), xbmc.LOGWARNING)

                except:
                    import traceback
                    xbmc.log('[Eternity Library Service] Failed to check show: %s' % traceback.format_exc(), xbmc.LOGERROR)

            # Update Kodi library if new episodes were added
            if self.library_update and not control.condVisibility('Library.IsScanningVideo') and files_added > 0:
                xbmc.log('[Eternity Library Service] Added %d new episodes, updating library' % files_added, xbmc.LOGINFO)
                if (control.getSetting('library.notifications') == 'true'):
                    control.infoDialog('%d neue Episoden hinzugefügt' % files_added, heading='Bibliothek')
                control.sleep(10000)
                control.execute('UpdateLibrary(video)')

        except:
            import traceback
            xbmc.log('[Eternity Library Service] Update failed: %s' % traceback.format_exc(), xbmc.LOGERROR)

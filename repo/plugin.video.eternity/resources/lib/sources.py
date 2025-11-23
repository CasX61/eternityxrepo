# edit 2025-06-12
import sys
import re, json, random, time
from concurrent.futures import ThreadPoolExecutor
from resources.lib import log_utils, utils, control
from resources.lib.control import py2_decode, py2_encode, quote_plus, parse_qsl
import resolveurl as resolver
# from functools import reduce
from resources.lib.control import getKodiVersion

if int(getKodiVersion()) >= 20: from infotagger.listitem import ListItemInfoTag

# für self.sysmeta - zur späteren verwendung als meta
_params = dict(parse_qsl(sys.argv[2].replace('?',''))) if len(sys.argv) > 1 else dict()

class sources:
    def __init__(self):
        self.getConstants()
        self.sources = []
        self.current = int(time.time())
        if 'sysmeta' in _params: self.sysmeta = _params['sysmeta'] # string zur späteren verwendung als meta
        self.watcher = False
        self.executor = ThreadPoolExecutor(max_workers=20)
        self.url = None

    def get(self, params):
        # sysmeta should always be provided (even for Trakt - fixed in episodes.py)
        sysmeta_str = params.get('sysmeta', '{}')
        data = json.loads(sysmeta_str) if sysmeta_str else {}

        self.mediatype = data.get('mediatype')
        self.aliases = data.get('aliases') if 'aliases' in data else []

        title = py2_encode(data.get('title')) if data.get('title') else ''
        originaltitle = py2_encode(data.get('originaltitle')) if 'originaltitle' in data else title
        year = data.get('year') if 'year' in data else None
        imdb = data.get('imdb_id') if 'imdb_id' in data else data.get('imdbnumber') if 'imdbnumber' in data else None
        if not imdb and 'imdb' in data: imdb = data.get('imdb')
        tmdb = data.get('tmdb_id') if 'tmdb_id' in data else None
        season = data.get('season') if 'season' in data else 0
        episode = data.get('episode') if 'episode' in data else 0
        premiered = data.get('premiered') if 'premiered' in data else None
        meta = sysmeta_str
        select = data.get('select') if 'select' in data else None

        return title, year, imdb, season, episode, originaltitle, premiered, meta, select

    def play(self, params):
        title, year, imdb, season, episode, originaltitle, premiered, meta, select = self.get(params)
        try:
            url = None
            #Liste der gefundenen Streams
            items = self.getSources(title, year, imdb, season, episode, originaltitle, premiered)
            select = control.getSetting('hosts.mode') if select == None else select
            ## unnötig
            #select = '1' if control.getSetting('downloads') == 'true' and not (control.getSetting('download.movie.path') == '' or control.getSetting('download.tv.path') == '') else select

            # # TODO überprüfen wofür mal gedacht
            # if control.window.getProperty('PseudoTVRunning') == 'True':
            #     return control.resolveUrl(int(sys.argv[1]), True, control.item(path=str(self.sourcesDirect(items))))

            if len(items) > 0:
                # Auswahl Verzeichnis
                if select == '1' and 'plugin' in control.infoLabel('Container.PluginName'):
                    control.window.clearProperty(self.itemsProperty)
                    control.window.setProperty(self.itemsProperty, json.dumps(items))
                    
                    control.window.clearProperty(self.metaProperty)
                    control.window.setProperty(self.metaProperty, meta)
                    control.sleep(2)
                    return control.execute('Container.Update(%s?action=addItem&title=%s)' % (sys.argv[0], quote_plus(title)))
                # Auswahl Dialog
                elif select == '0' or select == '1':
                    url = self.sourcesDialog(items)
                    if  url == 'close://': return
                # Autoplay
                else:
                    url = self.sourcesDirect(items)

            if url == None:
                import xbmc
                xbmc.log('SOURCES play: URL is None, showing error', xbmc.LOGERROR)
                return self.errorForSources()

            import xbmc
            xbmc.log('SOURCES play: Got URL, calling player. URL: %s' % url, xbmc.LOGINFO)

            try: meta = json.loads(meta)
            except: pass

            from resources.lib.player import player
            xbmc.log('SOURCES play: Calling player().run() with title=%s' % title, xbmc.LOGINFO)
            player().run(title, url, meta)
            xbmc.log('SOURCES play: player().run() returned', xbmc.LOGINFO)
        except Exception as e:
            import xbmc
            xbmc.log('SOURCES play: Exception in play(): %s' % str(e), xbmc.LOGERROR)
            log_utils.log('Error %s' % str(e), log_utils.LOGERROR)


# Liste gefundene Streams Indexseite|Hoster
    def addItem(self, title):
        control.playlist.clear()

        items = control.window.getProperty(self.itemsProperty)
        items = json.loads(items)
        if items == None or len(items) == 0: control.idle() ; sys.exit()

        sysaddon = sys.argv[0]
        syshandle = int(sys.argv[1])
        systitle = sysname = quote_plus(title)

        meta = control.window.getProperty(self.metaProperty)
        meta = json.loads(meta)
#TODO
        if meta['mediatype'] == 'movie':
            # downloads = True if control.getSetting('downloads') == 'true' and control.exists(control.translatePath(control.getSetting('download.movie.path'))) else False
            downloads = True if control.getSetting('downloads') == 'true' and control.getSetting('download.movie.path') else False
        else:
            # downloads = True if control.getSetting('downloads') == 'true' and control.exists(control.translatePath(control.getSetting('download.tv.path'))) else False
            downloads = True if control.getSetting('downloads') == 'true' and control.getSetting('download.tv.path') else False

        addonPoster, addonBanner = control.addonPoster(), control.addonBanner()
        addonFanart, settingFanart = control.addonFanart(), control.getSetting('fanart')

        if 'backdrop_url' in meta and 'http' in meta['backdrop_url']: fanart = meta['backdrop_url']
        elif 'fanart' in meta and 'http' in meta['fanart']: fanart = meta['fanart']
        else: fanart = addonFanart

        if 'cover_url' in meta and 'http' in meta['cover_url']: poster = meta['cover_url']
        elif 'poster' in meta and 'http' in meta['poster']: poster = meta['poster']
        else:  poster = addonPoster
        sysimage = poster

        if 'season' in meta and 'episode' in meta:
            sysname += quote_plus(' S%02dE%02d' % (int(meta['season']), int(meta['episode'])))
        elif 'year' in meta:
            sysname += quote_plus(' (%s)' % meta['year'])

        for i in range(len(items)):
            try:
                label = items[i]['label']
                syssource = quote_plus(json.dumps([items[i]]))

                item = control.item(label=label, offscreen=True)
                item.setProperty('IsPlayable', 'true')
                item.setArt({'poster': poster, 'banner': addonBanner})
                if settingFanart == 'true': item.setProperty('Fanart_Image', fanart)

                cm = []
                if downloads:
                    cm.append(("Download", 'RunPlugin(%s?action=download&name=%s&image=%s&source=%s)' % (sysaddon, sysname, sysimage, syssource)))
                cm.append(('Einstellungen', 'RunPlugin(%s?action=addonSettings)' % sysaddon))
                item.addContextMenuItems(cm)

                url = "%s?action=playItem&title=%s&source=%s" % (sysaddon, systitle, syssource)

                # ## Notwendig für Library Exporte ##
                # ## Amazon Scraper Details ##
                # if "amazon" in label.lower():
                #     aid = re.search(r'asin%3D(.*?)%22%2C', url)
                #     url = "plugin://plugin.video.amazon-test/?mode=PlayVideo&asin=" + aid.group(1)

                ##https: // codedocs.xyz / AlwinEsch / kodi / group__python__xbmcgui__listitem.html  # ga0b71166869bda87ad744942888fb5f14

                name = '%s%sStaffel: %s   Episode: %s' % (title, "\n", meta['season'], meta['episode']) if 'season' in meta else title
                plot = meta['plot'] if 'plot' in meta and len(meta['plot'].strip()) >= 1 else ''
                plot = '[COLOR blue]%s[/COLOR]%s%s' % (name, "\n\n", py2_encode(plot))

                if 'duration' in meta:
                    infolable = {'plot': plot,'duration': meta['duration']}
                else:
                    infolable = {'plot': plot}

                # TODO
                # if 'cast' in meta and meta['cast']: item.setCast(meta['cast'])
                # # # remove unsupported InfoLabels
                meta.pop('cast', None)  # ersetzt durch item.setCast(i['cast'])
                meta.pop('number_of_seasons', None)
                meta.pop('imdb_id', None)
                meta.pop('tvdb_id', None)
                meta.pop('tmdb_id', None)

                ## Quality Video Stream from source.append quality - items[i]['quality']
                video_streaminfo ={}
                if "4k" in items[i]['quality'].lower():
                    video_streaminfo.update({'width': 3840, 'height': 2160})
                elif "1080p" in items[i]['quality'].lower():
                    video_streaminfo.update({'width': 1920, 'height': 1080})
                elif "hd" in items[i]['quality'].lower() or "720p" in items[i]['quality'].lower():
                    video_streaminfo.update({'width': 1280,'height': 720})
                else:
                    # video_streaminfo.update({"width": 720, "height": 576})
                    video_streaminfo.update({})

                ## Codec for Video Stream from extra info - items[i]['info']
                if 'hevc' in items[i]['label'].lower():
                    video_streaminfo.update({'codec': 'hevc'})
                elif '265' in items[i]['label'].lower():
                    video_streaminfo.update({'codec': 'h265'})
                elif 'mkv' in items[i]['label'].lower():
                    video_streaminfo.update({'codec': 'mkv'})
                elif 'mp4' in items[i]['label'].lower():
                    video_streaminfo.update({'codec': 'mp4'})
                else:
                    # video_streaminfo.update({'codec': 'h264'})
                    video_streaminfo.update({'codec': ''})

                ## Quality & Channels Audio Stream from extra info - items[i]['info']
                audio_streaminfo = {}
                if 'dts' in items[i]['label'].lower():
                    audio_streaminfo.update({'codec': 'dts'})
                elif 'plus' in items[i]['label'].lower() or 'e-ac3' in items[i]['label'].lower():
                    audio_streaminfo.update({'codec': 'eac3'})
                elif 'dolby' in items[i]['label'].lower() or 'ac3' in items[i]['label'].lower():
                    audio_streaminfo.update({'codec': 'ac3'})
                else:
                    # audio_streaminfo.update({'codec': 'aac'})
                    audio_streaminfo.update({'codec': ''})

                ## Channel update ##
                if '7.1' in items[i].get('info','').lower():
                    audio_streaminfo.update({'channels': 8})
                elif '5.1' in items[i].get('info','').lower():
                    audio_streaminfo.update({'channels': 6})
                else:
                    # audio_streaminfo.update({'channels': 2})
                    audio_streaminfo.update({'channels': ''})

                if int(getKodiVersion()) <= 19:
                    item.setInfo(type='Video', infoLabels=infolable)
                    item.addStreamInfo('video', video_streaminfo)
                    item.addStreamInfo('audio', audio_streaminfo)
                else:
                    info_tag = ListItemInfoTag(item, 'video')
                    info_tag.set_info(infolable)
                    stream_details = {
                        'video': [video_streaminfo],
                        'audio': [audio_streaminfo]}
                    info_tag.set_stream_details(stream_details)
                    # info_tag.set_cast(aActors)

                control.addItem(handle=syshandle, url=url, listitem=item, isFolder=False)
            except:
                pass

        control.content(syshandle, 'videos')
        control.plugincategory(syshandle, control.addonVersion)
        control.endofdirectory(syshandle, cacheToDisc=True)


    def playItem(self, title, source):
        isDebug = False
        if isDebug: log_utils.log('start playItem', log_utils.LOGWARNING)
        try:
            meta = control.window.getProperty(self.metaProperty)
            meta = json.loads(meta)

            header = control.addonInfo('name')
            # control.idle() #ok
            progressDialog = control.progressDialog if control.getSetting('progress.dialog') == '0' else control.progressDialogBG
            progressDialog.create(header, '')
            progressDialog.update(0)

            item = json.loads(source)[0]
            #if isDebug: log_utils.log('playItem 237', log_utils.LOGWARNING)
            if item['source'] == None: raise Exception()
            
            future = self.executor.submit(self.sourcesResolve, item)
            
            waiting_time = 30
            while waiting_time > 0:
                try:
                    if control.abortRequested: return sys.exit()
                    if progressDialog.iscanceled(): return progressDialog.close()
                except:
                    pass
                if future.done(): break
                control.sleep(1)
                waiting_time = waiting_time - 1
                progressDialog.update(int(100 - 100. / 30 * waiting_time), str(item['label']))
                #if isDebug: log_utils.log('playItem 252', log_utils.LOGWARNING)
                if control.condVisibility('Window.IsActive(virtualkeyboard)') or \
                        control.condVisibility('Window.IsActive(yesnoDialog)'):
                        # or control.condVisibility('Window.IsActive(PopupRecapInfoWindow)'):
                    waiting_time = waiting_time + 1  # dont count down while dialog is presented
                if future.done(): break

            try: progressDialog.close()
            except: pass
            if isDebug: log_utils.log('playItem 261', log_utils.LOGWARNING)
            control.execute('Dialog.Close(virtualkeyboard)')
            control.execute('Dialog.Close(yesnoDialog)')

            if isDebug: log_utils.log('playItem url: %s' % self.url, log_utils.LOGWARNING)
            if self.url == None:
                #self.errorForSources()
                return

            from resources.lib.player import player
            player().run(title, self.url, meta)
            return self.url
        except Exception as e:
            log_utils.log('Error %s' % str(e), log_utils.LOGERROR)


    def getSources(self, title, year, imdb, season, episode, originaltitle, premiered, quality='HD', timeout=30):
#TODO
        # self._getHostDict()
        control.idle() #ok
        progressDialog = control.progressDialog if control.getSetting('progress.dialog') == '0' else control.progressDialogBG
        progressDialog.create(control.addonInfo('name'), "Quellen werden vorbereitet")
        progressDialog.update(0, "Quellen werden vorbereitet")

        sourceDict = self.sourceDict
        sourceDict = [(i[0], i[1], i[1].priority) for i in sourceDict]
        random.shuffle(sourceDict)
        sourceDict = sorted(sourceDict, key=lambda i: i[2])
        content = 'movies' if season == 0 or season == '' or season == None else 'shows'
        aliases, localtitle = utils.getAliases(imdb, content)
        if localtitle and title != localtitle and originaltitle != localtitle:
            if not title in aliases: aliases.append(title)
            title = localtitle
        for i in self.aliases:
            if not i in aliases:
                aliases.append(i)
        titles = utils.get_titles_for_search(title, originaltitle, aliases)

        futures = {self.executor.submit(self._getSource, titles, year, season, episode, imdb, provider[0], provider[1]): provider[0] for provider in sourceDict}
        provider_names = {provider[0].upper() for provider in sourceDict}

        # Check debrid status
        from resources.lib.modules import debrid
        debrid_status = debrid.status()

        string4 = "Total"
        string6 = "Prem"
        string7 = "Normal"

        try: timeout = int(control.getSetting('scrapers.timeout'))
        except: pass

        quality = control.getSetting('hosts.quality')
        if quality == '': quality = '0'

        source_4k = 0
        source_1080 = 0
        source_720 = 0
        source_sd = 0
        d_source_4k = 0
        d_source_1080 = 0
        d_source_720 = 0
        d_source_sd = 0
        total = d_total = 0
        total_format = '[COLOR %s][B]%s[/B][/COLOR]'
        pdiag_format = ' 4K: %s | 1080p: %s | 720p: %s | SD: %s | %s: %s                                         '.split('|')

        for i in range(0, 4 * timeout):
            try:
                if control.abortRequested: return sys.exit()
                try:
                    if progressDialog.iscanceled(): break
                except:
                    pass

                if len(self.sources) > 0:
                    # Count non-debrid sources
                    if quality in ['0']:
                        source_4k = len([e for e in self.sources if e['quality'] == '4K' and 'debrid' not in e])
                        source_1080 = len([e for e in self.sources if e['quality'] in ['1440p','1080p'] and 'debrid' not in e])
                        source_720 = len([e for e in self.sources if e['quality'] in ['720p','HD'] and 'debrid' not in e])
                        source_sd = len([e for e in self.sources if e['quality'] not in ['4K','1440p','1080p','720p','HD'] and 'debrid' not in e])
                    elif quality in ['1']:
                        source_1080 = len([e for e in self.sources if e['quality'] in ['1440p','1080p'] and 'debrid' not in e])
                        source_720 = len([e for e in self.sources if e['quality'] in ['720p','HD'] and 'debrid' not in e])
                        source_sd = len([e for e in self.sources if e['quality'] not in ['4K','1440p','1080p','720p','HD'] and 'debrid' not in e])
                    elif quality in ['2']:
                        source_1080 = len([e for e in self.sources if e['quality'] in ['1080p'] and 'debrid' not in e])
                        source_720 = len([e for e in self.sources if e['quality'] in ['720p','HD'] and 'debrid' not in e])
                        source_sd = len([e for e in self.sources if e['quality'] not in ['4K','1440p','1080p','720p','HD'] and 'debrid' not in e])
                    elif quality in ['3']:
                        source_720 = len([e for e in self.sources if e['quality'] in ['720p','HD'] and 'debrid' not in e])
                        source_sd = len([e for e in self.sources if e['quality'] not in ['4K','1440p','1080p','720p','HD'] and 'debrid' not in e])
                    else:
                        source_sd = len([e for e in self.sources if e['quality'] not in ['4K','1440p','1080p','720p','HD'] and 'debrid' not in e])

                    total = source_4k + source_1080 + source_720 + source_sd

                    # Count debrid sources
                    if debrid_status:
                        if quality in ['0']:
                            d_source_4k = len([e for e in self.sources if e['quality'] == '4K' and 'debrid' in e])
                            d_source_1080 = len([e for e in self.sources if e['quality'] in ['1440p','1080p'] and 'debrid' in e])
                            d_source_720 = len([e for e in self.sources if e['quality'] in ['720p','HD'] and 'debrid' in e])
                            d_source_sd = len([e for e in self.sources if e['quality'] not in ['4K','1440p','1080p','720p','HD'] and 'debrid' in e])
                        elif quality in ['1']:
                            d_source_1080 = len([e for e in self.sources if e['quality'] in ['1440p','1080p'] and 'debrid' in e])
                            d_source_720 = len([e for e in self.sources if e['quality'] in ['720p','HD'] and 'debrid' in e])
                            d_source_sd = len([e for e in self.sources if e['quality'] not in ['4K','1440p','1080p','720p','HD'] and 'debrid' in e])
                        elif quality in ['2']:
                            d_source_1080 = len([e for e in self.sources if e['quality'] in ['1080p'] and 'debrid' in e])
                            d_source_720 = len([e for e in self.sources if e['quality'] in ['720p','HD'] and 'debrid' in e])
                            d_source_sd = len([e for e in self.sources if e['quality'] not in ['4K','1440p','1080p','720p','HD'] and 'debrid' in e])
                        elif quality in ['3']:
                            d_source_720 = len([e for e in self.sources if e['quality'] in ['720p','HD'] and 'debrid' in e])
                            d_source_sd = len([e for e in self.sources if e['quality'] not in ['4K','1440p','1080p','720p','HD'] and 'debrid' in e])
                        else:
                            d_source_sd = len([e for e in self.sources if e['quality'] not in ['4K','1440p','1080p','720p','HD'] and 'debrid' in e])

                        d_total = d_source_4k + d_source_1080 + d_source_720 + d_source_sd

                # Create labels for debrid sources
                if debrid_status:
                    d_4k_label = total_format % ('red', d_source_4k) if d_source_4k == 0 else total_format % ('lime', d_source_4k)
                    d_1080_label = total_format % ('red', d_source_1080) if d_source_1080 == 0 else total_format % ('lime', d_source_1080)
                    d_720_label = total_format % ('red', d_source_720) if d_source_720 == 0 else total_format % ('lime', d_source_720)
                    d_sd_label = total_format % ('red', d_source_sd) if d_source_sd == 0 else total_format % ('lime', d_source_sd)
                    d_total_label = total_format % ('red', d_total) if d_total == 0 else total_format % ('lime', d_total)

                source_4k_label = total_format % ('red', source_4k) if source_4k == 0 else total_format % ('lime', source_4k)
                source_1080_label = total_format % ('red', source_1080) if source_1080 == 0 else total_format % ('lime', source_1080)
                source_720_label = total_format % ('red', source_720) if source_720 == 0 else total_format % ('lime', source_720)
                source_sd_label = total_format % ('red', source_sd) if source_sd == 0 else total_format % ('lime', source_sd)
                source_total_label = total_format % ('red', total) if total == 0 else total_format % ('lime', total)

                try:
                    info = [name.upper() for future, name in futures.items() if not future.done()]

                    percent = int(100 * float(i) / (2 * timeout) + 1)

                    # Build quality lines based on debrid status
                    if debrid_status:
                        # With debrid: show Prem and Normal lines
                        if quality in ['0']:
                            line1 = ('%s: ' + '|'.join(pdiag_format)) % (string6, d_4k_label, d_1080_label, d_720_label, d_sd_label, str(string4), d_total_label)
                            line2 = ('%s: ' + '|'.join(pdiag_format)) % (string7, source_4k_label, source_1080_label, source_720_label, source_sd_label, str(string4), source_total_label)
                        elif quality in ['1']:
                            line1 = ('%s: ' + '|'.join(pdiag_format[1:])) % (string6, d_1080_label, d_720_label, d_sd_label, str(string4), d_total_label)
                            line2 = ('%s: ' + '|'.join(pdiag_format[1:])) % (string7, source_1080_label, source_720_label, source_sd_label, str(string4), source_total_label)
                        elif quality in ['2']:
                            line1 = ('%s: ' + '|'.join(pdiag_format[1:])) % (string6, d_1080_label, d_720_label, d_sd_label, str(string4), d_total_label)
                            line2 = ('%s: ' + '|'.join(pdiag_format[1:])) % (string7, source_1080_label, source_720_label, source_sd_label, str(string4), source_total_label)
                        elif quality in ['3']:
                            line1 = ('%s: ' + '|'.join(pdiag_format[2:])) % (string6, d_720_label, d_sd_label, str(string4), d_total_label)
                            line2 = ('%s: ' + '|'.join(pdiag_format[2:])) % (string7, source_720_label, source_sd_label, str(string4), source_total_label)
                        else:
                            line1 = ('%s: ' + '|'.join(pdiag_format[3:])) % (string6, d_sd_label, str(string4), d_total_label)
                            line2 = ('%s: ' + '|'.join(pdiag_format[3:])) % (string7, source_sd_label, str(string4), source_total_label)
                    else:
                        # Without debrid: show only quality line
                        if quality in ['0']:
                            line1 = '|'.join(pdiag_format) % (source_4k_label, source_1080_label, source_720_label, source_sd_label, str(string4), source_total_label)
                        elif quality in ['1']:
                            line1 = '|'.join(pdiag_format[1:]) % (source_1080_label, source_720_label, source_sd_label, str(string4), source_total_label)
                        elif quality in ['2']:
                            line1 = '|'.join(pdiag_format[1:]) % (source_1080_label, source_720_label, source_sd_label, str(string4), source_total_label)
                        elif quality in ['3']:
                            line1 = '|'.join(pdiag_format[2:]) % (source_720_label, source_sd_label, str(string4), source_total_label)
                        else:
                            line1 = '|'.join(pdiag_format[3:]) % (source_sd_label, str(string4), source_total_label)

                        # Build remaining providers line (line2)
                        if (i / 2) < timeout:
                            string3 = "Verbleibende Indexseiten: %s"
                        else:
                            string3 = 'Waiting for: %s'

                        if len(info) > 6:
                            line2 = string3 % (str(len(info)))
                        elif len(info) > 1:
                            line2 = string3 % (', '.join(info))
                        elif len(info) == 1:
                            line2 = string3 % (''.join(info))
                        else:
                            line2 = 'Suche beendet!'

                    # Build remaining providers line (line3) for debrid mode
                    if debrid_status:
                        if (i / 2) < timeout:
                            string3 = "Verbleibende Indexseiten: %s"
                        else:
                            string3 = 'Waiting for: %s'

                        if len(info) > 6:
                            line3 = string3 % (str(len(info)))
                        elif len(info) > 1:
                            line3 = string3 % (', '.join(info))
                        elif len(info) == 1:
                            line3 = string3 % (''.join(info))
                        else:
                            line3 = 'Suche beendet!'

                    # Update dialog with multi-line message (Kodi 20+ style)
                    if progressDialog == control.progressDialogBG:
                        # Background dialog: combine lines
                        if debrid_status:
                            message = line1 + ' | ' + line3
                        else:
                            message = line1 + ' | ' + line2
                        progressDialog.update(max(1, percent), message)
                    else:
                        # Foreground dialog: use newlines to separate lines
                        if debrid_status:
                            message = line1 + '\n\n' + line2 + '\n\n' + line3
                        else:
                            message = line1 + '\n\n' + line2
                        progressDialog.update(max(1, percent), message)

                    if len(info) == 0: break

                except Exception as e:
                    log_utils.log('Exception Raised: %s' % str(e), log_utils.LOGERROR)

                control.sleep(1)
            except:
                pass

        time.sleep(1)

        try: progressDialog.close()
        except: pass
        self.sourcesFilter()
        return self.sources


    def _getSource(self, titles, year, season, episode, imdb, source, call):
        try:
            sources = call.run(titles, year, season, episode, imdb)  # kasi self.hostDict
            if sources == None or sources == []: raise Exception()
            sources = [json.loads(t) for t in set(json.dumps(d, sort_keys=True) for d in sources)]
            for i in sources:
                i.update({'provider': source})
                if not 'priority' in i: i.update({'priority': 100})
                if not 'prioHoster' in i: i.update({'prioHoster': 100})
            self.sources.extend(sources)
        except:
            pass


    def sourcesFilter(self):
        # hostblockDict = utils.getHostDict()
        # self.sources = [i for i in self.sources if i['source'].split('.')[0] not in str(hostblockDict)] # Hoster ausschließen (Liste)

        quality = control.getSetting('hosts.quality')
        if quality == '': quality = '0'

        random.shuffle(self.sources)

        self.sources = sorted(self.sources, key=lambda k: k['prioHoster'], reverse=False)

        for i in range(len(self.sources)):
            q = self.sources[i]['quality']
            if q.lower() == 'hd': self.sources[i].update({'quality': '720p'})

        # Debrid Integration: Tag sources with debrid resolver name
        from resources.lib.modules import debrid
        filter = []

        # Tag sources that can be resolved with debrid services
        if debrid.status():
            for d in debrid.debrid_resolvers:
                valid_hoster = set([i['source'] for i in self.sources])
                valid_hoster = [i for i in valid_hoster if d.valid_url('', i)]
                filter += [dict(list(i.items()) + [('debrid', d.name)]) for i in self.sources if i['source'] in valid_hoster]

        # Add non-debrid sources
        filter += [i for i in self.sources if not any(d.valid_url('', i['source']) for d in debrid.debrid_resolvers)] if debrid.status() else self.sources

        self.sources = filter

        # Quality filtering with debrid priority (debrid first, then non-debrid)
        filter = []
        if quality in ['0']:
            filter += [i for i in self.sources if i['quality'] == '4K' and 'debrid' in i]
            filter += [i for i in self.sources if i['quality'] == '4K' and not 'debrid' in i]
        if quality in ['0', '1']:
            filter += [i for i in self.sources if i['quality'] == '1440p' and 'debrid' in i]
            filter += [i for i in self.sources if i['quality'] == '1440p' and not 'debrid' in i]
        if quality in ['0', '1', '2']:
            filter += [i for i in self.sources if i['quality'] == '1080p' and 'debrid' in i]
            filter += [i for i in self.sources if i['quality'] == '1080p' and not 'debrid' in i]
        if quality in ['0', '1', '2', '3']:
            filter += [i for i in self.sources if i['quality'] == '720p' and 'debrid' in i]
            filter += [i for i in self.sources if i['quality'] == '720p' and not 'debrid' in i]

        filter += [i for i in self.sources if i['quality'] not in ['4K', '1440p', '1080p', '720p']]
        self.sources = filter

        if control.getSetting('hosts.sort.provider') == 'true':
            self.sources = sorted(self.sources, key=lambda k: k['provider'])

        if control.getSetting('hosts.sort.priority') == 'true' and self.mediatype == 'tvshow': self.sources = sorted(self.sources, key=lambda k: k['priority'], reverse=False)

        if str(control.getSetting('hosts.limit')) == 'true':
            self.sources = self.sources[:int(control.getSetting('hosts.limit.num'))]
        else:
            self.sources = self.sources[:100]

        for i in range(len(self.sources)):
            p = self.sources[i]['provider']
            q = self.sources[i]['quality']
            s = self.sources[i]['source']
            ## s = s.rsplit('.', 1)[0]
            l = self.sources[i]['language']

            try: f = (' | '.join(['[I]%s [/I]' % info.strip() for info in self.sources[i]['info'].split('|')]))
            except: f = ''

            label = '%02d | [B]%s[/B] | ' % (int(i + 1), p)
            if q in ['4K', '1440p', '1080p', '720p']: label += '%s | [B][I]%s [/I][/B] | %s' % (s, q, f)
            elif q == 'SD': label += '%s | %s' % (s, f)
            else: label += '%s | %s | [I]%s [/I]' % (s, f, q)
            label = label.replace('| 0 |', '|').replace(' | [I]0 [/I]', '')
            label = re.sub('\[I\]\s+\[/I\]', ' ', label)
            label = re.sub('\|\s+\|', '|', label)
            label = re.sub('\|(?:\s+|)$', '', label)

            self.sources[i]['label'] = label.upper()

            # Mark premium/debrid links with color
            if 'debrid' in self.sources[i]:
                prem_identify = control.getSetting('prem.identify')
                color_map = ['skyblue', 'red', 'yellow', 'pink', 'cyan', 'lawngreen', 'gold', 'magenta', 'yellowgreen', '']
                prem_color = color_map[int(prem_identify)] if prem_identify.isdigit() and int(prem_identify) < len(color_map) else 'skyblue'
                if prem_color:
                    self.sources[i]['label'] = '[COLOR %s]%s[/COLOR]' % (prem_color, label.upper())

        self.sources = [i for i in self.sources if 'label' in i]
        return self.sources


    def sourcesResolve(self, item, info=False):
        try:
            self.url = None
            url = item['url']
            direct = item['direct']
            local = item.get('local', False)
            provider = item['provider']
            call = [i[1] for i in self.sourceDict if i[0] == provider][0]
            url = call.resolve(url)

            if not direct == True:
                try:
                    import xbmc
                    xbmc.log('SOURCES: URL before resolveurl: %s' % url, xbmc.LOGINFO)
                    hmf = resolver.HostedMediaFile(url=url, include_disabled=True, include_universal=False)
                    xbmc.log('SOURCES: hmf.valid_url() = %s' % hmf.valid_url(), xbmc.LOGINFO)
                    if hmf.valid_url():
                        url = hmf.resolve()
                        xbmc.log('SOURCES: URL after resolveurl: %s' % url, xbmc.LOGINFO)
                        if url == False or url == None or url == '': url = None # raise Exception()
                except Exception as e:
                    import xbmc
                    xbmc.log('SOURCES: resolveurl ERROR: %s' % str(e), xbmc.LOGERROR)
                    url = None

            if url == None or (not '://' in str(url) and not local):
                log_utils.log('Kein Video Link gefunden: Provider %s / %s / %s ' % (item['provider'], item['source'] , str(item['source'])), log_utils.LOGERROR)
                raise Exception()

            # if not utils.test_stream(url):
            #     log_utils.log('URL Test Error: %s' % url, log_utils.LOGERROR)
            #     raise Exception()

            # url = utils.m3u8_check(url)

            if url:
                import xbmc
                xbmc.log('SOURCES: Final URL to play: %s' % url, xbmc.LOGINFO)
                self.url = url
                return url
            else:
                import xbmc
                xbmc.log('SOURCES: URL is empty/None, raising exception', xbmc.LOGERROR)
                raise Exception()
        except Exception as e:
            import xbmc
            xbmc.log('SOURCES: Exception in sourceResolve: %s' % str(e), xbmc.LOGERROR)
            if info: self.errorForSources()
            return


    def sourcesDialog(self, items):
        labels = [i['label'] for i in items]

        select = control.selectDialog(labels)
        if select == -1: return 'close://'

        next = [y for x,y in enumerate(items) if x >= select]
        prev = [y for x,y in enumerate(items) if x < select][::-1]

        items = [items[select]]
        items = [i for i in items+next+prev][:40]

        header = control.addonInfo('name')
        header2 = header.upper()

        progressDialog = control.progressDialog if control.getSetting('progress.dialog') == '0' else control.progressDialogBG
        progressDialog.create(header, '')
        progressDialog.update(0)

        block = None

        try:
            for i in range(len(items)):
                try:
                    if items[i]['source'] == block: raise Exception()

                    future = self.executor.submit(self.sourcesResolve, items[i])

                    try:
                        if progressDialog.iscanceled(): break
                        progressDialog.update(int((100 / float(len(items))) * i), str(items[i]['label']))
                    except:
                        progressDialog.update(int((100 / float(len(items))) * i), str(header2) + str(items[i]['label']))

                    waiting_time = 30
                    while waiting_time > 0:
                        try:
                            if control.abortRequested: return sys.exit() #xbmc.Monitor().abortRequested()
                            if progressDialog.iscanceled(): return progressDialog.close()
                        except:
                            pass

                        if future.done(): break
                        control.sleep(1)

                        waiting_time = waiting_time - 1

                        if control.condVisibility('Window.IsActive(virtualkeyboard)') or \
                                control.condVisibility('Window.IsActive(yesnoDialog)') or \
                                control.condVisibility('Window.IsActive(ProgressDialog)'):
                            waiting_time = waiting_time + 1 #dont count down while dialog is presented ## control.condVisibility('Window.IsActive(PopupRecapInfoWindow)') or \

                    if not future.done(): block = items[i]['source']

                    import xbmc
                    xbmc.log('SOURCES sourcesDialog: self.url = %s' % str(self.url), xbmc.LOGINFO)
                    if self.url == None:
                        xbmc.log('SOURCES sourcesDialog: self.url is None, raising exception', xbmc.LOGERROR)
                        raise Exception()

                    self.selectedSource = items[i]['label']

                    try: progressDialog.close()
                    except: pass

                    control.execute('Dialog.Close(virtualkeyboard)')
                    control.execute('Dialog.Close(yesnoDialog)')
                    xbmc.log('SOURCES sourcesDialog: Returning URL: %s' % str(self.url), xbmc.LOGINFO)
                    return self.url
                except:
                    pass

            try: progressDialog.close()
            except: pass

        except Exception as e:
            try: progressDialog.close()
            except: pass
            log_utils.log('Error %s' % str(e), log_utils.LOGINFO)


    def sourcesDirect(self, items):
        # TODO - OK
        # filter = [i for i in items if i['source'].lower() in self.hostcapDict and i['debrid'] == '']
        # items = [i for i in items if not i in filter]
        # items = [i for i in items if ('autoplay' in i and i['autoplay'] == True) or not 'autoplay' in i]

        u = None

        header = control.addonInfo('name')
        header2 = header.upper()

        try:
            control.sleep(1)

            progressDialog = control.progressDialog if control.getSetting('progress.dialog') == '0' else control.progressDialogBG
            progressDialog.create(header, '')
            progressDialog.update(0)
        except:
            pass

        for i in range(len(items)):
            try:
                if progressDialog.iscanceled(): break
                progressDialog.update(int((100 / float(len(items))) * i), str(items[i]['label']))
            except:
                progressDialog.update(int((100 / float(len(items))) * i), str(header2) + str(items[i]['label']))

            try:
                if control.abortRequested: return sys.exit()

                url = self.sourcesResolve(items[i])
                if u == None: u = url
                if not url == None: break
            except:
                pass

        try: progressDialog.close()
        except: pass

        return u

    def errorForSources(self):
        control.infoDialog("Keine Streams verfügbar oder ausgewählt", sound=False, icon='INFO')
  
    def getTitle(self, title):
        title = utils.normalize(title)
        return title

    def getConstants(self):
        self.itemsProperty = '%s.container.items' % control.Addon.getAddonInfo('id')
        self.metaProperty = '%s.container.meta'  % control.Addon.getAddonInfo('id')
        from scrapers import sources
        self.sourceDict = sources()

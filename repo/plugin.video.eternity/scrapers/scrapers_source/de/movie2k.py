
# megakino to (clone)  # https://movie2k.at/
# 2022-11-04
# edit 2024-12-14

from resources.lib.utils import isBlockedHoster
import re, json
from resources.lib.control import getSetting
from resources.lib.requestHandler import cRequestHandler
from scrapers.modules.tools import cParser

SITE_IDENTIFIER = 'movie2k'
SITE_DOMAIN = 'movie2k.ch' # https://www3.hdfilme.me/  https://kinokiste.eu/
SITE_NAME = SITE_IDENTIFIER.upper()

class source:
    def __init__(self):
        self.priority = 1
        self.language = ['de']
        self.domain = getSetting('provider.' + SITE_IDENTIFIER + '.domain', SITE_DOMAIN)
        self.base_link = 'https://' + self.domain

        # self.api = 'api.' + self.domain
        #self.search_link = 'https://'+ self.api +'/data/browse?lang=2&keyword=%s&year=%s&rating=&votes=&genre=&country=&cast=&directors=&type=%s&order_by=&page=1' # 'browse?c=movie&m=filter&year=%s&keyword=%s'
        #self.search_link = 'https://api.movie2k.ch/data/search/?lang=2&keyword=%s'
        # https://api.movie2k.ch/data/browse?keyword=mulan
        # https://movie2k.ch/browse?c=movie&m=filter&keyword=mulan
        #self.search_link = 'https://api.movie2k.ch/data/browse?lang=2&keyword=%s&year=%s&rating=&votes=&genre=&country=&cast=&directors=&type=%s&order_by=&page=1'
        self.search_link = 'https://movie2k.ch/data/browse/?lang=2&keyword=%s&year=%s&type=%s&page=1'   # (title, year, mtype)
        self.sources = []

    def run(self, titles, year, season=0, episode=0, imdb=''):
        jSearch = self.search(titles, year, season, episode)
        if jSearch == [] or jSearch == 0: return

        # Sort by quality (1080p first) and date (newest first)
        def get_quality_score(stream):
            release = stream.get('release', '').lower()
            if '2160p' in release or '4k' in release: return 4
            if '1080p' in release: return 3
            if '720p' in release: return 2
            return 1

        jSearch = sorted(jSearch, key=lambda k: (get_quality_score(k), k.get('added', '')), reverse=True)

        import xbmc
        xbmc.log('MOVIE2K run: Found %d total streams' % len(jSearch), xbmc.LOGINFO)

        total = 0
        loop = 0
        for stream in jSearch:
            sUrl = stream['stream']
            if 'streamtape' in sUrl: continue
            loop += 1
            xbmc.log('MOVIE2K run: Processing stream %d: %s' % (loop, sUrl), xbmc.LOGINFO)
            if loop == 50:  # Check max 50 streams
                break

            quality = 'HD'
            release = stream.get('release', '')
            if '2160p' in release or '4k' in release.lower():
                quality = '4K'
            elif '1080p' in release:
                quality = '1080p'
            elif '720p' in release:
                quality = '720p'

            isBlocked, hoster, url, prioHoster = isBlockedHoster(sUrl)
            if isBlocked: continue
            if url:
                self.sources.append({'source': hoster, 'quality': quality, 'language': 'de', 'url': url, 'direct': True, 'prioHoster': prioHoster})
                total += 1
                xbmc.log('MOVIE2K run: Added source %d/%d: %s (%s)' % (total, 10, hoster, quality), xbmc.LOGINFO)
                if total == 10: break

        xbmc.log('MOVIE2K run: Returning %d sources' % len(self.sources), xbmc.LOGINFO)
        return self.sources

    def resolve(self, url):
        return  url

    def search(self, titles, year, season, episode):
        jSearch = []
        mtype = 'movies'
        if season > 0:
            year = ''
            mtype = 'tvseries'
        for title in titles:
            try:
                query = self.search_link % (title, year, mtype)
                oRequest = cRequestHandler(query)
                Search = oRequest.request()
                if '"success":false' in Search: continue
                Search = re.sub(r'\\\s+\\', '\\\\',   Search) # error - Rick and Morty
                jSearch = json.loads(Search)['movies']
                if jSearch == []:  continue

                import xbmc
                xbmc.log('MOVIE2K search: Found %d results for "%s"' % (len(jSearch), title), xbmc.LOGINFO)

                if season > 0:
                    for i in jSearch:
                        isMatch, sSeason = cParser.parseSingleResult(i.get('title'), 'Staffel.*?(\d+)')
                        if sSeason == str(season):
                            id = i.get('_id', False)
                            if id: break
                else:
                    for i in jSearch:
                        movie_year = str(i.get('year', '')) if i.get('year') else ''
                        search_year = str(year) if year else ''
                        xbmc.log('MOVIE2K search: Checking "%s" (%s) against year %s' % (i.get('title'), movie_year, search_year), xbmc.LOGINFO)

                        # Compare years as strings, allow +/- 1 year tolerance
                        if movie_year and search_year:
                            if abs(int(movie_year) - int(search_year)) > 1:
                                xbmc.log('MOVIE2K search: Year mismatch, skipping', xbmc.LOGINFO)
                                continue

                        id = i.get('_id', False)
                        if id:
                            xbmc.log('MOVIE2K search: Found match! ID: %s' % id, xbmc.LOGINFO)
                            break
                oRequest = cRequestHandler('https://movie2k.ch/data/watch/?_id=%s'  % id)
                jSearch = json.loads(oRequest.request())
                if season > 0:
                    jSearch = jSearch['streams']
                    #jSearch = sorted(jSearch, key=lambda k: k['e'], reverse=False)
                    jSearchNew = []
                    for i in jSearch:
                        if not i.get('e', False): continue
                        elif not str(i.get('e')) == str(episode): continue
                        jSearchNew.append(i)
                    return jSearchNew
                else:
                    return jSearch['streams']
            except:
                continue
        return jSearch

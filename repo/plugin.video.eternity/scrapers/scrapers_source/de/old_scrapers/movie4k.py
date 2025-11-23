
# movie4k
# 2022-11-11
# edit 2024-12-14

from resources.lib.utils import isBlockedHoster
import re
from scrapers.modules.tools import cParser  # re - alternative
from resources.lib.requestHandler import cRequestHandler
from scrapers.modules import cleantitle, dom_parser
from resources.lib.control import getSetting, setSetting

# Try to import cloudscraper for Cloudflare bypass
try:
    # Try cloudscraper2 (from script.module.cloudscraper)
    import cloudscraper2 as cloudscraper
    CLOUDSCRAPER_AVAILABLE = True
    CLOUDSCRAPER_TYPE = 'cloudscraper2'
except:
    try:
        # Try standard cloudscraper
        import cloudscraper
        CLOUDSCRAPER_AVAILABLE = True
        CLOUDSCRAPER_TYPE = 'cloudscraper'
    except:
        try:
            # Fallback to old cfscrape module (won't work with modern CF)
            import sys
            import os
            addon_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            modules_path = os.path.join(addon_path, 'modules')
            if modules_path not in sys.path:
                sys.path.insert(0, modules_path)
            import cfscrape as cloudscraper
            CLOUDSCRAPER_AVAILABLE = True
            CLOUDSCRAPER_TYPE = 'cfscrape (legacy - may not work)'
        except:
            CLOUDSCRAPER_AVAILABLE = False
            CLOUDSCRAPER_TYPE = 'none'

SITE_IDENTIFIER = 'movie4k'
SITE_DOMAIN = 'movie4k.food' # https://movie4k.bid/
SITE_NAME = SITE_IDENTIFIER.upper()

class source:
    def __init__(self):
        self.priority = 1
        self.language = ['de']
        self.domain = getSetting('provider.' + SITE_IDENTIFIER + '.domain', SITE_DOMAIN)
        self.base_link = 'https://' + self.domain

        #self.search_link = 'https://movie4k.pics/index.php?do=search&subaction=search&search_start=0&full_search=1&result_from=1&titleonly=3&story=%s'
        self.search_link = self.base_link + '/index.php?story=%s&do=search&subaction=search&titleonly=3'
        self.checkHoster = False if getSetting('provider.movie4k.checkHoster') == 'false' else True
        self.sources = []

        # Create cloudflare-bypassing session
        if CLOUDSCRAPER_AVAILABLE:
            try:
                self.scraper = cloudscraper.create_scraper()
                import xbmc
                xbmc.log('MOVIE4K: Cloudflare scraper initialized - Type: %s' % CLOUDSCRAPER_TYPE, xbmc.LOGINFO)
            except Exception as e:
                import xbmc
                xbmc.log('MOVIE4K: Failed to create scraper: %s' % str(e), xbmc.LOGERROR)
                self.scraper = None
        else:
            self.scraper = None


    def run(self, titles, year, season=0, episode=0, imdb=''):
        sources = []
        try:
            import xbmc

            # WARNING: movie4k.food is protected by Cloudflare
            if not self.scraper:
                xbmc.log('MOVIE4K: Cloudflare scraper not available - movie4k.food requires Cloudflare bypass!', xbmc.LOGERROR)
                xbmc.log('MOVIE4K: Install script.module.cloudscraper for Cloudflare support', xbmc.LOGINFO)
                # Still try, but will likely fail
            else:
                xbmc.log('MOVIE4K: Using cloudflare bypass scraper', xbmc.LOGINFO)

            t = set([cleantitle.get(i) for i in set(titles) if i])
            years = (year, year+1, year-1, 0)
            links = []

            if season == 0:
                xbmc.log('MOVIE4K: Fetching from meinecloud for IMDb: %s' % imdb, xbmc.LOGINFO)
                ## https://meinecloud.click/movie/tt1477834
                #oRequest = cRequestHandler('https://meinecloud.click/movie/%s' % imdb, caching=True)
                #sHtmlContent = oRequest.request()

                # Use scraper if available, otherwise fallback
                if self.scraper:
                    try:
                        sHtmlContent = self.scraper.get('https://meinecloud.click/movie/%s' % imdb, timeout=10).text
                    except:
                        xbmc.log('MOVIE4K: Cloudflare scraper failed, trying direct request', xbmc.LOGERROR)
                        import requests
                        sHtmlContent = requests.get('https://meinecloud.click/movie/%s' % imdb, timeout=10).text
                else:
                    import requests
                    sHtmlContent = requests.get('https://meinecloud.click/movie/%s' % imdb, timeout=10).text
                isMatch, aResult = cParser.parse(sHtmlContent, 'data-link="([^"]+)')
                for sUrl in aResult:
                    if sUrl.startswith('/'): sUrl = 'https:' + sUrl
                    isBlocked, hoster, url, prioHoster = isBlockedHoster(sUrl)
                    if isBlocked: continue
                    if url:
                        self.sources.append({'source': hoster, 'quality': '1080p', 'language': 'de', 'url': url, 'direct': True, 'prioHoster': prioHoster})
                return self.sources

            for sSearchText in titles:
                try:
                    xbmc.log('MOVIE4K: Searching for: %s' % sSearchText, xbmc.LOGINFO)
                    #oRequest = cRequestHandler(self.search_link % sSearchText, caching=True)
                    #sHtmlContent = oRequest.request()

                    search_url = self.search_link % sSearchText
                    # Use scraper if available
                    if self.scraper:
                        try:
                            sHtmlContent = self.scraper.get(search_url, timeout=10).text
                            xbmc.log('MOVIE4K: Got response with cloudflare bypass, length=%d' % len(sHtmlContent), xbmc.LOGINFO)
                        except Exception as e:
                            xbmc.log('MOVIE4K: Cloudflare scraper failed: %s' % str(e), xbmc.LOGERROR)
                            import requests
                            sHtmlContent = requests.get(search_url, timeout=10).text
                    else:
                        xbmc.log('MOVIE4K: No cloudflare scraper available, using direct request', xbmc.LOGINFO)
                        import requests
                        sHtmlContent = requests.get(search_url, timeout=10).text
                    pattern = 'article class.*?href="([^"]+).*?<h3>([^<]+).*?white">([^<]+)'
                    isMatch, aResult = cParser.parse(sHtmlContent, pattern)
                    if not isMatch: continue

                    for sUrl, sName, sYear in aResult:
                        # if season == 0:
                        #     if cleantitle.get(sName) in t and int(sYear) in years:
                        #         # url = sUrl
                        #         # break
                        #         links.append(sUrl)
                        #
                        # else:
                        # if cleantitle.get(sName.split('-')[0].strip()) in t and str(season) in sName.split('-')[1]:
                        if cleantitle.get(sName) in t:
                            links.append(sUrl)
                            #break
                    if len(links) > 0: break
                except:
                    continue

            if len(links) == 0: return sources

            for url in links:
                xbmc.log('MOVIE4K: Fetching streams from: %s' % url, xbmc.LOGINFO)
                #sHtmlContent = cRequestHandler(url).request()

                # Use scraper if available
                if self.scraper:
                    try:
                        sHtmlContent = self.scraper.get(url, timeout=10).text
                    except:
                        import requests
                        sHtmlContent = requests.get(url, timeout=10).text
                else:
                    import requests
                    sHtmlContent = requests.get(url, timeout=10).text
                #isMatch, quality = cParser().parseSingleResult(sHtmlContent, 'QualitÃ¤t:.*?span>([^<]+)')
                quality = 'HD'
                #if season > 0:
                #pattern = '\s%s<.*?</ul>' % episode
                pattern = 'data-num="%sx%s"(.*?)</div' % (season, episode)
                isMatch, sHtmlContent = cParser.parseSingleResult(sHtmlContent, pattern)
                if not isMatch: return sources

                isMatch, aResult = cParser().parse(sHtmlContent, 'link="([^"]+)".*?">([^<]+)')    # link="([^"]+)">([^<]+)
                if not isMatch: return sources
                for sUrl, sName in aResult:
                    if 'railer' in sName or 'youtube'in sUrl or 'vod'in sUrl: continue
                    if sUrl.startswith('/'): sUrl = re.sub('//', 'https://', sUrl)
                    if sUrl.startswith('/'): sUrl = 'https:/' + sUrl
                    isBlocked, hoster, url, prioHoster = isBlockedHoster(sUrl)
                    if isBlocked: continue
                    if url: self.sources.append({'source': hoster, 'quality': quality, 'language': 'de', 'url': url, 'direct': True, 'prioHoster': prioHoster})

            return self.sources
        except:
            return self.sources

    def resolve(self, url):
        try:
            return url
        except:
            return

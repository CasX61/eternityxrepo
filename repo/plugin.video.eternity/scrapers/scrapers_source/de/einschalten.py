
# einschalten
# 2024-09-05
# edit 2025-06-15

from resources.lib.utils import isBlockedHoster
import json
from resources.lib.requestHandler import cRequestHandler
from scrapers.modules.tools import cParser
from resources.lib.control import urljoin, getSetting, urlparse
from scrapers.modules import cleantitle, dom_parser

SITE_IDENTIFIER = 'einschalten'
SITE_DOMAIN = 'einschalten.in'
SITE_NAME = SITE_IDENTIFIER.upper()

class source:
    def __init__(self):
        self.priority = 1
        self.language = ['de']
        self.domain = getSetting('provider.' + SITE_IDENTIFIER + '.domain', SITE_DOMAIN)
        self.base_link = 'https://' + self.domain

        self.search_link = self.base_link + '/search?query=%s'
        self.sources = []

    def run(self, titles, year, season=0, episode=0, imdb='', hostDict=None):
        if season > 0: return  self.sources
        try:
            import xbmc

            # Filter out 'none' titles
            titles = [t for t in titles if t and str(t).lower() != 'none']
            xbmc.log('[EINSCHALTEN] Starting search - Year: %s, Titles: %s' % (year, list(titles)[:2]), xbmc.LOGINFO)

            t = [cleantitle.get(i) for i in set(titles) if i]
            links = []
            for sSearchText in set(titles):
                URL_SEARCH = self.search_link % sSearchText
                oRequest = cRequestHandler(URL_SEARCH, caching=True)
                oRequest.cacheTime = 60 * 60 #* 48  # 48 Stunden
                sHtmlContent = oRequest.request()
                # pattern = 'class="group.*?href="([^"]+).*?title="([^"]+).*?alt=.*?(\d+)'
                pattern = 'class="group.*?title="([^"]+).*?href="([^"]+).*?span>(\d+)'
                isMatch, aResult = cParser.parse(sHtmlContent, pattern)
                if not isMatch:
                    xbmc.log('[EINSCHALTEN] No matches found for: %s' % sSearchText, xbmc.LOGINFO)
                    continue

                xbmc.log('[EINSCHALTEN] Found %d results for: %s' % (len(aResult), sSearchText), xbmc.LOGINFO)
                for sName, sUrl, sYear in aResult:
                    xbmc.log('[EINSCHALTEN] Checking: %s (%s) - URL: %s' % (sName, sYear, sUrl), xbmc.LOGINFO)

                    # Convert year to int for comparison
                    try:
                        year_int = int(sYear)
                        xbmc.log('[EINSCHALTEN] Year comparison: %s (type: %s) vs %s (type: %s)' % (year, type(year).__name__, year_int, type(year_int).__name__), xbmc.LOGINFO)
                    except:
                        xbmc.log('[EINSCHALTEN] Failed to convert year: %s' % sYear, xbmc.LOGERROR)
                        continue

                    if int(year) != year_int:
                        xbmc.log('[EINSCHALTEN] Year mismatch: %s != %s' % (year, year_int), xbmc.LOGINFO)
                        continue

                    # More flexible title matching
                    clean_found = cleantitle.get(sName)
                    xbmc.log('[EINSCHALTEN] Clean found: "%s"' % clean_found, xbmc.LOGINFO)
                    xbmc.log('[EINSCHALTEN] Clean search titles: %s' % str(t[:3]), xbmc.LOGINFO)

                    matched = False
                    for clean_search in t:
                        # Check if titles match (either direction)
                        if clean_found == clean_search or clean_search in clean_found or clean_found in clean_search:
                            xbmc.log('[EINSCHALTEN] Title MATCH! "%s" matches "%s"' % (clean_found, clean_search), xbmc.LOGINFO)
                            matched = True
                            break

                    if matched and sUrl not in links:
                        xbmc.log('[EINSCHALTEN] MATCH: %s (%s) -> %s' % (sName, sYear, sUrl), xbmc.LOGINFO)
                        links.append(sUrl)
                        break
                    elif not matched:
                        xbmc.log('[EINSCHALTEN] No title match for: %s' % sName, xbmc.LOGINFO)

                if len(links) > 0: break

            if len(links) == 0:
                xbmc.log('[EINSCHALTEN] No matching links found', xbmc.LOGINFO)
                return self.sources

            for link in set(links):
                sUrl = self.base_link + '/api' + link + '/watch'
                xbmc.log('[EINSCHALTEN] Fetching streams from: %s' % sUrl, xbmc.LOGINFO)
                sHtmlContent = cRequestHandler(sUrl).request()
                if not 'streamUrl' in sHtmlContent:
                    xbmc.log('[EINSCHALTEN] No streamUrl in response: %s' % sHtmlContent[:100], xbmc.LOGINFO)
                    continue
                jResult = json.loads(sHtmlContent)
                releaseName = jResult['releaseName']
                if '720p' in releaseName: quality = '720p'
                elif '1080p' in releaseName: quality = '1080p'
                else: quality = 'SD'
                streamUrl = jResult['streamUrl']
                xbmc.log('[EINSCHALTEN] Stream found - Release: %s, URL: %s' % (releaseName, streamUrl[:50]), xbmc.LOGINFO)
                isBlocked, hoster, url, prioHoster = isBlockedHoster(streamUrl)
                if isBlocked:
                    xbmc.log('[EINSCHALTEN] Hoster blocked: %s' % hoster, xbmc.LOGINFO)
                    continue
                if url:
                    xbmc.log('[EINSCHALTEN] Adding source - Hoster: %s, Quality: %s' % (hoster, quality), xbmc.LOGINFO)
                    self.sources.append({'source': hoster, 'quality': quality, 'language': 'de', 'url': url, 'direct': True, 'prioHoster': prioHoster})

            return self.sources
        except Exception as e:
            import xbmc
            xbmc.log('[EINSCHALTEN] Error: %s' % str(e), xbmc.LOGERROR)
            return self.sources

    def resolve(self, url):
        return  url


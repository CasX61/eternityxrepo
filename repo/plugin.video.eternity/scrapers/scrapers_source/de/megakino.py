
# megakino
# 2022-07-19
# edit 2025-01-30 - Neuer Suchmechanismus basierend auf funktionierendem Scraper

from resources.lib.utils import isBlockedHoster
import re
import requests
import time
from scrapers.modules.tools import cParser
from scrapers.modules import cleantitle
from resources.lib.control import getSetting
import xbmc

SITE_IDENTIFIER = 'megakino'
SITE_DOMAIN = 'megakino1.com'
SITE_NAME = SITE_IDENTIFIER.upper()

class source:
    def __init__(self):
        self.priority = 1
        self.language = ['de']
        self.domain = getSetting('provider.' + SITE_IDENTIFIER + '.domain', SITE_DOMAIN)
        self.base_link = 'https://' + self.domain
        self.search_link = self.base_link + '/index.php?do=search&subaction=search&story=%s'
        self.sources = []
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'de-DE,de;q=0.9,en;q=0.8',
            'Referer': self.base_link
        }

    def get_html(self, url):
        """Fetch HTML with automatic token handling"""
        try:
            session = requests.Session()
            r = session.get(url, headers=self.headers, timeout=10)
            html = r.text

            # Check if token is needed
            if html and 'yg=token' in html:
                xbmc.log('MEGAKINO: Token required, fetching...', xbmc.LOGINFO)
                token_url = self.base_link + '/index.php?yg=token'
                token_headers = self.headers.copy()
                token_headers.update({'X-Requested-With': 'XMLHttpRequest', 'Referer': url})
                session.get(token_url, headers=token_headers, timeout=10)
                time.sleep(0.5)
                r = session.get(url, headers=self.headers, timeout=10)
                html = r.text

            return html if html and len(html) > 500 else ""
        except Exception as e:
            xbmc.log('MEGAKINO: get_html error: %s' % str(e), xbmc.LOGERROR)
            return ""

    def run(self, titles, year, season=0, episode=0, imdb='', hostDict=None):
        self.sources = []
        try:
            xbmc.log('MEGAKINO: Starting search - titles=%s, year=%s, season=%s, episode=%s' %
                     (titles, year, season, episode), xbmc.LOGINFO)

            t = [cleantitle.get(i) for i in set(titles) if i]

            for sSearchText in titles:
                search_url = self.search_link % sSearchText
                xbmc.log('MEGAKINO: Search URL: %s' % search_url, xbmc.LOGINFO)

                sHtmlContent = self.get_html(search_url)
                if not sHtmlContent:
                    xbmc.log('MEGAKINO: Empty response', xbmc.LOGWARNING)
                    continue

                xbmc.log('MEGAKINO: Got response, length=%d' % len(sHtmlContent), xbmc.LOGINFO)

                # Simple pattern without year (like working scraper)
                pattern = r'<a class="poster grid-item[^>]*href="([^"]+)"[^>]*>.*?alt="([^"]+)"'
                isMatch, aResult = cParser.parse(sHtmlContent, pattern)

                if not isMatch:
                    xbmc.log('MEGAKINO: No matches for pattern', xbmc.LOGINFO)
                    continue

                xbmc.log('MEGAKINO: Found %d results' % len(aResult), xbmc.LOGINFO)

                for sUrl, sName in aResult:
                    if not sUrl.startswith('http'):
                        sUrl = self.base_link + sUrl

                    clean_name = cleantitle.get(sName)
                    xbmc.log('MEGAKINO: Checking "%s" (clean: %s)' % (sName, clean_name), xbmc.LOGINFO)

                    # Match title
                    if clean_name in t or any(cleantitle.get(x) in clean_name for x in titles):
                        xbmc.log('MEGAKINO: MATCH! Getting sources from: %s' % sUrl, xbmc.LOGINFO)
                        self.get_sources(sUrl, year, season, episode)
                        if self.sources:
                            return self.sources

            return self.sources
        except Exception as e:
            xbmc.log('MEGAKINO: run() error: %s' % str(e), xbmc.LOGERROR)
            return self.sources

    def get_sources(self, url, year, season, episode):
        """Extract stream sources from movie/series page"""
        try:
            html = self.get_html(url)
            if not html:
                return

            # Determine quality
            quality = '720p'
            if '1080' in html:
                quality = '1080p'

            xbmc.log('MEGAKINO: Getting sources, quality=%s, season=%s, episode=%s' %
                     (quality, season, episode), xbmc.LOGINFO)

            if season > 0:
                # Series: Find episode select
                pattern = r'<select[^>]*id="ep%s"[^>]*>(.*?)</select>' % str(episode)
                isMatch, sContainer = cParser.parseSingleResult(html, pattern)

                if isMatch:
                    isMatch, links = cParser.parse(sContainer, 'value="([^"]+)"')
                    xbmc.log('MEGAKINO: Found %d episode links' % (len(links) if isMatch else 0), xbmc.LOGINFO)
                else:
                    xbmc.log('MEGAKINO: No episode select found for ep%s' % episode, xbmc.LOGINFO)
                    return
            else:
                # Movie: Find iframes
                pattern = r'<iframe[^>]*src="([^"]+)"'
                isMatch, links = cParser.parse(html, pattern)

                if not isMatch:
                    # Try data-src
                    pattern = r'<iframe[^>]*data-src="([^"]+)"'
                    isMatch, links = cParser.parse(html, pattern)

                xbmc.log('MEGAKINO: Found %d iframe links' % (len(links) if isMatch else 0), xbmc.LOGINFO)

            if not isMatch:
                return

            for sUrl in links:
                # Skip YouTube
                if 'youtube' in sUrl.lower():
                    continue

                # Fix URL
                if sUrl.startswith('//'):
                    sUrl = 'https:' + sUrl
                elif sUrl.startswith('/'):
                    sUrl = self.base_link + sUrl

                xbmc.log('MEGAKINO: Checking URL: %s' % sUrl[:60], xbmc.LOGINFO)

                isBlocked, hoster, resolved_url, prioHoster = isBlockedHoster(sUrl)

                if isBlocked:
                    xbmc.log('MEGAKINO: Blocked: %s' % hoster, xbmc.LOGDEBUG)
                    continue

                if resolved_url:
                    xbmc.log('MEGAKINO: Adding source: %s (%s)' % (hoster, quality), xbmc.LOGINFO)
                    self.sources.append({
                        'source': hoster,
                        'quality': quality,
                        'language': 'de',
                        'url': resolved_url,
                        'direct': True,
                        'prioHoster': prioHoster
                    })

            xbmc.log('MEGAKINO: Total sources: %d' % len(self.sources), xbmc.LOGINFO)

        except Exception as e:
            xbmc.log('MEGAKINO: get_sources() error: %s' % str(e), xbmc.LOGERROR)

    def resolve(self, url):
        return url

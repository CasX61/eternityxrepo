

# edit 2025-02-12

import re
import datetime
from resources.lib.control import  getSetting, urljoin, setSetting
from resources.lib.requestHandler import cRequestHandler
from scrapers.modules import cleantitle, dom_parser
from resources.lib.utils import isBlockedHoster

SITE_IDENTIFIER = 'aniworld'
SITE_DOMAIN = 'aniworld.to' # https://www.aniworld.info/
SITE_NAME = SITE_IDENTIFIER.upper()

date = datetime.date.today()
currentyear = int(date.strftime("%Y"))

class source:
    def __init__(self):
        self.priority = 1
        self.language = ['de']
        self.domain = getSetting('provider.' + SITE_IDENTIFIER + '.domain', SITE_DOMAIN)
        self.base_link = 'https://' + self.domain

        self.search_link = '/animes'
        self.login = getSetting('aniworld.user')
        self.password = getSetting('aniworld.pass')
        self.sources = []

    def run(self, titles, year, season=0, episode=0, imdb='', hostDict=None):
        # Login is optional for aniworld
        # if self.login == '' or self.password == '':
        #     import xbmcgui, xbmcaddon
        #     AddonName = xbmcaddon.Addon().getAddonInfo('name')
        #     xbmcgui.Dialog().ok(AddonName,
        #                         "In den Einstellungen die Kontodaten (Login) für %s eintragen / überprüfen\nBis dahin wird %s von der Suche ausgeschlossen. Es erfolgt kein erneuter Hinweis!" % (
        #                         SITE_NAME, SITE_NAME))
        #     setSetting('provider.' + SITE_IDENTIFIER, 'false')
        #     return []

        sources = []

        # For movies (season=0), treat as season 1 episode 1
        # Aniworld lists anime movies as "Staffel 1 Episode 1"
        if season == 0:
            season = 1
            episode = 1

        try:
            # Build URL directly from title
            # Format: /anime/stream/one-punch-man/staffel-1/episode-1
            from scrapers.modules import cleantitle
            import xbmc

            xbmc.log('ANIWORLD: Received %d titles to try' % len(titles), xbmc.LOGINFO)
            xbmc.log('ANIWORLD: Year = %s' % year, xbmc.LOGINFO)

            for title in titles:
                if not title:
                    continue

                # Clean title for URL (replace spaces with dashes, lowercase, remove special chars)
                title_clean = title.lower()
                title_clean = re.sub(r'[^a-z0-9\s-]', '', title_clean)
                title_clean = re.sub(r'\s+', '-', title_clean)
                title_clean = re.sub(r'-+', '-', title_clean)
                title_clean = title_clean.strip('-')

                # OPTION 1: Jahr-Matching - Try multiple URL variants
                urls_to_try = []

                # 1. First try: Title with year (for remakes like "Berserk (1997)")
                if year:
                    title_with_year = '%s-%s' % (title_clean, year)
                    urls_to_try.append('/anime/stream/%s/staffel-%d/episode-%d' % (title_with_year, int(season), int(episode)))

                # 2. Second try: Title without year (most common case)
                urls_to_try.append('/anime/stream/%s/staffel-%d/episode-%d' % (title_clean, int(season), int(episode)))

                xbmc.log('ANIWORLD: Will try %d URL variants' % len(urls_to_try), xbmc.LOGINFO)

                # Try each URL variant
                for url in urls_to_try:
                    xbmc.log('ANIWORLD: Trying URL: %s' % url, xbmc.LOGINFO)

                    # Try to scrape this URL
                    result = self.run2(url, year, season=season, episode=episode, hostDict=hostDict, imdb=imdb)
                    if result and len(result) > 0:
                        xbmc.log('ANIWORLD: Found %d sources with URL: %s' % (len(result), url), xbmc.LOGINFO)
                        # Found sources, stop searching
                        break
                    else:
                        xbmc.log('ANIWORLD: No sources found for URL: %s' % url, xbmc.LOGINFO)

                # If sources found, stop trying other titles
                if self.sources and len(self.sources) > 0:
                    break

        except Exception as e:
            import xbmc
            xbmc.log('ANIWORLD ERROR: %s' % str(e), xbmc.LOGERROR)
            return sources

        return self.sources

    def run2(self, url, year, season=0, episode=0, hostDict=None, imdb=None):
        try:
            import xbmc
            # URL is already built in run(), just add base if needed
            if not url.startswith('http'):
                url = urljoin(self.base_link, url)

            xbmc.log('ANIWORLD run2: Fetching %s' % url, xbmc.LOGINFO)
            sHtmlContent = cRequestHandler(url).request()
            xbmc.log('ANIWORLD run2: Got response, length=%d' % len(sHtmlContent), xbmc.LOGINFO)

            # Optional IMDB check (only if IMDB is provided)
            if imdb:
                try:
                    a = dom_parser.parse_dom(sHtmlContent, 'a', attrs={'class': 'imdb-link'}, req='href')
                    if a and len(a) > 0:
                        foundImdb = a[0].attrs.get("data-imdb", '')
                        if foundImdb and foundImdb != imdb:
                            xbmc.log('ANIWORLD run2: IMDB mismatch, skipping', xbmc.LOGINFO)
                            return self.sources
                except:
                    pass


            r = dom_parser.parse_dom(sHtmlContent, 'div', attrs={'class': 'hosterSiteVideo'})
            xbmc.log('ANIWORLD run2: Found %d hosterSiteVideo divs' % len(r), xbmc.LOGINFO)
            #r = dom_parser.parse_dom(r, 'li', attrs={'data-lang-key': re.compile('[1|2|3]')})
            #r = dom_parser.parse_dom(r, 'li', attrs={'data-lang-key': re.compile('[1]')}) #- only german
            r = dom_parser.parse_dom(r, 'li', attrs={'data-lang-key': re.compile('[1|3]')})  #- only german and subbed DE
            xbmc.log('ANIWORLD run2: Found %d hoster entries' % len(r), xbmc.LOGINFO)

            r = [(i.attrs['data-link-target'], dom_parser.parse_dom(i, 'h4'),
                  'Untertitel DE' if i.attrs['data-lang-key'] == '3' else '' if i.attrs['data-lang-key'] == '1' else 'Untertitel EN' if i.attrs['data-lang-key'] == '2' else '') for i
                 in r]

            r = [(i[0], re.sub('\s(.*)', '', i[1][0].content), 'HD' if 'hd' in i[1][0][1].lower() else 'SD', i[2]) for i in r]

            for link, host, quality, info in r:
                quality = 'HD'  # temp
                isBlocked, hoster, url, prioHoster = isBlockedHoster(host, isResolve=False)
                if isBlocked:
                    xbmc.log('ANIWORLD run2: Hoster %s is blocked, skipping' % host, xbmc.LOGINFO)
                    continue
                xbmc.log('ANIWORLD run2: Adding source: %s' % host, xbmc.LOGINFO)
                self.sources.append(
                    {'source': host, 'quality': quality, 'language': 'de', 'url': link, 'info': info, 'direct': False, 'priority': self.priority, 'prioHoster': prioHoster})

            xbmc.log('ANIWORLD run2: Total sources found: %d' % len(self.sources), xbmc.LOGINFO)
            return self.sources
        except Exception as e:
            import xbmc
            xbmc.log('ANIWORLD run2 ERROR: %s' % str(e), xbmc.LOGERROR)
            import traceback
            xbmc.log('ANIWORLD run2 TRACEBACK: %s' % traceback.format_exc(), xbmc.LOGERROR)
            return self.sources

    def resolve(self, url):
        try:
            import xbmc
            xbmc.log('ANIWORLD resolve: Starting to resolve URL: %s' % url, xbmc.LOGINFO)

            # Login if credentials are provided
            if self.login and self.password:
                xbmc.log('ANIWORLD resolve: Logging in with credentials', xbmc.LOGINFO)
                URL_LOGIN = urljoin(self.base_link, '/login')
                Handler = cRequestHandler(URL_LOGIN, caching=False)
                Handler.addHeaderEntry('Upgrade-Insecure-Requests', '1')
                Handler.addHeaderEntry('Referer', self.base_link)
                Handler.addParameters('email', self.login)
                Handler.addParameters('password', self.password)
                Handler.request()
            else:
                xbmc.log('ANIWORLD resolve: No login credentials, proceeding without login', xbmc.LOGINFO)

            # Resolve the redirect URL
            full_url = self.base_link + url
            xbmc.log('ANIWORLD resolve: Requesting redirect from: %s' % full_url, xbmc.LOGINFO)
            Request = cRequestHandler(full_url, caching=False)
            Request.addHeaderEntry('Referer', self.base_link)
            Request.addHeaderEntry('Upgrade-Insecure-Requests', '1')
            Request.request()
            resolved_url = Request.getRealUrl()
            xbmc.log('ANIWORLD resolve: Got resolved URL: %s' % resolved_url, xbmc.LOGINFO)

            if self.base_link in resolved_url:
                xbmc.log('ANIWORLD resolve: URL still contains base_link - protected content', xbmc.LOGWARNING)
                import xbmcgui, xbmcaddon
                AddonName = xbmcaddon.Addon().getAddonInfo('name')
                xbmcgui.Dialog().ok(AddonName, "- Geschützter Link - \nIn den Einstellungen die Kontodaten (Login) für Aniworld eintragen")
                return
            else:
                xbmc.log('ANIWORLD resolve: Successfully resolved to external URL', xbmc.LOGINFO)
                return resolved_url

        except Exception as e:
            import xbmc, traceback
            xbmc.log('ANIWORLD resolve ERROR: %s' % str(e), xbmc.LOGERROR)
            xbmc.log('ANIWORLD resolve TRACEBACK: %s' % traceback.format_exc(), xbmc.LOGERROR)
            return


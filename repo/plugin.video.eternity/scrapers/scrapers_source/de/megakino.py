
# megakino
# 2022-07-19
# edit 2024-12-14

from resources.lib.utils import isBlockedHoster
import re
from scrapers.modules.tools import cParser  # re - alternative
from resources.lib.requestHandler import cRequestHandler
from scrapers.modules import cleantitle, dom_parser
from resources.lib.control import getSetting, quote, quote_plus
import urllib.request
import urllib.parse
from http.cookiejar import CookieJar

SITE_IDENTIFIER = 'megakino'
SITE_DOMAIN = 'w1.megakino.do'
SITE_NAME = SITE_IDENTIFIER.upper()

class source:
    def __init__(self):
        self.priority = 1
        self.language = ['de']
        self.domain = getSetting('provider.' + SITE_IDENTIFIER + '.domain', SITE_DOMAIN)
        self.base_link = 'https://' + self.domain

        self.sources = []

    def run(self, titles, year, season=0, episode=0, imdb='', hostDict=None):
        sources = []
        try:
            import xbmc

            # Convert year to int if it's a string
            if isinstance(year, str):
                year = int(year) if year else 0

            xbmc.log('MEGAKINO: Starting search - Year: %s (type: %s), Season: %s, Episode: %s' % (year, type(year).__name__, season, episode), xbmc.LOGINFO)

            # STEP 1: Get authentication token using urllib with cookie jar
            xbmc.log('MEGAKINO: Getting authentication token', xbmc.LOGINFO)

            # Create cookie jar that persists across requests
            cookie_jar = CookieJar()
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
            opener.addheaders = [('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')]

            # Get token
            token_url = self.base_link + '/index.php?yg=token'
            opener.open(token_url, timeout=10)
            xbmc.log('MEGAKINO: Token retrieved, cookies: %d' % len(cookie_jar), xbmc.LOGINFO)

            t = set([cleantitle.get(i) for i in set(titles) if i])
            links = []
            for sSearchText in titles:
                try:
                    xbmc.log('MEGAKINO: Searching for: %s' % sSearchText, xbmc.LOGINFO)

                    # STEP 2: Search with cookies using POST (Megakino requires POST for search)
                    search_url = self.base_link + '/index.php?do=search'
                    post_data = {
                        'do': 'search',
                        'subaction': 'search',
                        'story': sSearchText,
                        'search_start': '0',
                        'full_search': '0',
                        'result_from': '1'
                    }
                    post_data_encoded = urllib.parse.urlencode(post_data).encode('utf-8')
                    response = opener.open(search_url, post_data_encoded, timeout=10)
                    sHtmlContent = response.read().decode('utf-8', errors='ignore')

                    xbmc.log('MEGAKINO: Got search response, length=%d' % len(sHtmlContent), xbmc.LOGINFO)

                    # Check if dle-content exists
                    dle_content = dom_parser.parse_dom(sHtmlContent, 'div', attrs={'id': 'dle-content'})
                    if not dle_content:
                        xbmc.log('MEGAKINO: No dle-content found, token auth may have failed', xbmc.LOGERROR)
                        continue
                    r = dle_content[0].content
                    #a = dom_parser.parse_dom(r, 'a')
                    #pattern = '<a\s+class=[^>]*href="([^"]+)">.*?alt="([^"]+)">\s*<div\s+class="poster__label">([^<]+).*?<li>.*?(\d{4}).*?</a>'
                    if season != 0:pattern = '<a\s+class="poster[^>]*href="([^"]+).*?alt="([^"]+)'
                    else: pattern = '<a\s+class="poster[^>]*href="([^"]+).*?alt="([^"]+)">.*?<li>.*?(\d{4}).*?</a>'
                    isMatch, aResult = cParser.parse(r, pattern)
                    if not isMatch:
                        xbmc.log('MEGAKINO: No matches found for pattern', xbmc.LOGINFO)
                        continue

                    xbmc.log('MEGAKINO: Found %d results' % len(aResult), xbmc.LOGINFO)

                    if season == 0:
                        for sUrl, sName, sYear in aResult:  # sUrl, sName, sQuality, sYear
                            xbmc.log('MEGAKINO: Checking movie - Title: "%s", Year: "%s" (type: %s), looking for %s (type: %s)' % (sName, sYear, type(sYear).__name__, year, type(year).__name__), xbmc.LOGINFO)

                            try:
                                year_int = int(sYear)
                                year_match = (year_int == year)
                                xbmc.log('MEGAKINO: Year comparison - int(%s) == %s: %s' % (sYear, year, year_match), xbmc.LOGINFO)

                                if not year_match:
                                    xbmc.log('MEGAKINO: Year mismatch, skipping', xbmc.LOGINFO)
                                    continue
                            except Exception as e:
                                xbmc.log('MEGAKINO: Error converting year to int: %s' % str(e), xbmc.LOGERROR)
                                continue

                            clean_name = cleantitle.get(sName)
                            xbmc.log('MEGAKINO: Clean title: "%s", checking against: %s' % (clean_name, list(t)[:3]), xbmc.LOGINFO)

                            if clean_name in t:
                                xbmc.log('MEGAKINO: MATCH! Adding to links: %s' % sUrl, xbmc.LOGINFO)
                                links.append({'url': sUrl, 'name': sName, 'quality': 'HD', 'year': sYear})
                                # Break after first match to avoid duplicates with same year
                                break
                            else:
                                xbmc.log('MEGAKINO: Title does not match', xbmc.LOGINFO)

                    elif season > 0:
                        for sUrl, sName in aResult:
                            xbmc.log('MEGAKINO: Checking series - Title: "%s", Season: %s' % (sName, season), xbmc.LOGINFO)

                            sYear = ''
                            title_part = None
                            season_number = None

                            # Check for "- Staffel X" pattern (German)
                            if ' - Staffel ' in sName or ' Staffel ' in sName:
                                # Try "Title - Staffel X" or "Title Staffel X"
                                if ' - Staffel ' in sName:
                                    parts = sName.split(' - Staffel ')
                                else:
                                    parts = sName.split(' Staffel ')

                                if len(parts) == 2:
                                    title_part = parts[0].strip()
                                    # Extract season number (could be "1" or "1 kostenlos anschauen" etc)
                                    season_str = parts[1].split()[0] if parts[1].split() else ''
                                    try:
                                        season_number = int(season_str)
                                    except:
                                        pass

                            # Check for "- SX" pattern (English)
                            elif '- S' in sName:
                                parts = sName.split('- S')
                                if len(parts) == 2:
                                    title_part = parts[0].strip()
                                    season_str = parts[1].split()[0] if parts[1].split() else ''
                                    try:
                                        season_number = int(season_str.replace('S', '').replace('s', ''))
                                    except:
                                        pass

                            if title_part and season_number:
                                clean_name = cleantitle.get(title_part)
                                xbmc.log('MEGAKINO: Series parsed - Title: "%s" (clean: %s), Season: %s' % (title_part, clean_name, season_number), xbmc.LOGINFO)

                                if clean_name in t and season_number == season:
                                    xbmc.log('MEGAKINO: MATCH! Adding series to links: %s' % sUrl, xbmc.LOGINFO)
                                    links.append({'url': sUrl, 'name': title_part, 'quality': 'HD', 'year': sYear})
                                    break  # Stop after first match
                                else:
                                    xbmc.log('MEGAKINO: Series does not match (title in t: %s, season match: %s)' % (clean_name in t, season_number == season), xbmc.LOGINFO)
                            else:
                                xbmc.log('MEGAKINO: Could not parse season info from title', xbmc.LOGINFO)

                    if len(links) == 0 and season == 0:
                        for sUrl, sName, sYear in aResult:
                            if not int(sYear) == year: continue
                            #if '1080' in sQuality: sQuality = '1080p'
                            for a in t:
                                if any([a in cleantitle.get(sName)]):
                                    links.append({'url': sUrl, 'name': sName, 'quality': 'HD', 'year': sYear})
                                    break


                    if len(links) > 0:
                        xbmc.log('MEGAKINO: Found %d matching links, breaking search loop' % len(links), xbmc.LOGINFO)
                        break

                except:
                    continue

            if len(links) == 0:
                xbmc.log('MEGAKINO: No matching links found, returning empty', xbmc.LOGINFO)
                return sources

            xbmc.log('MEGAKINO: Processing %d links for streams' % len(links), xbmc.LOGINFO)

            for link in links:
                xbmc.log('MEGAKINO: Fetching streams from: %s' % link['url'], xbmc.LOGINFO)

                # Use opener with cookies to fetch film/series page
                response = opener.open(link['url'], timeout=10)
                sHtmlContent = response.read().decode('utf-8', errors='ignore')

                if season > 0:
                    self.quality = link['quality']
                    xbmc.log('MEGAKINO: Parsing episode %s from series page' % episode, xbmc.LOGINFO)

                    # Log first 1000 chars to see structure
                    xbmc.log('MEGAKINO: HTML preview (first 1000 chars): %s' % sHtmlContent[:1000], xbmc.LOGINFO)

                    pattern = '<select\s+name="pmovie__select-items"\s+class="[^"]+"\s+style="[^"]+"\s+id="ep%s">\s*(.*?)\s*</select>' % str(episode)
                    xbmc.log('MEGAKINO: Looking for episode select with pattern for ep%s' % episode, xbmc.LOGINFO)

                    isMatch, sHtmlContent = cParser.parseSingleResult(sHtmlContent, pattern)
                    if not isMatch:
                        xbmc.log('MEGAKINO: No episode select found for ep%s' % episode, xbmc.LOGINFO)
                        # Try to find any episode selects to see what's available
                        all_selects = re.findall(r'<select[^>]*id="(ep\d+)"', sHtmlContent)
                        xbmc.log('MEGAKINO: Found episode selects: %s' % all_selects, xbmc.LOGINFO)
                        return sources

                    xbmc.log('MEGAKINO: Found episode select, parsing stream URLs', xbmc.LOGINFO)
                    isMatch, aResult = cParser().parse(sHtmlContent, 'value="([^"]+)')
                    if not isMatch:
                        xbmc.log('MEGAKINO: No stream URLs found in episode select', xbmc.LOGINFO)
                        return sources

                    xbmc.log('MEGAKINO: Found %d stream URLs for episode %s' % (len(aResult), episode), xbmc.LOGINFO)

                    # Process episode streams
                    for sUrl in aResult:
                        xbmc.log('MEGAKINO: Processing episode stream URL: %s' % sUrl, xbmc.LOGINFO)

                        if sUrl.startswith('/'):
                            sUrl = re.sub('//', 'https://', sUrl)
                        if sUrl.startswith('/'):
                            sUrl = 'https:/' + sUrl

                        xbmc.log('MEGAKINO: Checking hoster for URL: %s' % sUrl, xbmc.LOGINFO)
                        isBlocked, hoster, url, prioHoster = isBlockedHoster(sUrl)

                        if isBlocked:
                            xbmc.log('MEGAKINO: Stream blocked - Hoster: %s, URL: %s' % (hoster, sUrl), xbmc.LOGINFO)
                            continue

                        if url:
                            xbmc.log('MEGAKINO: Adding stream - Hoster: %s, Quality: %s' % (hoster, self.quality), xbmc.LOGINFO)
                            self.sources.append({
                                'source': hoster,
                                'quality': self.quality,
                                'language': 'de',
                                'url': url,
                                'direct': True,
                                'prioHoster': prioHoster
                            })

                    xbmc.log('MEGAKINO: Total sources after episode processing: %d' % len(self.sources), xbmc.LOGINFO)

                else:
                    pattern = 'poster__label">([^/|<]+)'
                    isMatch, sQuality = cParser.parseSingleResult(sHtmlContent, pattern)
                    if '1080' in sQuality: sQuality = '1080p'
                    quality = sQuality if isMatch else link['quality']

                    # UPDATED 2025-10-17: Megakino now uses data-src instead of src for iframes
                    # Try both data-src and src
                    pattern = '<iframe.*?(?:data-src|src)=["\']([^"\']+)["\']'
                    isMatch, aResult = cParser().parse(sHtmlContent, pattern)
                    if not isMatch: return sources
                    for sUrl in aResult:
                        # Skip YouTube trailer links
                        if 'youtube.com' in sUrl or 'youtu.be' in sUrl:
                            xbmc.log('MEGAKINO: Skipping YouTube trailer: %s' % sUrl, xbmc.LOGINFO)
                            continue

                        if sUrl.startswith('/'): sUrl = re.sub('//', 'https://', sUrl)
                        if sUrl.startswith('/'): sUrl = 'https:/' + sUrl

                        xbmc.log('MEGAKINO: Checking stream URL: %s' % sUrl, xbmc.LOGINFO)
                        isBlocked, hoster, url, prioHoster = isBlockedHoster(sUrl)
                        if isBlocked:
                            xbmc.log('MEGAKINO: Hoster blocked: %s' % hoster, xbmc.LOGINFO)
                            continue
                        if url:
                            xbmc.log('MEGAKINO: Adding source - Hoster: %s, Quality: %s, URL: %s' % (hoster, quality, url[:50]), xbmc.LOGINFO)
                            self.sources.append({'source': hoster, 'quality': quality, 'language': 'de', 'url': url, 'direct': True, 'prioHoster': prioHoster})

            return self.sources
        except:
            return self.sources


    def resolve(self, url):
        try:
            return url
        except:
            return
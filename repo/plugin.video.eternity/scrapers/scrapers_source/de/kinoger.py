

# edit 2025-10-17 - Komplett neu implementiert (neue Website-Struktur)
# edit 2025-11-21 - Fixed year/None matching, added logging

from resources.lib.utils import isBlockedHoster
import re, json, requests
from resources.lib.control import getSetting
from resources.lib.requestHandler import cRequestHandler
from scrapers.modules import cleantitle
from resources.lib import log_utils
import xbmc

SITE_IDENTIFIER = 'kinoger'
SITE_DOMAIN = 'kinoger.com'
SITE_NAME = SITE_IDENTIFIER.upper()

class source:
    def __init__(self):
        self.priority = 1
        self.language = ['de']
        self.domain = getSetting('provider.' + SITE_IDENTIFIER + '.domain', SITE_DOMAIN)
        self.base_link = 'https://' + self.domain
        self.search = self.base_link + '/index.php?do=search&subaction=search&search_start=1&full_search=0&result_from=1&titleonly=3&story=%s'
        self.sources = []

    def run(self, titles, year, season=0, episode=0, imdb='', hostDict=None):
        """
        Main scraper method - searches for title and extracts stream links
        """
        try:
            # Convert year to int for comparison
            if year:
                try:
                    year = int(year)
                except (ValueError, TypeError):
                    year = None

            xbmc.log('[KINOGER] Searching: titles=%s, year=%s, season=%s, episode=%s, imdb=%s' %
                     (titles, year, season, episode, imdb), xbmc.LOGINFO)

            # Step 1: Search for the title and get the stream page URL
            url = self._search(titles, year, season)
            if not url:
                xbmc.log('[KINOGER] No search results found for: %s' % titles[0], xbmc.LOGINFO)
                return []

            xbmc.log('[KINOGER] Found URL: %s' % url, xbmc.LOGINFO)

            # Step 2: Fetch the stream page
            oRequest = cRequestHandler(url, caching=False)
            sHtmlContent = oRequest.request()

            # Step 3: Extract qualities
            qualities = re.findall(r'title="Stream\s*(.+?)"', sHtmlContent)
            xbmc.log('[KINOGER] Found %d quality labels' % len(qualities), xbmc.LOGINFO)

            # Step 4: Extract player links (pw.show, fsst.show, go.show, ollhd.show)
            # Pattern: .show(number, [[links]], optional_param)
            player_matches = re.findall(r'(\w+)\.show\([^,]+,(\[\[.+?\]\])(?:,[^)]+)?\)', sHtmlContent)

            if not player_matches:
                xbmc.log('[KINOGER] No player links found!', xbmc.LOGWARNING)
                return []

            xbmc.log('[KINOGER] Found %d player groups' % len(player_matches), xbmc.LOGINFO)

            # Step 5: Parse each player group
            sources = []
            for idx, (player_name, links_str) in enumerate(player_matches):
                try:
                    # Quality for this player (matches index)
                    quality = qualities[idx] if idx < len(qualities) else 'SD'
                    quality = self._normalize_quality(quality)

                    # Parse the JavaScript array
                    # Format: [['link1',' link2',' link3']] or [['link1']]
                    links_array = eval(links_str)  # Safe here - it's our regex-extracted data

                    if not links_array or not links_array[0]:
                        continue

                    # Get links from first (and only) array element
                    raw_links = links_array[0]

                    # Handle both single link and multiple links (space-separated)
                    if isinstance(raw_links, list):
                        # Already a list
                        all_links = raw_links
                    else:
                        # Single string or space-separated string
                        all_links = [raw_links]

                    # For series: select the specific episode
                    if season > 0 and episode > 0:
                        # Links are space-separated for episodes
                        episode_links = []
                        for link in all_links:
                            if ' ' in link:
                                # Space-separated episodes
                                episode_links.extend([l.strip() for l in link.split(' ') if l.strip()])
                            else:
                                episode_links.append(link.strip())

                        # Select the specific episode (1-indexed)
                        if episode <= len(episode_links):
                            selected_link = episode_links[episode - 1]
                            xbmc.log('[KINOGER] Selected episode %d/%d: %s' % (episode, len(episode_links), selected_link[:50]), xbmc.LOGINFO)
                        else:
                            xbmc.log('[KINOGER] Episode %d not found (only %d episodes)' % (episode, len(episode_links)), xbmc.LOGWARNING)
                            continue
                    else:
                        # For movies: take first link
                        if isinstance(all_links[0], str):
                            selected_link = all_links[0].strip()
                        else:
                            selected_link = str(all_links[0]).strip()

                    # Clean the link
                    selected_link = selected_link.strip().strip("'\"")

                    if not selected_link or selected_link.startswith('#'):
                        xbmc.log('[KINOGER] Skipping invalid link: %s' % selected_link, xbmc.LOGINFO)
                        continue

                    # Check if hoster is blocked
                    isBlocked, hoster, resolved_url, prioHoster = isBlockedHoster(selected_link, isResolve=False)

                    if isBlocked:
                        xbmc.log('[KINOGER] Hoster blocked: %s' % hoster, xbmc.LOGINFO)
                        continue

                    xbmc.log('[KINOGER] Adding source: %s (%s) - %s' % (hoster, quality, selected_link[:50]), xbmc.LOGINFO)

                    sources.append({
                        'source': hoster,
                        'quality': quality,
                        'language': 'de',
                        'url': selected_link,
                        'direct': False,
                        'priority': self.priority,
                        'prioHoster': prioHoster
                    })

                except Exception as e:
                    xbmc.log('[KINOGER] Error parsing player %d: %s' % (idx, str(e)), xbmc.LOGERROR)
                    continue

            if len(sources) == 0:
                log_utils.log('KINOGER: No valid sources found for %s' % titles[0], log_utils.LOGINFO)
            else:
                xbmc.log('[KINOGER] Total sources found: %d' % len(sources), xbmc.LOGINFO)

            self.sources = sources
            return sources

        except Exception as e:
            xbmc.log('[KINOGER] Error in run(): %s' % str(e), xbmc.LOGERROR)
            import traceback
            xbmc.log('[KINOGER] Traceback: %s' % traceback.format_exc(), xbmc.LOGERROR)
            return []

    def _search(self, titles, year, season):
        """
        Search for title and return stream page URL

        HTML structure (real search results):
        <img src=".../postinfo-icon.png" ... /> <a href="https://kinoger.com/stream/19516-conjuring-4-das-letzte-kapitel-2025.html">Conjuring 4: Das letzte Kapitel (2025) Film</a>
        """
        # Clean titles for matching
        t = [cleantitle.get(i) for i in titles if i]

        # Convert year to int for comparison (already converted in run(), but check again)
        if year:
            try:
                year = int(year)
            except (ValueError, TypeError):
                year = None

        xbmc.log('[KINOGER] Search parameters: year=%s, season=%s' % (year, season), xbmc.LOGINFO)

        for title in titles:
            try:
                # Search URL
                sUrl = self.search % title
                xbmc.log('[KINOGER] Search URL: %s' % sUrl, xbmc.LOGINFO)

                oRequest = cRequestHandler(sUrl)
                oRequest.removeBreakLines(False)
                oRequest.removeNewLines(False)
                oRequest.cacheTime = 60 * 60 * 12  # 12h cache
                sHtmlContent = oRequest.request()

                # REAL search results structure: postinfo-icon.png + link
                # Pattern: <img src=".../postinfo-icon.png" ... /> <a href="URL">Title (Year) Film</a>
                pattern = r'postinfo-icon\.png[^<]*<a href="([^"]+)">([^<]+)\((\d{4})\)[^<]*</a>'
                matches = re.findall(pattern, sHtmlContent)

                # Fallback: Try without year in parentheses
                if not matches:
                    pattern_no_year = r'postinfo-icon\.png[^<]*<a href="([^"]+)">([^<]+)</a>'
                    matches_no_year = re.findall(pattern_no_year, sHtmlContent)
                    # Add empty year to match structure
                    matches = [(url, title, '') for url, title in matches_no_year]

                if not matches:
                    xbmc.log('[KINOGER] No results found in HTML', xbmc.LOGINFO)
                    continue

                xbmc.log('[KINOGER] Found %d search results' % len(matches), xbmc.LOGINFO)

                # Filter results
                for url, result_title, result_year in matches:
                    # Remove " Film" or " Serie" suffix from title
                    result_title = result_title.strip()
                    if result_title.endswith(' Film') or result_title.endswith(' Serie'):
                        result_title = result_title.rsplit(' ', 1)[0]

                    result_title_clean = cleantitle.get(result_title)

                    # For series: check if "staffel" is in title
                    if season > 0:
                        if 'staffel' in result_title_clean.lower() and any(k in result_title_clean for k in t):
                            xbmc.log('[KINOGER] ✅ Series match: %s' % result_title, xbmc.LOGINFO)
                            return url
                        else:
                            xbmc.log('[KINOGER] ❌ Series mismatch: %s' % result_title, xbmc.LOGDEBUG)
                    else:
                        # For movies: match title and year

                        # Convert result_year to int for comparison
                        result_year_int = None
                        if result_year:
                            try:
                                result_year_int = int(result_year)
                            except (ValueError, TypeError):
                                result_year_int = None

                        # Title matching
                        title_matches = any(k in result_title_clean for k in t)

                        # Year matching - FIXED: Compare integers!
                        if year and result_year_int:
                            # Both have years - compare as integers
                            year_matches = (year == result_year_int)
                        elif not year:
                            # No year provided - accept any year
                            year_matches = True
                        elif not result_year_int:
                            # No year in result - skip if we're searching with year
                            xbmc.log('[KINOGER] ❌ No year data: %s (skipping)' % result_title, xbmc.LOGINFO)
                            continue
                        else:
                            year_matches = False

                        # Debug logging
                        xbmc.log('[KINOGER] Checking: "%s" (year: %s) - title_match=%s, year_match=%s (searched: %s vs found: %s)' %
                                 (result_title, result_year_int, title_matches, year_matches, year, result_year_int), xbmc.LOGINFO)

                        if title_matches and year_matches:
                            xbmc.log('[KINOGER] ✅ Movie match: %s (%s)' % (result_title, result_year_int), xbmc.LOGINFO)
                            return url
                        else:
                            if not title_matches:
                                xbmc.log('[KINOGER] ❌ Title mismatch: "%s" not in %s' % (result_title_clean, t), xbmc.LOGDEBUG)
                            if not year_matches:
                                xbmc.log('[KINOGER] ❌ Year mismatch: %s != %s' % (result_year_int, year), xbmc.LOGINFO)

            except Exception as e:
                xbmc.log('[KINOGER] Search error: %s' % str(e), xbmc.LOGERROR)
                continue

        return None

    def _normalize_quality(self, quality):
        """
        Normalize quality labels:
        - 'HD+' → '1080p'
        - 'HD' → '720p'
        - Everything else → 'SD'
        """
        quality = quality.strip()
        if quality == 'HD+':
            return '1080p'
        elif quality == 'HD':
            return '720p'
        else:
            return 'SD'

    def resolve(self, url):
        """
        Resolve URL - special handling for kinoger.ru/kinoger.be, others via ResolveURL
        """
        import requests
        from scrapers.modules.tools import cParser

        try:
            # Special handling for kinoger.ru (VOE.SX redirects)
            if 'kinoger.ru' in url or 'jilliandescribecompany.com' in url:
                xbmc.log('[KINOGER] Resolving kinoger.ru URL: %s' % url[:50], xbmc.LOGINFO)

                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Referer': 'https://kinoger.com/'
                }

                # Follow redirects and get the embed page
                response = requests.get(url, headers=headers, allow_redirects=True, timeout=10)
                html = response.text

                # Try to find direct video source (m3u8 or mp4)
                # VOE.SX pages have patterns like: "hls_src":"URL" or file:"URL"
                patterns = [
                    r'"hls_src"\s*:\s*"([^"]+)"',
                    r'"file"\s*:\s*"([^"]+\.m3u8[^"]*)"',
                    r'"file"\s*:\s*"([^"]+\.mp4[^"]*)"',
                    r'var\s+source\s*=\s*["\']([^"\']+\.(?:m3u8|mp4)[^"\']*)["\']'
                ]

                for pattern in patterns:
                    match = re.search(pattern, html, re.IGNORECASE)
                    if match:
                        stream_url = match.group(1)
                        # Skip test videos
                        if 'test-videos.co.uk' in stream_url or 'bigbuckbunny' in stream_url.lower():
                            continue

                        xbmc.log('[KINOGER] Found direct stream: %s' % stream_url[:50], xbmc.LOGINFO)
                        return stream_url

                xbmc.log('[KINOGER] No direct stream found, returning original URL', xbmc.LOGINFO)
                return url

            # Special handling for kinoger.be (similar to old code)
            elif 'kinoger.be' in url or 'streamhide.to' in url:
                xbmc.log('[KINOGER] Resolving kinoger.be URL: %s' % url[:50], xbmc.LOGINFO)

                oRequest = cRequestHandler(url, ignoreErrors=True)
                oRequest.addHeaderEntry('Referer', 'https://kinoger.com/')
                sHtmlContent = oRequest.request()

                # Look for packed JavaScript and extract sources
                pattern = r'sources:\s*\[{file:\s*["\']([^"\']+)["\']}]'
                isMatch, sUrl = cParser().parseSingleResult(sHtmlContent, pattern)

                if isMatch:
                    xbmc.log('[KINOGER] Found kinoger.be master playlist: %s' % sUrl[:50], xbmc.LOGINFO)
                    return sUrl

                xbmc.log('[KINOGER] No stream found for kinoger.be, returning original URL', xbmc.LOGINFO)
                return url

            # All other hosters: return as-is for ResolveURL
            else:
                return url

        except Exception as e:
            xbmc.log('[KINOGER] Resolve error: %s' % str(e), xbmc.LOGERROR)
            return url



#2023-07-28
# edit 2024-12-30
# edit 2025-11-21 - Fixed year/None matching, added logging

import json
import xbmc
from resources.lib.requestHandler import cRequestHandler
from scrapers.modules import cleantitle, dom_parser
from resources.lib.control import getSetting, quote
from resources.lib.utils import isBlockedHoster

SITE_IDENTIFIER = 'moflix'
SITE_DOMAIN = 'moflix-stream.xyz'
SITE_NAME = SITE_IDENTIFIER.upper()

class source:
    def __init__(self):
        self.priority = 1
        self.language = ['de']
        self.domain = getSetting('provider.' + SITE_IDENTIFIER + '.domain', SITE_DOMAIN)
        self.base_link = 'https://' + self.domain

        # self.search_link = self.base_link + '/secure/search/%s?type=&limit=8&provider='
        self.search_link = self.base_link + '/api/v1/search/%s?query=%s&limit=8'
        self.sources = []

    def run(self, titles, year, season=0, episode=0, imdb='', hostDict=None):
        try:
            # Convert year to int for comparison
            if year:
                try:
                    year = int(year)
                except (ValueError, TypeError):
                    year = None

            xbmc.log('[Moflix] Searching: titles=%s, year=%s, season=%s, episode=%s, imdb=%s' %
                     (titles, year, season, episode, imdb), xbmc.LOGINFO)

            t = set([cleantitle.get(i) for i in set(titles) if i])
            links = []

            for title in titles:
                title = quote(title)
                search_url = self.search_link % (title, title)
                xbmc.log('[Moflix] Search URL: %s' % search_url, xbmc.LOGINFO)

                oRequest = cRequestHandler(search_url)
                oRequest.addHeaderEntry('Referer', self.base_link + '/')
                response = oRequest.request()

                if not response:
                    xbmc.log('[Moflix] Empty response from search', xbmc.LOGERROR)
                    continue

                try:
                    jSearch = json.loads(response)
                except Exception as e:
                    xbmc.log('[Moflix] JSON parse error: %s, Response: %s' % (str(e), response[:200]), xbmc.LOGERROR)
                    continue

                if not jSearch:
                    xbmc.log('[Moflix] No search results', xbmc.LOGINFO)
                    continue

                aResults = jSearch.get('results', [])
                xbmc.log('[Moflix] Found %d results' % len(aResults), xbmc.LOGINFO)

                for i in aResults:
                    movie_name = i.get('name', 'Unknown')
                    movie_id = i.get('id')
                    movie_year = i.get('year')
                    movie_imdb = i.get('imdb_id')
                    is_series = i.get('is_series', False)

                    # Convert year to int for comparison (API returns int, but ensure consistency)
                    if movie_year:
                        try:
                            movie_year = int(movie_year)
                        except (ValueError, TypeError):
                            movie_year = None

                    # IMDb match - BEST!
                    if imdb and movie_imdb and movie_imdb == imdb:
                        xbmc.log('[Moflix] ✅ IMDb Match: %s (ID: %s, Year: %s)' %
                                 (movie_name, movie_id, movie_year), xbmc.LOGINFO)
                        links.append({'id': movie_id, 'name': movie_name})
                        break

                    # Movie search
                    elif season == 0:
                        # Skip series
                        if is_series:
                            xbmc.log('[Moflix] ❌ Skip series: %s' % movie_name, xbmc.LOGINFO)
                            continue

                        # Year check - FIXED: Skip if year is None or doesn't match
                        if year and movie_year:
                            if year != movie_year:
                                xbmc.log('[Moflix] ❌ Year mismatch: %s (%s != %s)' %
                                         (movie_name, movie_year, year), xbmc.LOGINFO)
                                continue
                        elif year and not movie_year:
                            # Skip entries without year if we're searching with year
                            xbmc.log('[Moflix] ❌ No year data: %s (skipping)' % movie_name, xbmc.LOGINFO)
                            continue

                        # Title match - Debug cleantitle
                        movie_clean = cleantitle.get(movie_name)
                        xbmc.log('[Moflix] Checking: "%s" (cleaned: "%s") against titles: %s' %
                                 (movie_name, movie_clean, t), xbmc.LOGINFO)

                        if movie_clean in t:
                            xbmc.log('[Moflix] ✅ Title Match: %s (ID: %s, Year: %s)' %
                                     (movie_name, movie_id, movie_year), xbmc.LOGINFO)
                            links.append({'id': movie_id, 'name': movie_name})
                        else:
                            xbmc.log('[Moflix] ❌ Title mismatch: "%s" not in %s' %
                                     (movie_clean, t), xbmc.LOGINFO)

                    # Series search
                    else:
                        # Skip movies
                        if not is_series:
                            xbmc.log('[Moflix] ❌ Skip movie (searching series): %s' % movie_name, xbmc.LOGDEBUG)
                            continue

                        # Title match
                        if cleantitle.get(movie_name) in t:
                            xbmc.log('[Moflix] ✅ Series Match: %s (ID: %s)' % (movie_name, movie_id), xbmc.LOGINFO)
                            url = self.base_link + '/api/v1/titles/%s?load=images,genres,productionCountries,keywords,videos,primaryVideo,seasons,compactCredits' % movie_id
                            oRequest = cRequestHandler(url)
                            oRequest.addHeaderEntry('Referer', url)
                            jSearch = json.loads(oRequest.request())
                            links.append({'id': jSearch['title']['id'], 'name': movie_name})

                if len(links) > 0:
                    xbmc.log('[Moflix] Found %d link(s), stopping search' % len(links), xbmc.LOGINFO)
                    break

            if len(links) == 0:
                xbmc.log('[Moflix] No matching titles found', xbmc.LOGINFO)
                return self.sources
            for link in links:
                id = link['id']
                link_name = link.get('name', 'Unknown')

                if season == 0:
                    url = self.base_link + '/api/v1/titles/%s?load=images,genres,productionCountries,keywords,videos,primaryVideo,seasons,compactCredits' % id
                else:
                    url = self.base_link + '/api/v1/titles/%s/seasons/%s/episodes/%s?load=videos,compactCredits,primaryVideo' % (id, season, episode)

                xbmc.log('[Moflix] Getting details: %s (ID: %s)' % (link_name, id), xbmc.LOGINFO)
                xbmc.log('[Moflix] Details URL: %s' % url, xbmc.LOGINFO)

                oRequest = cRequestHandler(url)
                oRequest.addHeaderEntry('Referer', url)
                response = oRequest.request()

                if not response:
                    xbmc.log('[Moflix] Empty response from details', xbmc.LOGERROR)
                    continue

                try:
                    jSearch = json.loads(response)
                except Exception as e:
                    xbmc.log('[Moflix] Details JSON parse error: %s, Response: %s' % (str(e), response[:200]), xbmc.LOGERROR)
                    continue

                if not jSearch:
                    xbmc.log('[Moflix] No details data', xbmc.LOGERROR)
                    continue

                # Get videos
                try:
                    if season == 0:
                        jVideos = jSearch['title']['videos']
                    else:
                        jVideos = jSearch['episode']['videos']

                    xbmc.log('[Moflix] Found %d video(s)' % len(jVideos), xbmc.LOGINFO)

                except KeyError as e:
                    xbmc.log('[Moflix] Missing key in response: %s' % str(e), xbmc.LOGERROR)
                    continue

                for j in jVideos:
                    quality = j.get('quality', 'SD')
                    if not quality:
                        quality = 'SD'
                    quality = '1080p' if '1080' in quality else '720p'

                    sUrl = j.get('src', '')
                    if not sUrl:
                        continue

                    isBlocked, sHoster, url, prioHoster = isBlockedHoster(sUrl)

                    # Rename hosts
                    if 'poophq' in sHoster:
                        sHoster = 'Veev'
                    elif 'moflix-stream.click' in sHoster:
                        sHoster = 'FileLions'
                    elif 'moflix-stream.day' in sHoster:
                        sHoster = 'VidGuard'

                    if isBlocked:
                        xbmc.log('[Moflix] ❌ Blocked hoster: %s' % sHoster, xbmc.LOGDEBUG)
                        continue

                    if url:
                        xbmc.log('[Moflix] ✅ Found source: %s (%s)' % (sHoster, quality), xbmc.LOGINFO)
                        self.sources.append({
                            'source': sHoster,
                            'quality': quality,
                            'language': 'de',
                            'url': url,
                            'info': j.get('language', ''),
                            'direct': True,
                            'prioHoster': prioHoster
                        })

            xbmc.log('[Moflix] Total sources found: %d' % len(self.sources), xbmc.LOGINFO)
            return self.sources

        except Exception as e:
            xbmc.log('[Moflix] Exception in run(): %s' % str(e), xbmc.LOGERROR)
            import traceback
            xbmc.log('[Moflix] Traceback: %s' % traceback.format_exc(), xbmc.LOGERROR)
            return self.sources

    def resolve(self, url):
        try:
            return url
        except:
            return
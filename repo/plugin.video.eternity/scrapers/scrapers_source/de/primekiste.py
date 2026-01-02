# -*- coding: utf-8 -*-

# primekiste.com
# 2026-01-02
# API-based scraper (React SPA)

from resources.lib.utils import isBlockedHoster
import re, json
from resources.lib.control import getSetting
from resources.lib.requestHandler import cRequestHandler
from scrapers.modules import cleantitle
import xbmc

SITE_IDENTIFIER = 'primekiste'
SITE_DOMAIN = 'primekiste.com'
SITE_NAME = SITE_IDENTIFIER.upper()

class source:
	def __init__(self):
		self.priority = 1
		self.language = ['de']
		self.domain = getSetting('provider.' + SITE_IDENTIFIER + '.domain', SITE_DOMAIN)
		self.base_link = 'https://' + self.domain
		# API endpoints discovered from DevTools:
		# Search: /data/browse/?lang=2&keyword=avatar&year=&type=&page=1&limit=20
		# Watch: /data/watch/?_id=694b185b93b6479496c12e72
		self.search_link = '/data/browse/?lang=2&keyword=%s&year=%s&type=%s&page=1&limit=20'  # (keyword, year, type)
		self.watch_link = '/data/watch/?_id=%s'  # (id)
		self.sources = []

	def run(self, titles, year, season=0, episode=0, imdb='', hostDict=None):
		try:
			xbmc.log('[PRIMEKISTE] Searching: titles=%s, year=%s, season=%s, episode=%s, imdb=%s' %
					 (titles, year, season, episode, imdb), xbmc.LOGINFO)

			# Step 1: Search for the title and get movie/series ID
			jSearch = self.search(titles, year, season, episode)
			if not jSearch or len(jSearch) == 0:
				xbmc.log('[PRIMEKISTE] No search results found', xbmc.LOGINFO)
				return []

			xbmc.log('[PRIMEKISTE] Found %d search results' % len(jSearch), xbmc.LOGINFO)

			# Step 2: Process each search result
			for item in jSearch:
				movie_id = item.get('id')
				if not movie_id:
					continue

				xbmc.log('[PRIMEKISTE] Getting streams for ID: %s' % movie_id, xbmc.LOGINFO)

				# Step 3: Fetch watch data using API
				watch_url = self.base_link + self.watch_link % movie_id
				xbmc.log('[PRIMEKISTE] Watch URL: %s' % watch_url, xbmc.LOGINFO)

				oRequest = cRequestHandler(watch_url, caching=False)
				response = oRequest.request()

				if not response:
					xbmc.log('[PRIMEKISTE] Empty watch response', xbmc.LOGWARNING)
					continue

				try:
					jWatch = json.loads(response)
				except Exception as e:
					xbmc.log('[PRIMEKISTE] JSON parse error: %s' % str(e), xbmc.LOGERROR)
					continue

				# Step 4: Extract streams from JSON response
				streams = jWatch.get('streams', [])
				if not streams:
					xbmc.log('[PRIMEKISTE] No streams in response', xbmc.LOGINFO)
					continue

				xbmc.log('[PRIMEKISTE] Found %d total streams' % len(streams), xbmc.LOGINFO)

				# Step 5: Sort streams by quality (best first) and date (newest first)
				def get_quality_score(stream):
					release = stream.get('release', '').lower()
					if '2160p' in release or '4k' in release:
						return 4
					if '1080p' in release:
						return 3
					if '720p' in release:
						return 2
					return 1

				streams = sorted(streams, key=lambda k: (get_quality_score(k), k.get('added', '')), reverse=True)

				# Step 6: Process streams with limit (exactly like movie2k)
				total = 0  # Successfully added sources
				loop = 0   # Checked streams (includes blocked ones)

				for stream in streams:
					# For series: filter by episode BEFORE counting
					if season > 0 and episode > 0:
						stream_episode = stream.get('e')
						if stream_episode and int(stream_episode) != episode:
							continue

					# Get stream URL
					stream_url = stream.get('stream')
					if not stream_url:
						continue

					# Skip streamtape (doesn't count to loop, like movie2k)
					if 'streamtape' in stream_url.lower():
						continue

					# NOW increment loop counter (after filters, like movie2k)
					loop += 1
					xbmc.log('[PRIMEKISTE] Processing stream %d: %s' % (loop, stream_url[:50]), xbmc.LOGINFO)

					# Stop after checking 50 streams (like movie2k line 56)
					if loop == 50:
						xbmc.log('[PRIMEKISTE] Reached max 50 checked streams, stopping', xbmc.LOGINFO)
						break

					# Get quality
					quality = 'HD'
					release = stream.get('release', '')
					if release:
						if '2160p' in release or '4k' in release.lower():
							quality = '4K'
						elif '1080p' in release:
							quality = '1080p'
						elif '720p' in release:
							quality = '720p'

					# Check if hoster is blocked
					isBlocked, hoster, url, prioHoster = isBlockedHoster(stream_url)

					if isBlocked:
						xbmc.log('[PRIMEKISTE] Hoster blocked: %s' % hoster, xbmc.LOGDEBUG)
						continue  # Counts to loop, but not to total

					if url:
						self.sources.append({
							'source': hoster,
							'quality': quality,
							'language': 'de',
							'url': url,
							'direct': True,
							'prioHoster': prioHoster
						})
						total += 1
						xbmc.log('[PRIMEKISTE] ✅ Added source %d/10: %s (%s)' % (total, hoster, quality), xbmc.LOGINFO)

						# Stop after 10 successful sources (like movie2k line 74)
						if total == 10:
							xbmc.log('[PRIMEKISTE] Reached limit of 10 sources, stopping', xbmc.LOGINFO)
							break

			xbmc.log('[PRIMEKISTE] Total sources found: %d' % len(self.sources), xbmc.LOGINFO)
			return self.sources

		except Exception as e:
			xbmc.log('[PRIMEKISTE] Error in run(): %s' % str(e), xbmc.LOGERROR)
			import traceback
			xbmc.log('[PRIMEKISTE] Traceback: %s' % traceback.format_exc(), xbmc.LOGERROR)
			return []

	def search(self, titles, year, season, episode):
		"""
		Search for title using API and return movie/series data
		API: /data/browse/?lang=2&keyword=TITLE&year=YEAR&type=TYPE&page=1&limit=20
		"""
		results = []

		# Determine content type for API
		mtype = 'tvseries' if season > 0 else 'movies'

		# Convert year to string
		year_str = str(year) if year else ''

		# Clean titles for matching
		t = [cleantitle.get(i) for i in titles if i]

		for title in titles:
			try:
				# Build API search URL
				search_url = self.base_link + self.search_link % (title, year_str, mtype)
				xbmc.log('[PRIMEKISTE] Search URL: %s' % search_url, xbmc.LOGINFO)

				# Make API request
				oRequest = cRequestHandler(search_url, caching=False)
				response = oRequest.request()

				if not response:
					xbmc.log('[PRIMEKISTE] Empty search response', xbmc.LOGWARNING)
					continue

				# Parse JSON response
				try:
					jSearch = json.loads(response)
				except Exception as e:
					xbmc.log('[PRIMEKISTE] JSON parse error: %s, Response: %s' % (str(e), response[:200]), xbmc.LOGERROR)
					continue

				# Get movies array from response
				movies = jSearch.get('movies', [])
				if not movies:
					xbmc.log('[PRIMEKISTE] No movies in response', xbmc.LOGINFO)
					continue

				xbmc.log('[PRIMEKISTE] Found %d results in API' % len(movies), xbmc.LOGINFO)

				# Process results
				for item in movies:
					movie_id = item.get('_id')
					movie_title = item.get('title', '')
					movie_year = item.get('year')

					if not movie_id:
						continue

					# Clean title for comparison
					clean_title = cleantitle.get(movie_title)

					xbmc.log('[PRIMEKISTE] Checking: "%s" (ID: %s, Year: %s)' % (movie_title, movie_id, movie_year), xbmc.LOGINFO)

					# For series: check if season matches
					if season > 0:
						# Check if title contains season info
						# Format: "Breaking Bad - Staffel 1" or "Breaking Bad Staffel 1"
						season_match = False
						if 'staffel' in clean_title.lower():
							# Extract season number from title
							season_pattern = r'staffel\s*(\d+)'
							match = re.search(season_pattern, clean_title.lower())
							if match:
								found_season = int(match.group(1))
								if found_season == season:
									season_match = True

						# Check if base title matches
						title_match = any(t_clean in clean_title for t_clean in t)

						if title_match and season_match:
							xbmc.log('[PRIMEKISTE] ✅ Series match: %s (Season %d)' % (movie_title, season), xbmc.LOGINFO)
							results.append({'id': movie_id, 'title': movie_title, 'year': movie_year})
							break
					else:
						# For movies: check title and year
						title_match = clean_title in t

						# Year check (allow +/- 1 year tolerance like movie2k)
						year_match = True
						if year and movie_year:
							try:
								year_int = int(year)
								movie_year_int = int(movie_year)
								if abs(movie_year_int - year_int) > 1:
									year_match = False
							except:
								pass

						if title_match and year_match:
							xbmc.log('[PRIMEKISTE] ✅ Movie match: %s (%s)' % (movie_title, movie_year), xbmc.LOGINFO)
							results.append({'id': movie_id, 'title': movie_title, 'year': movie_year})
							break

				if results:
					break

			except Exception as e:
				xbmc.log('[PRIMEKISTE] Search error: %s' % str(e), xbmc.LOGERROR)
				import traceback
				xbmc.log('[PRIMEKISTE] Traceback: %s' % traceback.format_exc(), xbmc.LOGERROR)
				continue

		return results

	def resolve(self, url):
		"""
		Resolve URL - return as-is for ResolveURL
		"""
		return url

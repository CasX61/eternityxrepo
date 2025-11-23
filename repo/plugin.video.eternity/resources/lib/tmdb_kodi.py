# -*- coding: utf-8 -*-
"""
TMDB API Module for Eternity
Based on Kodi's official TMDB scrapers (Team Kodi)
Adapted for Python 3 and Eternity integration
"""

from __future__ import absolute_import, unicode_literals
import json
import re
import unicodedata
from resources.lib.requestHandler import cRequestHandler
from resources.lib import control

# TMDB API Configuration
TMDB_API_KEY = 'f090bb54758cabf231fb605d3e3e0468'  # Team Kodi's API key
BASE_URL = 'https://api.themoviedb.org/3/{}'
HEADERS = {
    'User-Agent': 'Eternity Kodi Addon',
    'Accept': 'application/json'
}

# API Endpoints
SEARCH_MOVIE_URL = BASE_URL.format('search/movie')
SEARCH_TV_URL = BASE_URL.format('search/tv')
FIND_URL = BASE_URL.format('find/{}')
MOVIE_URL = BASE_URL.format('movie/{}')
TV_URL = BASE_URL.format('tv/{}')
SEASON_URL = BASE_URL.format('tv/{}/season/{}')
EPISODE_URL = BASE_URL.format('tv/{}/season/{}/episode/{}')
CONFIG_URL = BASE_URL.format('configuration')

# Image URLs (will be loaded from configuration)
IMAGE_BASE_URL = 'https://image.tmdb.org/t/p/'
POSTER_SIZE = 'w500'
FANART_SIZE = 'w1280'
PREVIEW_SIZE = 'w780'


class TMDBApi:
    """TMDB API wrapper based on Kodi's official scraper"""

    def __init__(self, language='de'):
        """
        Initialize TMDB API

        Args:
            language (str): Language code (e.g., 'de', 'en', 'auto')
        """
        self.language = self._get_language(language)
        self.search_language = self.language
        self.api_key = TMDB_API_KEY
        self._config = None

    def _get_language(self, lang):
        """Get language from settings or use default"""
        if lang == 'auto':
            # Try to get Kodi's language setting
            try:
                import xbmc
                kodi_lang = xbmc.getLanguage(xbmc.ISO_639_1)
                return kodi_lang if kodi_lang else 'de'
            except:
                return 'de'
        return lang

    def _call(self, url, params=None):
        """
        Make API call to TMDB

        Args:
            url (str): API endpoint URL
            params (dict): Query parameters

        Returns:
            dict: API response or error dict
        """
        if params is None:
            params = {}

        params['api_key'] = self.api_key

        # Build URL with parameters
        try:
            from urllib.parse import urlencode
            param_str = urlencode(params)
        except:
            param_str = '&'.join([f'{k}={v}' for k, v in params.items()])

        full_url = f'{url}?{param_str}'

        try:
            import xbmc
            xbmc.log('ETERNITY TMDB API Call: %s' % full_url, xbmc.LOGDEBUG)
        except:
            pass

        try:
            oRequest = cRequestHandler(full_url, ignoreErrors=True)
            response = oRequest.request()

            if response:
                result = json.loads(response)
                try:
                    import xbmc
                    xbmc.log('ETERNITY TMDB API Response: %s results' % len(result.get('results', [])), xbmc.LOGDEBUG)
                except:
                    pass
                return result
            else:
                try:
                    import xbmc
                    xbmc.log('ETERNITY TMDB API: No response from TMDB', xbmc.LOGERROR)
                except:
                    pass
                return {'error': 'No response from TMDB'}
        except Exception as e:
            try:
                import xbmc
                xbmc.log('ETERNITY TMDB API Error: %s' % str(e), xbmc.LOGERROR)
            except:
                pass
            return {'error': str(e)}

    def _parse_media_id(self, title):
        """
        Parse media ID from title string

        Supports formats:
        - 12345 (pure number = TMDB ID)
        - tmdb/12345
        - imdb/tt0133093 or tt0133093
        - tvdb/12345

        Args:
            title (str): Title string possibly containing media ID

        Returns:
            dict: {'type': 'tmdb'|'imdb'|'tvdb', 'id': '12345'} or None
        """
        # Check if title is pure numeric (TMDB ID)
        if title.strip().isdigit():
            return {'type': 'tmdb', 'id': title.strip()}

        patterns = [
            (r'tmdb[/\-](\d+)', 'tmdb'),
            (r'(tt\d{7,8})', 'imdb'),
            (r'tvdb[/\-](\d+)', 'tvdb')
        ]

        for pattern, id_type in patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                return {'type': id_type, 'id': match.group(1)}

        return None

    # ==================== MOVIE METHODS ====================

    def search_movie(self, query, year=None, page=1):
        """
        Search for movies

        Args:
            query (str): Search query
            year (str/int): Release year (optional)
            page (int): Results page number

        Returns:
            dict: Search results with 'results' and 'total_pages'
        """
        query = unicodedata.normalize('NFC', query)

        params = {
            'query': query,
            'language': self.search_language,
            'page': page,
            'include_adult': 'false'
        }

        if year:
            params['year'] = str(year)

        return self._call(SEARCH_MOVIE_URL, params)

    def find_movie_by_external_id(self, external_id, external_source='imdb_id'):
        """
        Find movie by external ID (IMDB, TVDB)

        Args:
            external_id (str): External ID (e.g., 'tt0133093')
            external_source (str): Source type ('imdb_id', 'tvdb_id')

        Returns:
            dict: Find results with 'movie_results'
        """
        params = {
            'external_source': external_source,
            'language': self.language
        }

        url = FIND_URL.format(external_id)
        return self._call(url, params)

    def get_movie_details(self, movie_id, append_to_response='credits,videos,images,alternative_titles,release_dates'):
        """
        Get detailed movie information

        Args:
            movie_id (str/int): TMDB movie ID
            append_to_response (str): Additional data to include

        Returns:
            dict: Movie details
        """
        params = {
            'language': self.language,
            'append_to_response': append_to_response
        }

        url = MOVIE_URL.format(movie_id)
        result = self._call(url, params)

        # Also get English fallback for missing translations
        if result and 'error' not in result:
            params_en = params.copy()
            params_en['language'] = 'en'
            fallback = self._call(url, params_en)

            if fallback and 'error' not in fallback:
                # Use English data as fallback
                if not result.get('overview'):
                    result['overview'] = fallback.get('overview')
                if not result.get('title'):
                    result['title'] = fallback.get('title')

        return result

    def search_movie_advanced(self, title, year=None):
        """
        Advanced movie search with intelligent matching
        Based on Kodi's TMDBMovieScraper.search() method

        Args:
            title (str): Movie title
            year (str/int): Release year (optional)

        Returns:
            list: List of movie results, sorted by relevance
        """
        def is_best(item):
            """Check if item is best match"""
            return (item.get('title', '').lower() == title.lower() and
                   (not year or item.get('release_date', '').startswith(str(year))))

        # Check if title contains media ID
        media_id = self._parse_media_id(title)

        if media_id:
            if media_id['type'] == 'tmdb':
                # Direct TMDB ID lookup
                result = self.get_movie_details(media_id['id'])
                if 'error' not in result:
                    return [result]
                return []
            else:
                # Find by external ID (IMDB)
                external_source = 'imdb_id' if media_id['type'] == 'imdb' else 'tvdb_id'
                result = self.find_movie_by_external_id(media_id['id'], external_source)
                if 'error' in result:
                    return []
                return result.get('movie_results', [])

        # Regular search
        response = self.search_movie(title, year, page=1)
        if 'error' in response:
            return []

        results = response.get('results', [])

        # Get second page if first page doesn't have good match
        if response.get('total_pages', 0) > 1:
            bests = [item for item in results if is_best(item) and item.get('popularity', 0) > 5]
            if not bests:
                page2 = self.search_movie(title, year, page=2)
                if 'error' not in page2:
                    results += page2.get('results', [])

        # Sort: best matches first, then by popularity
        bests_first = sorted([item for item in results if is_best(item)],
                           key=lambda k: k.get('popularity', 0), reverse=True)
        others = [item for item in results if item not in bests_first]

        return bests_first + others

    # ==================== TV SHOW METHODS ====================

    def search_tv(self, query, year=None, page=1):
        """
        Search for TV shows

        Args:
            query (str): Search query
            year (str/int): First air date year (optional)
            page (int): Results page number

        Returns:
            dict: Search results with 'results' and 'total_pages'
        """
        query = unicodedata.normalize('NFKC', query)

        params = {
            'query': query,
            'language': self.search_language,
            'page': page,
            'include_adult': 'false'
        }

        if year:
            params['first_air_date_year'] = str(year)

        return self._call(SEARCH_TV_URL, params)

    def get_tv_details(self, tv_id, append_to_response='credits,videos,images,alternative_titles,content_ratings,external_ids'):
        """
        Get detailed TV show information

        Args:
            tv_id (str/int): TMDB TV show ID
            append_to_response (str): Additional data to include

        Returns:
            dict: TV show details
        """
        params = {
            'language': self.language,
            'append_to_response': append_to_response
        }

        url = TV_URL.format(tv_id)
        result = self._call(url, params)

        # English fallback
        if result and 'error' not in result:
            params_en = params.copy()
            params_en['language'] = 'en'
            fallback = self._call(url, params_en)

            if fallback and 'error' not in fallback:
                if not result.get('overview'):
                    result['overview'] = fallback.get('overview')
                if not result.get('name'):
                    result['name'] = fallback.get('name')

        return result

    def get_season_details(self, tv_id, season_number):
        """
        Get season details

        Args:
            tv_id (str/int): TMDB TV show ID
            season_number (int): Season number

        Returns:
            dict: Season details with episodes
        """
        params = {'language': self.language}
        url = SEASON_URL.format(tv_id, season_number)
        return self._call(url, params)

    def get_episode_details(self, tv_id, season_number, episode_number):
        """
        Get episode details

        Args:
            tv_id (str/int): TMDB TV show ID
            season_number (int): Season number
            episode_number (int): Episode number

        Returns:
            dict: Episode details
        """
        params = {'language': self.language}
        url = EPISODE_URL.format(tv_id, season_number, episode_number)
        return self._call(url, params)

    def search_tv_advanced(self, title, year=None):
        """
        Advanced TV show search with intelligent matching

        Args:
            title (str): TV show title
            year (str/int): First air date year (optional)

        Returns:
            list: List of TV show results, sorted by relevance
        """
        # Check if title contains media ID
        media_id = self._parse_media_id(title)

        if media_id:
            if media_id['type'] == 'tmdb':
                result = self.get_tv_details(media_id['id'])
                if 'error' not in result:
                    return [result]
                return []
            else:
                external_source = 'imdb_id' if media_id['type'] == 'imdb' else 'tvdb_id'
                result = self.find_movie_by_external_id(media_id['id'], external_source)
                if 'error' in result:
                    return []
                return result.get('tv_results', [])

        # Regular search
        response = self.search_tv(title, year, page=1)
        if 'error' in response:
            return []

        return response.get('results', [])

    # ==================== UTILITY METHODS ====================

    def get_poster_url(self, poster_path, size=POSTER_SIZE):
        """Get full poster URL"""
        if not poster_path:
            return None
        return f'{IMAGE_BASE_URL}{size}{poster_path}'

    def get_fanart_url(self, backdrop_path, size=FANART_SIZE):
        """Get full fanart/backdrop URL"""
        if not backdrop_path:
            return None
        return f'{IMAGE_BASE_URL}{size}{backdrop_path}'

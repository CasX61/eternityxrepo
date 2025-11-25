# -*- coding: utf-8 -*-
"""
Eternity Cache Module - Lightweight SQLite-based cache
Based on Umbrella's cache system, simplified for Eternity
"""

from hashlib import md5
from sqlite3 import dbapi2 as db
from time import time
import os
import xbmc
import xbmcvfs

# Get Kodi's addon data path
from resources.lib import control
dataPath = control.dataPath if hasattr(control, 'dataPath') else xbmcvfs.translatePath('special://profile/addon_data/plugin.video.eternity/')

if not xbmcvfs.exists(dataPath):
	xbmcvfs.mkdirs(dataPath)

cacheFile = os.path.join(dataPath, 'cache.db')


def get(function, duration, *args):
	"""
	Get cached result or execute function and cache it
	:param function: Function to be executed
	:param duration: Duration of validity of cache in hours
	:param args: Arguments for the function
	"""
	try:
		key = _hash_function(function, args)
		cache_result = _cache_get(key)

		if cache_result:
			try:
				result = eval(cache_result['value'])
			except:
				result = None

			# Check if cache is still valid
			if _is_cache_valid(cache_result['date'], duration):
				return result

		# Execute function to get fresh result
		fresh_result = repr(function(*args))

		# Check if result is invalid (None, empty, etc.)
		invalid = False
		try:
			if not fresh_result:
				invalid = True
			elif fresh_result in ('None', '', '[]', '{}'):
				invalid = True
		except:
			pass

		if invalid:
			# Return old cache if available
			if cache_result:
				return result
			else:
				return None
		else:
			# Cache fresh result
			_cache_insert(key, fresh_result)
			return eval(fresh_result)
	except Exception as e:
		xbmc.log('[Eternity-Cache] get() Error: %s' % str(e), xbmc.LOGERROR)
		return None


def _is_cache_valid(cached_time, cache_timeout):
	"""Check if cache is still valid"""
	now = int(time())
	diff = now - cached_time
	return (cache_timeout * 3600) > diff


def _hash_function(function, args):
	"""Create unique hash for function + args"""
	try:
		function_name = repr(function)
		args_str = ','.join([repr(arg) for arg in args])
		combined = function_name + args_str
		return md5(combined.encode('utf-8')).hexdigest()
	except:
		return md5(str(function).encode('utf-8')).hexdigest()


def _cache_get(key):
	"""Get cache entry from database"""
	try:
		dbcon = _get_connection()
		dbcur = dbcon.cursor()

		# Check if table exists
		ck_table = dbcur.execute("""SELECT * FROM sqlite_master WHERE type='table' AND name='cache';""").fetchone()
		if not ck_table:
			dbcon.close()
			return None

		# Get cache entry
		dbcur.execute("""SELECT * FROM cache WHERE key=?""", (key,))
		result = dbcur.fetchone()
		dbcon.close()

		if result:
			return {'key': result[0], 'value': result[1], 'date': result[2]}
		return None
	except Exception as e:
		xbmc.log('[Eternity-Cache] _cache_get() Error: %s' % str(e), xbmc.LOGERROR)
		return None


def _cache_insert(key, value):
	"""Insert or update cache entry"""
	try:
		dbcon = _get_connection()
		dbcur = dbcon.cursor()

		# Create table if not exists
		dbcur.execute("""CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT, date INTEGER);""")

		# Insert or replace
		now = int(time())
		dbcur.execute("""INSERT OR REPLACE INTO cache (key, value, date) VALUES (?, ?, ?)""", (key, value, now))

		dbcon.commit()
		dbcon.close()
	except Exception as e:
		xbmc.log('[Eternity-Cache] _cache_insert() Error: %s' % str(e), xbmc.LOGERROR)


def _get_connection():
	"""Get database connection"""
	try:
		dbcon = db.connect(cacheFile, timeout=20)
		dbcon.row_factory = None
		return dbcon
	except Exception as e:
		xbmc.log('[Eternity-Cache] _get_connection() Error: %s' % str(e), xbmc.LOGERROR)
		return None


def remove(function, *args):
	"""Remove specific cache entry"""
	try:
		key = _hash_function(function, args)
		dbcon = _get_connection()
		dbcur = dbcon.cursor()
		dbcur.execute("""DELETE FROM cache WHERE key=?""", (key,))
		dbcon.commit()
		dbcon.close()
	except Exception as e:
		xbmc.log('[Eternity-Cache] remove() Error: %s' % str(e), xbmc.LOGERROR)


def clear_all():
	"""Clear entire cache"""
	try:
		dbcon = _get_connection()
		dbcur = dbcon.cursor()
		dbcur.execute("""DELETE FROM cache""")
		dbcon.commit()
		dbcon.close()
		xbmc.log('[Eternity-Cache] All cache cleared', xbmc.LOGINFO)
	except Exception as e:
		xbmc.log('[Eternity-Cache] clear_all() Error: %s' % str(e), xbmc.LOGERROR)


# Simple key-value storage for timestamps and simple data
_simple_cache = {}

def set_simple(key, value):
	"""Simple in-memory cache for timestamps"""
	global _simple_cache
	_simple_cache[key] = value


def get_simple(key, default=None):
	"""Get simple in-memory cache value"""
	global _simple_cache
	return _simple_cache.get(key, default)

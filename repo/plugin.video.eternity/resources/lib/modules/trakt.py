# -*- coding: utf-8 -*-
"""
Eternity Trakt Integration - Phase 1.1 Complete
Based on Umbrella (Python 3, modern), adapted for Eternity
Implements CLAUDE.md Phase 1.1-1.5 requirements
"""

from datetime import datetime
from json import dumps as jsdumps, loads as jsloads
import re
import requests
from requests.adapters import HTTPAdapter
from threading import Thread
from urllib3.util.retry import Retry
from urllib.parse import urljoin
import time
import os

from resources.lib import control

# Trakt API Configuration
BASE_URL = 'https://api.trakt.tv'
CLIENT_ID = '239a31316d98d8a9b6590a9a8204de30a5056fbeaa5a630b3c5539c06cd37179'
CLIENT_SECRET = '4e552b8c913ae5f739b2a49522db6d10243d4e1b0a2bbea896d7efa7a0d58ae0'
REDIRECT_URI = 'urn:ietf:wg:oauth:2.0:oob'

# HTTP Session with retries
session = requests.Session()
retries = Retry(total=4, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504, 520, 521, 522, 524, 530])
session.mount('https://api.trakt.tv', HTTPAdapter(max_retries=retries, pool_maxsize=100))

# Helper functions
getLS = control.lang if hasattr(control, 'lang') else lambda x: str(x)
getSetting = control.getSetting
setSetting = control.setSetting

headers = {'Content-Type': 'application/json', 'trakt-api-key': '', 'trakt-api-version': '2'}
trakt_icon = os.path.join(control.artPath(), 'trakt.png') if hasattr(control, 'artPath') else ''

def getTrakt(url, post=None, extended=False, silent=False, reauth_attempts=0):
	"""
	Core API request function with auto token refresh and error handling
	Based on Umbrella's getTrakt() with loop prevention
	"""
	try:
		if not url.startswith(BASE_URL): url = urljoin(BASE_URL, url)
		if headers['trakt-api-key'] == '': headers['trakt-api-key'] = CLIENT_ID
		if post: post = jsdumps(post)

		# Add authorization if user is logged in
		if getTraktCredentialsInfo():
			current_token = getSetting('trakt.user.token')
			headers['Authorization'] = 'Bearer %s' % current_token

		# Make request
		if post:
			response = session.post(url, data=post, headers=headers, timeout=20)
		else:
			response = session.get(url, headers=headers, timeout=20)

		status_code = str(response.status_code)

		# Handle different status codes
		if status_code in ('200', '201'):
			if extended: return response, response.headers
			else: return response

		elif status_code == '401':  # Unauthorized - Token expired
			# Check for private user header (Umbrella compatibility)
			if response.headers.get('x-private-user') == 'true':
				control.log('TRAKT: Private user header detected, ignoring 401 for URL: %s' % url)
				return None

			# Prevent infinite re-auth loops (CLAUDE.md requirement)
			if reauth_attempts >= 2:
				control.log('TRAKT: Too many re-auth attempts, stopping to prevent infinite loop')
				return None

			control.log('TRAKT: Token expired (401), attempting re-auth (attempt %d)' % (reauth_attempts + 1))
			success = re_auth(headers)
			if success: return getTrakt(url, post, extended=extended, silent=silent, reauth_attempts=reauth_attempts + 1)

		elif status_code == '429':  # Rate limit
			if 'Retry-After' in response.headers:
				throttleTime = response.headers['Retry-After']
				control.log('TRAKT: Rate limit hit, sleeping for %s seconds' % throttleTime)
				if not silent and not control.condVisibility('Player.HasVideo'):
					control.infoDialog(title=32315, message='Trakt Throttling: Sleeping for %s seconds' % throttleTime)
				control.sleep((int(throttleTime) + 1) * 1000)
				return getTrakt(url, post, extended=extended, silent=silent, reauth_attempts=reauth_attempts)

		elif status_code == '423':  # Locked account
			control.log('TRAKT: Locked User Account - Contact Trakt Support')
			if not silent: control.infoDialog(title='Trakt', message='Account Locked - Contact Trakt Support')

		elif status_code == '404':  # Not found
			control.log('TRAKT: 404 Not Found: %s' % url)

		elif status_code.startswith('5'):  # Server errors
			control.log('TRAKT: Temporary Server Problem (%s)' % status_code)
			if not silent: control.infoDialog(title='Trakt', message='Temporary Server Problem')

		return None

	except Exception as e:
		control.log('TRAKT: getTrakt Error: %s' % str(e))
		return None

def getTraktAsJson(url, post=None, silent=False):
	"""
	Get Trakt API response as JSON with sorting support
	"""
	try:
		res_headers = {}
		r = getTrakt(url=url, post=post, extended=True, silent=silent)
		if not r: return None
		if isinstance(r, tuple) and len(r) == 2: r, res_headers = r[0], r[1]
		if not r: return None
		r = r.json()

		# Handle Trakt sorting headers
		if 'X-Sort-By' in res_headers and 'X-Sort-How' in res_headers:
			r = sort_list(res_headers['X-Sort-By'], res_headers['X-Sort-How'], r)
		return r
	except Exception as e:
		control.log('TRAKT: getTraktAsJson Error: %s' % str(e))
		return None

def sort_list(sort_key, sort_direction, list_data):
	"""
	Sort list based on Trakt headers
	"""
	try:
		reverse = False if sort_direction == 'asc' else True
		if sort_key == 'rank':
			return sorted(list_data, key=lambda x: x.get('rank', 0), reverse=reverse)
		elif sort_key == 'added':
			return sorted(list_data, key=lambda x: x.get('listed_at', ''), reverse=reverse)
		elif sort_key == 'title':
			return sorted(list_data, key=lambda x: x.get('title', ''), reverse=reverse)
		elif sort_key == 'released':
			return sorted(list_data, key=lambda x: x.get('released', ''), reverse=reverse)
		elif sort_key == 'runtime':
			return sorted(list_data, key=lambda x: x.get('runtime', 0), reverse=reverse)
		else:
			return list_data
	except:
		return list_data

def re_auth(headers):
	"""
	Refresh OAuth token with loop prevention and invalid_grant handling
	Based on Umbrella's re_auth() - CLAUDE.md Phase 1.1 requirement
	"""
	try:
		oauth = urljoin(BASE_URL, '/oauth/token')
		opost = {
			'client_id': CLIENT_ID,
			'client_secret': CLIENT_SECRET,
			'redirect_uri': REDIRECT_URI,
			'grant_type': 'refresh_token',
			'refresh_token': getSetting('trakt.refreshtoken')
		}

		control.log('TRAKT: Re-Authenticating with refresh token')
		response = session.post(url=oauth, data=jsdumps(opost), headers=headers, timeout=20)
		status_code = str(response.status_code)

		if status_code not in ('401', '403', '405'):
			try:
				response_json = response.json()
			except Exception as e:
				control.log('TRAKT: JSON decode error in re_auth: %s' % str(e))
				return False

			# Check for invalid_grant error (CLAUDE.md requirement)
			if 'error' in response_json and response_json['error'] == 'invalid_grant':
				control.log('TRAKT: Invalid grant - clearing tokens and forcing re-auth')
				control.infoDialog(title='Trakt', message='Please Re-Authorize your Trakt Account')

				# Clear invalid tokens (with homeWindow property protection)
				control.homeWindow.setProperty('eternity.updateSettings', 'false')
				setSetting('trakt.isauthed', 'false')
				setSetting('trakt.user.token', '')
				setSetting('trakt.refreshtoken', '')
				setSetting('trakt.token.expires', '')
				control.homeWindow.setProperty('eternity.updateSettings', 'true')
				return False

			# Success - save new tokens
			token = response_json['access_token']
			refresh = response_json['refresh_token']

			# Use Trakt's expiration time (CLAUDE.md requirement - not hardcoded 24h!)
			expires_from_trakt = response_json.get('expires_in', 86400)
			expires = str(time.time() + expires_from_trakt)

			control.log('TRAKT: Token refreshed successfully, expires at %s' % str(datetime.fromtimestamp(float(expires))))

			# Save tokens (with homeWindow property protection)
			control.homeWindow.setProperty('eternity.updateSettings', 'false')
			setSetting('trakt.isauthed', 'true')
			setSetting('trakt.user.token', token)
			setSetting('trakt.refreshtoken', refresh)
			setSetting('trakt.token.expires', expires)
			control.homeWindow.setProperty('eternity.updateSettings', 'true')
			return True
		else:
			control.log('TRAKT: Error while re-authorizing token: %s' % status_code)

			# Invalid refresh token - clear credentials
			if status_code in ('401', '403'):
				control.log('TRAKT: Refresh token appears to be invalid, clearing tokens')
				control.homeWindow.setProperty('eternity.updateSettings', 'false')
				setSetting('trakt.isauthed', 'false')
				setSetting('trakt.user.token', '')
				setSetting('trakt.refreshtoken', '')
				setSetting('trakt.token.expires', '')
				control.homeWindow.setProperty('eternity.updateSettings', 'true')
			return False

	except Exception as e:
		control.log('TRAKT: Exception in re_auth: %s' % str(e))
		return False

def traktAuth(fromSettings=0):
	"""
	OAuth Device Flow with QR Code support
	EXACT 1:1 from Umbrella's traktAuth() - CLAUDE.md Phase 1.1
	"""
	try:
		import xbmc
		xbmc.log('[Eternity-Trakt] traktAuth: START', xbmc.LOGINFO)

		# Check if already authenticated
		if getTraktCredentialsInfo():
			xbmc.log('[Eternity-Trakt] traktAuth: Already authenticated!', xbmc.LOGINFO)
			username = getSetting('trakt.user.name')
			if control.yesnoDialog('Trakt Konto bereits verbunden', 'Benutzername: %s' % username, 'Möchten Sie das Konto zurücksetzen?', 'Trakt'):
				xbmc.log('[Eternity-Trakt] traktAuth: User wants to re-auth, clearing credentials', xbmc.LOGINFO)
				# Clear old credentials (with homeWindow property protection)
				control.homeWindow.setProperty('eternity.updateSettings', 'false')
				setSetting('trakt.user.name', '')
				setSetting('trakt.user.token', '')
				setSetting('trakt.refreshtoken', '')
				setSetting('trakt.token.expires', '')
				setSetting('trakt.isauthed', 'false')
				control.homeWindow.setProperty('eternity.updateSettings', 'true')
			else:
				xbmc.log('[Eternity-Trakt] traktAuth: User cancelled re-auth', xbmc.LOGINFO)
				if fromSettings == 1:
					control.openSettings('4.0', 'plugin.video.eternity')
				return True

		traktDeviceCode = getTraktDeviceCode()
		xbmc.log('[Eternity-Trakt] traktAuth: Got device code: %s' % str(bool(traktDeviceCode)), xbmc.LOGINFO)

		deviceCode = getTraktDeviceToken(traktDeviceCode)
		xbmc.log('[Eternity-Trakt] traktAuth: getTraktDeviceToken returned: %s' % str(type(deviceCode)), xbmc.LOGINFO)

		if deviceCode:
			xbmc.log('[Eternity-Trakt] traktAuth: Parsing JSON...', xbmc.LOGINFO)
			deviceCode = deviceCode.json()
			xbmc.log('[Eternity-Trakt] traktAuth: JSON parsed, got access_token: %s' % str('access_token' in deviceCode), xbmc.LOGINFO)

			# Use Trakt's provided expiration time (not hardcoded 24h)
			expires_from_trakt = deviceCode.get('expires_in', 86400)  # fallback to 24 hours
			expires_at = time.time() + expires_from_trakt

			xbmc.log('[Eternity-Trakt] traktAuth: Saving settings...', xbmc.LOGINFO)
			# Save tokens (with homeWindow property protection)
			control.homeWindow.setProperty('eternity.updateSettings', 'false')
			setSetting('trakt.token.expires', str(expires_at))
			setSetting('trakt.user.token', deviceCode["access_token"])
			setSetting('trakt.scrobble', 'true')
			setSetting('trakt.isauthed', 'true')
			setSetting('trakt.refreshtoken', deviceCode["refresh_token"])
			control.homeWindow.setProperty('eternity.updateSettings', 'true')
			xbmc.log('[Eternity-Trakt] traktAuth: Settings saved!', xbmc.LOGINFO)

			# Get username - NO SLEEP, do it immediately!
			try:
				xbmc.log('[Eternity-Trakt] traktAuth: Getting username...', xbmc.LOGINFO)

				# Make direct API call with new token
				headers_user = {
					'Content-Type': 'application/json',
					'trakt-api-key': CLIENT_ID,
					'trakt-api-version': '2',
					'Authorization': 'Bearer %s' % deviceCode["access_token"]
				}

				xbmc.log('[Eternity-Trakt] traktAuth: Calling /users/me...', xbmc.LOGINFO)
				user_response = requests.get(urljoin(BASE_URL, '/users/me'), headers=headers_user, timeout=30)
				xbmc.log('[Eternity-Trakt] traktAuth: Got response: %d' % user_response.status_code, xbmc.LOGINFO)

				if user_response.status_code == 200:
					user_data = user_response.json()
					username = user_data['username']
					setSetting('trakt.user.name', str(username))
					xbmc.log('[Eternity-Trakt] traktAuth: Username saved: %s' % username, xbmc.LOGINFO)
				else:
					xbmc.log('[Eternity-Trakt] traktAuth: Username fetch failed with status %d' % user_response.status_code, xbmc.LOGERROR)
			except Exception as e:
				xbmc.log('[Eternity-Trakt] traktAuth: Username fetch exception: %s' % str(e), xbmc.LOGERROR)
				import traceback
				xbmc.log('[Eternity-Trakt] traktAuth: Traceback: %s' % traceback.format_exc(), xbmc.LOGERROR)

			trakt_icon = os.path.join(control.artPath(), 'trakt.png')
			control.infoDialog('Trakt erfolgreich autorisiert!', icon=trakt_icon)
			xbmc.log('[Eternity-Trakt] traktAuth: Notification shown', xbmc.LOGINFO)

			if fromSettings == 1:
				control.openSettings('4.0', 'plugin.video.eternity')

			# Ask about indicators
			xbmc.log('[Eternity-Trakt] traktAuth: Showing indicators dialog...', xbmc.LOGINFO)
			if not control.yesnoDialog('Trakt als Gesehen/Ungesehen Status verwenden?', '', '', 'Indicators', 'Nein', 'Ja'):
				xbmc.log('[Eternity-Trakt] traktAuth: User declined indicators, returning True', xbmc.LOGINFO)
				return True

			# Set indicators (with homeWindow property protection)
			control.homeWindow.setProperty('eternity.updateSettings', 'false')
			setSetting('indicators.alt', '1')
			setSetting('indicators', 'Trakt')
			control.homeWindow.setProperty('eternity.updateSettings', 'true')
			xbmc.log('[Eternity-Trakt] traktAuth: SUCCESS - returning True', xbmc.LOGINFO)
			return True

		xbmc.log('[Eternity-Trakt] traktAuth: deviceCode was None/False', xbmc.LOGWARNING)
		if fromSettings == 1:
			control.openSettings('4.0', 'plugin.video.eternity')

		trakt_icon = os.path.join(control.artPath(), 'trakt.png')
		control.infoDialog('Trakt Autorisierung fehlgeschlagen', icon=trakt_icon)
		return False

	except Exception as e:
		import xbmc
		xbmc.log('[Eternity-Trakt] traktAuth EXCEPTION: %s' % str(e), xbmc.LOGERROR)
		import traceback
		xbmc.log('[Eternity-Trakt] traktAuth Traceback: %s' % traceback.format_exc(), xbmc.LOGERROR)
		return False

def traktRevoke(fromSettings=0):
	"""
	Revoke Trakt authorization and clear all credentials
	CLAUDE.md Phase 1.3 requirement
	"""
	import xbmc

	# Check if authenticated
	if not getTraktCredentialsInfo():
		xbmc.log('[Eternity-Trakt] traktRevoke: Not authenticated!', xbmc.LOGWARNING)
		control.dialog.ok('Trakt', 'Nicht mit Trakt verbunden')
		if fromSettings == 1:
			control.openSettings('4.0', 'plugin.video.eternity')
		return

	xbmc.log('[Eternity-Trakt] traktRevoke: Revoking authorization...', xbmc.LOGINFO)

	data = {"token": getSetting('trakt.user.token')}
	try:
		getTrakt('/oauth/revoke', post=data)
	except: pass

	# Clear credentials (with homeWindow property protection)
	control.homeWindow.setProperty('eternity.updateSettings', 'false')
	setSetting('trakt.user.name', '')
	setSetting('trakt.token.expires', '')
	setSetting('trakt.user.token', '')
	setSetting('trakt.isauthed', 'false')
	setSetting('trakt.refreshtoken', '')

	# Reset indicators if using Trakt
	if getSetting('indicators.alt') == '1':
		setSetting('indicators.alt', '0')
		setSetting('indicators', 'Local')
	control.homeWindow.setProperty('eternity.updateSettings', 'true')

	xbmc.log('[Eternity-Trakt] traktRevoke: Authorization revoked!', xbmc.LOGINFO)

	if fromSettings == 1:
		control.openSettings('4.0', 'plugin.video.eternity')

	control.dialog.ok('Trakt', 'Autorisierung erfolgreich entfernt')

def getTraktDeviceCode():
	"""
	Get device code for OAuth flow
	"""
	try:
		data = {'client_id': CLIENT_ID}
		dCode = getTrakt('/oauth/device/code', post=data)
		result = dCode.json()
		return result
	except Exception as e:
		control.log('TRAKT: getTraktDeviceCode Error: %s' % str(e))
		return ''

def getTraktDeviceToken(traktDeviceCode):
	"""
	Poll for device token with progress dialog and QR code
	EXACT 1:1 from Umbrella's getTraktDeviceToken() - includes QR code support
	"""
	try:
		import xbmc
		xbmc.log('[Eternity-Trakt] getTraktDeviceToken: START', xbmc.LOGINFO)

		data = {
			"code": traktDeviceCode["device_code"],
			"client_id": CLIENT_ID,
			"client_secret": CLIENT_SECRET
		}

		start = time.time()
		expires_in = traktDeviceCode['expires_in']
		highlight_color = getSetting('highlight.color') or 'skyblue'

		# EXACT 1:1 from Umbrella - Same formatting!
		verification_url = '1) Open this link in a browser : [COLOR %s]%s[/COLOR]' % (highlight_color, str(traktDeviceCode['verification_url']))
		user_code = '2) When prompted enter : [COLOR %s]%s[/COLOR]' % (highlight_color, str(traktDeviceCode['user_code']))

		xbmc.log('[Eternity-Trakt] getTraktDeviceToken: Creating dialog...', xbmc.LOGINFO)
		xbmc.log('[Eternity-Trakt] URL: %s' % traktDeviceCode['verification_url'], xbmc.LOGINFO)
		xbmc.log('[Eternity-Trakt] Code: %s' % traktDeviceCode['user_code'], xbmc.LOGINFO)

		# Standard Kodi progressDialog (EXACT like Umbrella)
		progressDialog = control.progressDialog
		progressDialog.create('TRAKT: Authorize', control.progress_line % (verification_url, user_code))
		xbmc.log('[Eternity-Trakt] getTraktDeviceToken: Dialog created, starting poll loop', xbmc.LOGINFO)

		try:
			# Simple FOR-LOOP like old working version (not while-loop!)
			interval = traktDeviceCode['interval']
			for i in range(0, expires_in):
				# Check if user cancelled
				if progressDialog.iscanceled():
					xbmc.log('[Eternity-Trakt] getTraktDeviceToken: User cancelled!', xbmc.LOGINFO)
					break

				# Sleep 1 second
				time.sleep(1)

				# Only check every interval seconds (like old version)
				if not float(i) % interval == 0:
					continue

				xbmc.log('[Eternity-Trakt] getTraktDeviceToken: Poll attempt at second %d' % i, xbmc.LOGINFO)

				try:
					url = urljoin(BASE_URL, '/oauth/device/token')
					response = requests.post(url, json=data, headers=headers, timeout=20)

					xbmc.log('[Eternity-Trakt] getTraktDeviceToken: Response status: %d' % response.status_code, xbmc.LOGINFO)

					if response.status_code == 200:
						xbmc.log('[Eternity-Trakt] getTraktDeviceToken: SUCCESS! Returning response', xbmc.LOGINFO)
						return response
					elif response.status_code == 400:
						# Pending - user hasn't authorized yet
						progress = int(100) - int(100 * float(i) / expires_in)
						progressDialog.update(progress, control.progress_line % (verification_url, user_code))
					else:
						xbmc.log('[Eternity-Trakt] getTraktDeviceToken: Unexpected status %d' % response.status_code, xbmc.LOGWARNING)

				except Exception as e:
					xbmc.log('[Eternity-Trakt] getTraktDeviceToken: Poll error: %s' % str(e), xbmc.LOGERROR)
		finally:
			xbmc.log('[Eternity-Trakt] getTraktDeviceToken: FINALLY block - closing dialog NOW', xbmc.LOGINFO)
			progressDialog.close()
			xbmc.log('[Eternity-Trakt] getTraktDeviceToken: Dialog closed!', xbmc.LOGINFO)

		xbmc.log('[Eternity-Trakt] getTraktDeviceToken: Exited loop, returning None', xbmc.LOGWARNING)
		return None

	except Exception as e:
		import xbmc
		xbmc.log('[Eternity-Trakt] getTraktDeviceToken EXCEPTION: %s' % str(e), xbmc.LOGERROR)
		control.log('TRAKT: getTraktDeviceToken Error: %s' % str(e))
		return None

def getTraktCredentialsInfo():
	"""
	Check if user is authenticated with Trakt
	CLAUDE.md Phase 1.1 requirement
	"""
	username = getSetting('trakt.user.name').strip()
	token = getSetting('trakt.user.token')
	refresh = getSetting('trakt.refreshtoken')

	if username == '' or token == '' or refresh == '':
		return False
	return True

def getTraktIndicatorsInfo():
	"""
	Check if Trakt is active as indicators source
	CLAUDE.md Phase 1.1 requirement
	"""
	indicators = getSetting('indicators.alt')
	indicators = True if indicators == '1' else False
	return indicators

# =============================
# WATCH/UNWATCH FUNCTIONS
# =============================

def watch(content_type, name, imdb=None, tvdb=None, season=None, episode=None, refresh=True):
	"""
	Mark as Watched - Based on Umbrella's watch()
	CLAUDE.md Phase 1.2 requirement
	"""
	control.busy()
	success = False

	if content_type == 'movie':
		success = markMovieAsWatched(imdb)
	elif content_type == 'tvshow':
		success = markTVShowAsWatched(imdb, tvdb)
	elif content_type == 'season':
		success = markSeasonAsWatched(imdb, tvdb, season)
	elif content_type == 'episode':
		success = markEpisodeAsWatched(imdb, tvdb, season, episode)
	else:
		success = False

	control.hide()
	if refresh: control.refresh()
	control.trigger_widget_refresh()  # Umbrella compatibility - refresh widgets

	if season and not episode: name = '%s-Season%s...' % (name, season)
	if season and episode: name = '%s-S%sxE%02d...' % (name, season, int(episode))

	if getSetting('trakt.general.notifications') == 'true':
		if success is True:
			control.infoDialog(title='Trakt', message='Marked as Watched: %s' % name)
		else:
			control.infoDialog(title='Trakt', message='Failed to mark as watched: %s' % name)

	if not success:
		control.log('TRAKT: Failed to mark as watched: %s (imdb=%s, tvdb=%s)' % (name, imdb, tvdb))

def unwatch(content_type, name, imdb=None, tvdb=None, season=None, episode=None, refresh=True):
	"""
	Mark as Unwatched - Based on Umbrella's unwatch()
	CLAUDE.md Phase 1.2 requirement
	"""
	control.busy()
	success = False

	if content_type == 'movie':
		success = markMovieAsNotWatched(imdb)
	elif content_type == 'tvshow':
		success = markTVShowAsNotWatched(imdb, tvdb)
	elif content_type == 'season':
		success = markSeasonAsNotWatched(imdb, tvdb, season)
	elif content_type == 'episode':
		success = markEpisodeAsNotWatched(imdb, tvdb, season, episode)
	else:
		success = False

	control.hide()
	if refresh: control.refresh()
	control.trigger_widget_refresh()  # Umbrella compatibility - refresh widgets

	if season and not episode: name = '%s-Season%s...' % (name, season)
	if season and episode: name = '%s-S%sxE%02d...' % (name, season, int(episode))

	if getSetting('trakt.general.notifications') == 'true':
		if success is True:
			control.infoDialog(title='Trakt', message='Marked as Unwatched: %s' % name)
		else:
			control.infoDialog(title='Trakt', message='Failed to mark as unwatched: %s' % name)

	if not success:
		control.log('TRAKT: Failed to mark as unwatched: %s (imdb=%s, tvdb=%s)' % (name, imdb, tvdb))

def markMovieAsWatched(imdb):
	"""Mark movie as watched"""
	try:
		if not imdb.startswith('tt'): imdb = 'tt' + imdb
		post = {"movies": [{"ids": {"imdb": imdb}}]}
		result = getTrakt('/sync/history', post=post)
		return result is not None
	except:
		return False

def markMovieAsNotWatched(imdb):
	"""Mark movie as unwatched"""
	try:
		if not imdb.startswith('tt'): imdb = 'tt' + imdb
		post = {"movies": [{"ids": {"imdb": imdb}}]}
		result = getTrakt('/sync/history/remove', post=post)
		return result is not None
	except:
		return False

def markTVShowAsWatched(imdb, tvdb):
	"""Mark entire TV show as watched"""
	try:
		post = {"shows": [{"ids": {"tvdb": tvdb}}]}
		result = getTrakt('/sync/history', post=post)
		return result is not None
	except:
		return False

def markTVShowAsNotWatched(imdb, tvdb):
	"""Mark entire TV show as unwatched"""
	try:
		post = {"shows": [{"ids": {"tvdb": tvdb}}]}
		result = getTrakt('/sync/history/remove', post=post)
		return result is not None
	except:
		return False

def markSeasonAsWatched(imdb, tvdb, season):
	"""Mark season as watched"""
	try:
		season = int('%01d' % int(season))
		post = {
			"shows": [{
				"ids": {"tvdb": tvdb},
				"seasons": [{"number": season}]
			}]
		}
		result = getTrakt('/sync/history', post=post)
		return result is not None
	except:
		return False

def markSeasonAsNotWatched(imdb, tvdb, season):
	"""Mark season as unwatched"""
	try:
		season = int('%01d' % int(season))
		post = {
			"shows": [{
				"ids": {"tvdb": tvdb},
				"seasons": [{"number": season}]
			}]
		}
		result = getTrakt('/sync/history/remove', post=post)
		return result is not None
	except:
		return False

def markEpisodeAsWatched(imdb, tvdb, season, episode):
	"""Mark episode as watched"""
	try:
		season = int('%01d' % int(season))
		episode = int('%01d' % int(episode))
		post = {
			"shows": [{
				"ids": {"tvdb": tvdb},
				"seasons": [{
					"number": season,
					"episodes": [{"number": episode}]
				}]
			}]
		}
		result = getTrakt('/sync/history', post=post)
		return result is not None
	except:
		return False

def markEpisodeAsNotWatched(imdb, tvdb, season, episode):
	"""Mark episode as unwatched"""
	try:
		season = int('%01d' % int(season))
		episode = int('%01d' % int(episode))
		post = {
			"shows": [{
				"ids": {"tvdb": tvdb},
				"seasons": [{
					"number": season,
					"episodes": [{"number": episode}]
				}]
			}]
		}
		result = getTrakt('/sync/history/remove', post=post)
		return result is not None
	except:
		return False

# =============================
# MANAGER FUNCTIONS
# =============================

def manager(name, imdb=None, tvdb=None, season=None, episode=None, refresh=True, watched=None, unfinished=False, tvshow=None):
	"""
	Trakt Manager - Context Menu with all options
	Based on Umbrella's manager() - CLAUDE.md Phase 1.2 requirement
	"""
	lists = []
	try:
		if season: season = int(season)
		if episode: episode = int(episode)
		media_type = 'Show' if tvdb else 'Movie'

		# Build menu items
		items = []

		# Watch/Unwatch
		if watched is not None:
			if watched is True:
				items.append(('Mark as [B]Unwatched[/B]', 'unwatch'))
			else:
				items.append(('Mark as [B]Watched[/B]', 'watch'))
		else:
			items.append(('Mark as [B]Watched[/B]', 'watch'))
			items.append(('Mark as [B]Unwatched[/B]', 'unwatch'))

		# Rate (if script.trakt addon is installed)
		if control.condVisibility('System.HasAddon(script.trakt)'):
			items.append(('[B]Rate[/B]', 'rate'))
			items.append(('[B]Unrate[/B]', 'unrate'))

		# Hide (TV shows only)
		if tvdb:
			items.append(('Hide %s' % media_type, 'hideItem'))
			items.append(('Hidden Manager', 'hiddenManager'))

		# Unfinished Manager
		if unfinished is True:
			if media_type == 'Movie':
				items.append(('Unfinished Movies Manager', 'unfinishedMovieManager'))
			elif episode:
				items.append(('Unfinished Episodes Manager', 'unfinishedEpisodeManager'))

		# Scrobble Reset
		if getSetting('trakt.scrobble') == 'true':
			if media_type == 'Movie' or episode:
				items.append(('Scrobble Reset', 'scrobbleReset'))

		# Watchlist/Collection
		if season or episode:
			items.append(('Add Episode to [B]Watchlist[/B]', '/sync/watchlist'))
			items.append(('Remove Episode from [B]Watchlist[/B]', '/sync/watchlist/remove'))

		items.append(('Add to [B]Watchlist[/B]', '/sync/watchlist'))
		items.append(('Remove from [B]Watchlist[/B]', '/sync/watchlist/remove'))
		items.append(('Add to [B]Collection[/B]', '/sync/collection'))
		items.append(('Remove from [B]Collection[/B]', '/sync/collection/remove'))
		items.append(('Add to new list', '/users/me/lists/%s/items'))

		# Get user lists
		result = getTraktAsJson('/users/me/lists')
		if result:
			lists = [(i['name'], i['ids']['slug']) for i in result]
			lists = [lists[i//2] for i in range(len(lists)*2)]

			for i in range(0, len(lists), 2):
				lists[i] = (('Add to [B]%s[/B]' % lists[i][0]), '/users/me/lists/%s/items' % lists[i][1])
			for i in range(1, len(lists), 2):
				lists[i] = (('Remove from [B]%s[/B]' % lists[i][0]), '/users/me/lists/%s/items/remove' % lists[i][1])
			items += lists

		control.hide()
		select = control.selectDialog([i[0] for i in items], heading='Trakt Manager')

		if select == -1: return
		if select >= 0:
			# Handle action
			if items[select][1] == 'watch':
				watch(control.infoLabel('Container.ListItem.DBTYPE'), name, imdb=imdb, tvdb=tvdb, season=season, episode=episode, refresh=refresh)
			elif items[select][1] == 'unwatch':
				unwatch(control.infoLabel('Container.ListItem.DBTYPE'), name, imdb=imdb, tvdb=tvdb, season=season, episode=episode, refresh=refresh)
			elif items[select][1] == 'rate':
				rate(imdb=imdb, tvdb=tvdb, season=season, episode=episode)
			elif items[select][1] == 'unrate':
				unrate(imdb=imdb, tvdb=tvdb, season=season, episode=episode)
			elif items[select][1] == 'hideItem':
				hideItem(name=name, imdb=imdb, tvdb=tvdb, season=season, episode=episode, tvshow=tvshow)
			elif items[select][1] == 'hiddenManager':
				control.execute('RunPlugin(plugin://plugin.video.eternity/?action=shows_traktHiddenManager)')
			elif items[select][1] == 'unfinishedEpisodeManager':
				control.execute('RunPlugin(plugin://plugin.video.eternity/?action=episodes_traktUnfinishedManager)')
			elif items[select][1] == 'unfinishedMovieManager':
				control.execute('RunPlugin(plugin://plugin.video.eternity/?action=movies_traktUnfinishedManager)')
			elif items[select][1] == 'scrobbleReset':
				scrobbleReset(imdb=imdb, tmdb='', tvdb=tvdb, season=season, episode=episode)
			else:
				# Collection/Watchlist/List operations
				if not tvdb:
					post = {"movies": [{"ids": {"imdb": imdb}}]}
				else:
					if episode:
						if items[select][1] == '/sync/watchlist' or items[select][1] == '/sync/watchlist/remove':
							post = {"shows": [{"ids": {"tvdb": tvdb}}]}
						else:
							post = {"shows": [{"ids": {"tvdb": tvdb}, "seasons": [{"number": season, "episodes": [{"number": episode}]}]}]}
							name = name + ' - ' + '%sx%02d' % (season, episode)
					elif season:
						if items[select][1] == '/sync/watchlist' or items[select][1] == '/sync/watchlist/remove':
							post = {"shows": [{"ids": {"tvdb": tvdb}}]}
						else:
							post = {"shows": [{"ids": {"tvdb": tvdb}, "seasons": [{"number": season}]}]}
							name = name + ' - ' + 'Season %s' % season
					else:
						post = {"shows": [{"ids": {"tvdb": tvdb}}]}

				if items[select][1] == '/users/me/lists/%s/items':
					slug = listAdd(successNotification=True)
					if slug: getTrakt(items[select][1] % slug, post=post)
				else:
					getTrakt(items[select][1], post=post)

				control.hide()
				list_name = re.search(r'\[B\](.+?)\[/B\]', items[select][0]).group(1) if '[B]' in items[select][0] else 'Trakt'
				message = 'Removed from' if 'remove' in items[select][1] else 'Added to'

				if refresh: control.refresh()
				control.trigger_widget_refresh()  # Umbrella compatibility - refresh widgets

				if getSetting('trakt.general.notifications') == 'true':
					control.infoDialog(title=name, message='%s (%s)' % (message, list_name))

	except Exception as e:
		control.log('TRAKT: manager Error: %s' % str(e))
		control.hide()

def listAdd(successNotification=True):
	"""Create new Trakt list"""
	try:
		k = control.keyboard('', 'Enter List Name')
		k.doModal()
		new = k.getText() if k.isConfirmed() else None
		if not new: return None

		result = getTrakt('/users/me/lists', post={"name": new, "privacy": "private"})
		if result:
			slug = result.json()['ids']['slug']
			if successNotification:
				control.infoDialog(title='Trakt', message='List Created Successfully')
			return slug
		else:
			control.infoDialog(title='Trakt', message='Failed to Create List')
			return None
	except:
		control.infoDialog(title='Trakt', message='Failed to Create List')
		return None

def rate(imdb=None, tvdb=None, season=None, episode=None):
	"""Rate content using script.trakt addon"""
	return _rating(action='rate', imdb=imdb, tvdb=tvdb, season=season, episode=episode)

def unrate(imdb=None, tvdb=None, season=None, episode=None):
	"""Remove rating using script.trakt addon"""
	return _rating(action='unrate', imdb=imdb, tvdb=tvdb, season=season, episode=episode)

def _rating(action, imdb=None, tvdb=None, season=None, episode=None):
	"""Internal rating function"""
	control.busy()
	try:
		addon = 'script.trakt'
		if control.condVisibility('System.HasAddon(%s)' % addon):
			import importlib.util
			data = {}
			data['action'] = action

			if tvdb:
				data['video_id'] = tvdb
				if episode:
					data['media_type'] = 'episode'
					data['dbid'] = 1
					data['season'] = int(season)
					data['episode'] = int(episode)
				elif season:
					data['media_type'] = 'season'
					data['dbid'] = 5
					data['season'] = int(season)
				else:
					data['media_type'] = 'show'
					data['dbid'] = 2
			else:
				data['video_id'] = imdb
				data['media_type'] = 'movie'
				data['dbid'] = 4

			# Call script.trakt's rating functionality
			script_path = control.joinPath(control.addonPath(addon), 'resources', 'lib', 'sqlitequeue.py')
			spec = importlib.util.spec_from_file_location("sqlitequeue.py", script_path)
			sqlitequeue = importlib.util.module_from_spec(spec)
			spec.loader.exec_module(sqlitequeue)
			data = {'action': 'manualRating', 'ratingData': data}
			sqlitequeue.SqliteQueue().append(data)
		else:
			control.infoDialog(title='Trakt', message='script.trakt addon not installed')
		control.hide()
	except Exception as e:
		control.log('TRAKT: _rating Error: %s' % str(e))
		control.hide()

def hideItem(name, imdb=None, tvdb=None, season=None, episode=None, refresh=True, tvshow=None):
	"""Hide item from progress/calendar"""
	success = None
	try:
		sections = ['progress_watched', 'calendar']
		sections_display = ['Progress', 'Calendar', 'Both']
		selection = control.selectDialog([i for i in sections_display], heading='Hide From')

		if selection == -1: return

		control.busy()

		if episode:
			post = {"shows": [{"ids": {"tvdb": tvdb}}]}
		elif tvshow:
			post = {"shows": [{"ids": {"tvdb": tvdb}}]}
		else:
			post = {"movies": [{"ids": {"imdb": imdb}}]}

		if selection in (0, 1):
			section = sections[selection]
			success = getTrakt('/users/hidden/%s' % section, post=post)
		else:
			for section in sections:
				success = getTrakt('/users/hidden/%s' % section, post=post)
				control.sleep(1000)

		if success:
			control.hide()
			if refresh: control.refresh()
			control.trigger_widget_refresh()  # Umbrella compatibility - refresh widgets
			if getSetting('trakt.general.notifications') == 'true':
				control.infoDialog(title='Trakt', message='Hidden: %s from %s' % (name, sections_display[selection]))
	except Exception as e:
		control.log('TRAKT: hideItem Error: %s' % str(e))

def scrobbleReset(imdb=None, tmdb='', tvdb=None, season=None, episode=None):
	"""Reset scrobble/playback position"""
	try:
		control.busy()

		# Get playback items
		playback = getTraktAsJson('/sync/playback/?extended=full')
		if not playback:
			control.hide()
			control.infoDialog(title='Trakt', message='No playback data found')
			return

		# Find matching item
		item_id = None
		for item in playback:
			if episode:
				if 'episode' in item and item.get('show', {}).get('ids', {}).get('tvdb') == tvdb:
					ep = item['episode']
					if ep.get('season') == int(season) and ep.get('number') == int(episode):
						item_id = item['id']
						break
			else:
				if 'movie' in item and item.get('movie', {}).get('ids', {}).get('imdb') == imdb:
					item_id = item['id']
					break

		if item_id:
			# Delete playback position
			url = '/sync/playback/%s' % item_id
			headers_copy = headers.copy()
			if getTraktCredentialsInfo():
				headers_copy['Authorization'] = 'Bearer %s' % getSetting('trakt.user.token')

			response = session.delete(urljoin(BASE_URL, url), headers=headers_copy, timeout=20)

			if response.status_code == 204:
				control.hide()
				if getSetting('trakt.general.notifications') == 'true':
					control.infoDialog(title='Trakt', message='Playback Position Reset')
				control.refresh()
				control.trigger_widget_refresh()  # Umbrella compatibility - refresh widgets
			else:
				control.hide()
				control.infoDialog(title='Trakt', message='Failed to Reset Playback')
		else:
			control.hide()
			control.infoDialog(title='Trakt', message='No playback data found')

	except Exception as e:
		control.log('TRAKT: scrobbleReset Error: %s' % str(e))
		control.hide()

# =============================
# SCROBBLE FUNCTIONS
# =============================

def scrobbleMovie(imdb, tmdb, watched_percent):
	"""Scrobble movie playback progress - Based on Umbrella"""
	import xbmc
	xbmc.log('[Eternity-Trakt] scrobbleMovie: imdb=%s, progress=%.1f%%' % (imdb, watched_percent), xbmc.LOGDEBUG)
	try:
		if not imdb.startswith('tt'): imdb = 'tt' + imdb
		success = getTrakt('/scrobble/pause', {"movie": {"ids": {"imdb": imdb}}, "progress": watched_percent})
		if success:
			xbmc.log('[Eternity-Trakt] Scrobble Movie Success: imdb=%s' % imdb, xbmc.LOGDEBUG)
			if getSetting('trakt.scrobble.notify') == 'true':
				control.infoDialog('Progress Saved (%.0f%%)' % watched_percent, heading='Trakt')
			return True
		else:
			xbmc.log('[Eternity-Trakt] Scrobble Movie Failed: imdb=%s' % imdb, xbmc.LOGWARNING)
			if getSetting('trakt.scrobble.notify') == 'true':
				control.infoDialog('Failed to Save Progress', heading='Trakt')
			return False
	except Exception as e:
		xbmc.log('[Eternity-Trakt] scrobbleMovie Error: %s' % str(e), xbmc.LOGERROR)
		return False

def scrobbleEpisode(imdb, tmdb, tvdb, season, episode, watched_percent):
	"""Scrobble episode playback progress - Based on Umbrella"""
	import xbmc
	xbmc.log('[Eternity-Trakt] scrobbleEpisode: tvdb=%s, S%02dE%02d, progress=%.1f%%' % (tvdb, int(season), int(episode), watched_percent), xbmc.LOGDEBUG)
	try:
		season, episode = int('%01d' % int(season)), int('%01d' % int(episode))
		success = getTrakt('/scrobble/pause', {"show": {"ids": {"tvdb": tvdb}}, "episode": {"season": season, "number": episode}, "progress": watched_percent})
		if success:
			xbmc.log('[Eternity-Trakt] Scrobble Episode Success: tvdb=%s S%02dE%02d' % (tvdb, season, episode), xbmc.LOGDEBUG)
			if getSetting('trakt.scrobble.notify') == 'true':
				control.infoDialog('Progress Saved S%02dE%02d (%.0f%%)' % (season, episode, watched_percent), heading='Trakt')
			return True
		else:
			xbmc.log('[Eternity-Trakt] Scrobble Episode Failed: tvdb=%s S%02dE%02d' % (tvdb, season, episode), xbmc.LOGWARNING)
			if getSetting('trakt.scrobble.notify') == 'true':
				control.infoDialog('Failed to Save Progress', heading='Trakt')
			return False
	except Exception as e:
		xbmc.log('[Eternity-Trakt] scrobbleEpisode Error: %s' % str(e), xbmc.LOGERROR)
		return False

# =============================
# LISTS FUNCTIONS
# =============================

def lists(id=None):
	"""Get user lists - uses Eternity's existing caching if available"""
	try:
		# Try to use existing cache mechanism if available
		from resources.lib import requestHandler
		if hasattr(requestHandler, 'cache'):
			return requestHandler.cache(getTraktAsJson, 48, '/users/me/lists' + ('' if not id else ('/' + str(id))))
		else:
			# Direct API call
			return getTraktAsJson('/users/me/lists' + ('' if not id else ('/' + str(id))))
	except:
		return getTraktAsJson('/users/me/lists' + ('' if not id else ('/' + str(id))))

def list(id):
	"""Get specific list"""
	return lists(id=id)

def slug(name):
	"""Convert name to Trakt slug format"""
	name = name.strip()
	name = name.lower()
	name = re.sub(r'[^a-z0-9_]', '-', name)
	name = re.sub(r'--+', '-', name)
	return name

# =============================
# UNFINISHED CONTENT (Phase 1.6)
# =============================

def getPlaybackProgress():
	"""
	Get ALL playback progress (movies + episodes)
	Based on Umbrella's sync_playbackProgress()
	"""
	try:
		return getTraktAsJson('/sync/playback/?extended=full')
	except:
		return None

# =============================
# MOVIE LISTS (Phase 1.5)
# =============================

def getMovieWatchlist():
	"""
	Get user's movie watchlist
	API: /users/me/watchlist/movies
	Based on Umbrella's sync_watch_list()
	"""
	try:
		# Direct API call (no cache for now - TODO: add cache system later)
		items = getTraktAsJson('/users/me/watchlist/movies?extended=full')
		if not items:
			return None

		# Return list with IDs extracted for movies.py to process
		result = []
		for i in items:
			try:
				movie = i.get('movie', {})
				ids = movie.get('ids', {})
				result.append({
					'title': movie.get('title', ''),
					'year': movie.get('year', ''),
					'imdb': ids.get('imdb', ''),
					'tmdb': ids.get('tmdb', ''),
					'trakt': ids.get('trakt', '')
				})
			except:
				pass
		return result if result else None
	except Exception as e:
		import xbmc
		xbmc.log('[Eternity-Trakt] getMovieWatchlist Error: %s' % str(e), xbmc.LOGERROR)
		return None

def getMovieCollection():
	"""
	Get user's movie collection
	API: /users/me/collection/movies
	Based on Umbrella's sync_collection()
	"""
	try:
		# Direct API call (no cache for now - TODO: add cache system later)
		items = getTraktAsJson('/users/me/collection/movies?extended=full')
		if not items:
			return None

		# Return list with IDs extracted for movies.py to process
		result = []
		for i in items:
			try:
				movie = i.get('movie', {})
				ids = movie.get('ids', {})
				result.append({
					'title': movie.get('title', ''),
					'year': movie.get('year', ''),
					'imdb': ids.get('imdb', ''),
					'tmdb': ids.get('tmdb', ''),
					'trakt': ids.get('trakt', '')
				})
			except:
				pass
		return result if result else None
	except Exception as e:
		import xbmc
		xbmc.log('[Eternity-Trakt] getMovieCollection Error: %s' % str(e), xbmc.LOGERROR)
		return None

def getMovieHistory():
	"""
	Get user's movie watch history
	API: /users/me/history/movies
	Based on Umbrella's movies.py trakthistory_link
	"""
	try:
		# Direct API call (no cache for now - TODO: add cache system later)
		items = getTraktAsJson('/users/me/history/movies?extended=full&limit=100')
		if not items:
			return None

		# Return list with IDs extracted for movies.py to process
		result = []
		for i in items:
			try:
				movie = i.get('movie', {})
				ids = movie.get('ids', {})
				result.append({
					'title': movie.get('title', ''),
					'year': movie.get('year', ''),
					'imdb': ids.get('imdb', ''),
					'tmdb': ids.get('tmdb', ''),
					'trakt': ids.get('trakt', '')
				})
			except:
				pass
		return result if result else None
	except Exception as e:
		import xbmc
		xbmc.log('[Eternity-Trakt] getMovieHistory Error: %s' % str(e), xbmc.LOGERROR)
		return None

# =============================
# TV SHOW LISTS (Phase 1.5 - TV)
# =============================

def getTVWatchlist():
	"""
	Get user's TV show watchlist
	API: /users/me/watchlist/shows
	"""
	try:
		# Direct API call
		items = getTraktAsJson('/users/me/watchlist/shows?extended=full')
		if not items:
			return None

		# Return list with IDs extracted
		result = []
		for i in items:
			try:
				show = i.get('show', {})
				ids = show.get('ids', {})
				result.append({
					'title': show.get('title', ''),
					'year': show.get('year', ''),
					'imdb': ids.get('imdb', ''),
					'tmdb': ids.get('tmdb', ''),
					'tvdb': ids.get('tvdb', ''),
					'trakt': ids.get('trakt', '')
				})
			except:
				pass
		return result if result else None
	except Exception as e:
		import xbmc
		xbmc.log('[Eternity-Trakt] getTVWatchlist Error: %s' % str(e), xbmc.LOGERROR)
		return None

def getTVCollection():
	"""
	Get user's TV show collection
	API: /users/me/collection/shows
	"""
	try:
		# Direct API call
		items = getTraktAsJson('/users/me/collection/shows?extended=full')
		if not items:
			return None

		# Return list with IDs extracted
		result = []
		for i in items:
			try:
				show = i.get('show', {})
				ids = show.get('ids', {})
				result.append({
					'title': show.get('title', ''),
					'year': show.get('year', ''),
					'imdb': ids.get('imdb', ''),
					'tmdb': ids.get('tmdb', ''),
					'tvdb': ids.get('tvdb', ''),
					'trakt': ids.get('trakt', '')
				})
			except:
				pass
		return result if result else None
	except Exception as e:
		import xbmc
		xbmc.log('[Eternity-Trakt] getTVCollection Error: %s' % str(e), xbmc.LOGERROR)
		return None

def getTVHistory():
	"""
	Get user's TV show watch history
	API: /users/me/history/shows
	"""
	try:
		# Direct API call
		items = getTraktAsJson('/users/me/history/shows?extended=full&limit=100')
		if not items:
			return None

		# Return list with IDs extracted
		result = []
		for i in items:
			try:
				show = i.get('show', {})
				ids = show.get('ids', {})
				result.append({
					'title': show.get('title', ''),
					'year': show.get('year', ''),
					'imdb': ids.get('imdb', ''),
					'tmdb': ids.get('tmdb', ''),
					'tvdb': ids.get('tvdb', ''),
					'trakt': ids.get('trakt', '')
				})
			except:
				pass
		return result if result else None
	except Exception as e:
		import xbmc
		xbmc.log('[Eternity-Trakt] getTVHistory Error: %s' % str(e), xbmc.LOGERROR)
		return None

def getContinueWatching():
	"""
	Get shows to continue watching (shows with unfinished episodes)
	This returns the SHOWS that have playback progress, not individual episodes
	API: /sync/playback/episodes (then group by show)
	"""
	try:
		import xbmc
		# Get unfinished episodes
		items = getTraktAsJson('/sync/playback/episodes?extended=full&limit=50')
		if not items:
			return None

		# Group by show (avoid duplicates)
		shows_seen = set()
		result = []

		for i in items:
			try:
				show = i.get('show', {})
				ids = show.get('ids', {})
				tvdb = ids.get('tvdb', '')

				# Skip if we've already added this show
				if tvdb in shows_seen:
					continue

				shows_seen.add(tvdb)

				result.append({
					'title': show.get('title', ''),
					'year': show.get('year', ''),
					'imdb': ids.get('imdb', ''),
					'tmdb': ids.get('tmdb', ''),
					'tvdb': tvdb,
					'trakt': ids.get('trakt', '')
				})
			except:
				pass

		xbmc.log('[Eternity-Trakt] getContinueWatching: Found %d shows' % len(result), xbmc.LOGINFO)
		return result if result else None
	except Exception as e:
		import xbmc
		xbmc.log('[Eternity-Trakt] getContinueWatching Error: %s' % str(e), xbmc.LOGERROR)
		return None

def getUnfinishedMovies():
	"""
	Get unfinished movies (< 90% watched)
	API: /sync/playback/movies
	"""
	try:
		items = getTraktAsJson('/sync/playback/movies?extended=full&limit=50')
		if not items: return None
		# Filter: Only items with progress < 90
		unfinished = [i for i in items if i.get('progress', 0) < 90]
		return unfinished if unfinished else None
	except Exception as e:
		control.log('TRAKT: getUnfinishedMovies Error: %s' % str(e))
		return None

def getUnfinishedEpisodes():
	"""
	Get unfinished episodes (< 90% watched)
	API: /sync/playback/episodes
	"""
	try:
		items = getTraktAsJson('/sync/playback/episodes?extended=full&limit=50')
		if not items: return None
		# Filter: Only items with progress < 90
		unfinished = [i for i in items if i.get('progress', 0) < 90]
		return unfinished if unfinished else None
	except Exception as e:
		control.log('TRAKT: getUnfinishedEpisodes Error: %s' % str(e))
		return None

# =============================
# PROGRESS/CONTINUE WATCHING (Phase 1.7)
# =============================

def getShowProgress(tvdb):
	"""
	Get show progress - next episode to watch
	API: /shows/{id}/progress/watched
	"""
	try:
		if not tvdb: return None
		url = '/shows/%s/progress/watched?extended=full&hidden=false&specials=false' % tvdb
		return getTraktAsJson(url)
	except Exception as e:
		control.log('TRAKT: getShowProgress Error: %s' % str(e))
		return None

def getProgressWatching():
	"""
	Get progress watching (next episodes to watch per show)
	FULL UMBRELLA IMPLEMENTATION - Calculates next episode with TMDB metadata
	Based on Umbrella's episodes.trakt_progress_list()
	"""
	try:
		from resources.lib.tmdb_kodi import TMDBApi
		from concurrent.futures import ThreadPoolExecutor
		import datetime

		# Get watched shows from Trakt
		items = getTraktAsJson('/users/me/watched/shows?extended=full')
		if not items: return None

		progress_items = []
		tmdb_api = TMDBApi(language='de')
		today_date = datetime.datetime.now().strftime('%Y-%m-%d')

		# Phase 1: Extract basic show info and calculate last watched episode
		for item in items:
			try:
				show = item.get('show', {})

				# Check if show is fully watched (ended shows only)
				if show.get('status', '').lower() == 'ended':
					watched_count = 0
					for season in item.get('seasons', []):
						if season.get('number', 0) > 0:  # Skip specials
							watched_count += len(season.get('episodes', []))
					aired_episodes = show.get('aired_episodes', 0)
					if watched_count >= aired_episodes:
						continue  # Skip fully watched ended shows

				# Sort seasons to handle Trakt's inconsistent ordering
				seasons = sorted(item.get('seasons', []), key=lambda k: k.get('number', 0), reverse=False)
				if not seasons: continue

				# Get last watched season and episode
				last_season = seasons[-1]
				last_season_num = last_season.get('number', 0)

				episodes = [x for x in last_season.get('episodes', []) if 'number' in x]
				episodes = sorted(episodes, key=lambda x: x.get('number', 0))
				if not episodes: continue

				last_episode_num = episodes[-1].get('number', 0)

				# Extract show IDs
				ids = show.get('ids', {})
				imdb = str(ids.get('imdb', '')) if ids.get('imdb') else ''
				tmdb = str(ids.get('tmdb', '')) if ids.get('tmdb') else ''
				tvdb = str(ids.get('tvdb', '')) if ids.get('tvdb') else ''

				if not tmdb:
					continue  # Need TMDB ID for metadata

				progress_items.append({
					'tvshowtitle': show.get('title', ''),
					'imdb': imdb,
					'tmdb': tmdb,
					'tvdb': tvdb,
					'last_season': last_season_num,
					'last_episode': last_episode_num,
					'lastplayed': item.get('last_watched_at', ''),
					'status': show.get('status', ''),
					'airday': show.get('airs', {}).get('day', ''),
					'airtime': show.get('airs', {}).get('time', '')[:5] if show.get('airs', {}).get('time') else '',
					'airzone': show.get('airs', {}).get('timezone', ''),
				})
			except:
				pass

		if not progress_items:
			return None

		# Phase 2: Calculate next episode and fetch TMDB metadata (threaded)
		def process_show(show_info):
			try:
				tmdb_id = show_info['tmdb']
				last_season = show_info['last_season']
				last_episode = show_info['last_episode']

				# Get show details from TMDB
				show_details = tmdb_api.get_tv_show(tmdb_id)
				if not show_details:
					return None

				total_seasons = show_details.get('number_of_seasons', 0)

				# Get current season details
				season_details = tmdb_api.get_season_details(tmdb_id, last_season)
				if not season_details:
					return None

				episode_count = len(season_details.get('episodes', []))

				# Calculate next episode
				if last_episode < episode_count:
					# Next episode in same season
					next_season = last_season
					next_episode = last_episode + 1
				else:
					# Next season
					next_season = last_season + 1
					next_episode = 1

				# Check if next season exists
				if next_season > total_seasons:
					return None  # Show fully watched

				# Get next episode metadata
				episode_details = tmdb_api.get_episode_details(tmdb_id, next_season, next_episode)
				if not episode_details:
					return None

				# Check if episode has aired
				premiered = episode_details.get('air_date', '')
				if premiered:
					try:
						aired_date_int = int(premiered.replace('-', ''))
						today_date_int = int(today_date.replace('-', ''))
						if aired_date_int > today_date_int:
							# Episode hasn't aired yet - mark as unaired but include it
							episode_details['unaired'] = 'true'
					except:
						pass

				# Merge all metadata
				result = {
					'tvshowtitle': show_info['tvshowtitle'],
					'title': episode_details.get('name', 'Episode %d' % next_episode),
					'season': next_season,
					'episode': next_episode,
					'imdb': show_info['imdb'],
					'tmdb': tmdb_id,
					'tvdb': show_info['tvdb'],
					'premiered': premiered,
					'plot': episode_details.get('overview', show_details.get('overview', '')),
					'rating': episode_details.get('vote_average', 0),
					'votes': episode_details.get('vote_count', 0),
					'poster': show_details.get('poster_path', ''),
					'fanart': show_details.get('backdrop_path', ''),
					'status': show_info['status'],
					'airday': show_info['airday'],
					'airtime': show_info['airtime'],
					'airzone': show_info['airzone'],
					'lastplayed': show_info['lastplayed'],
					'duration': episode_details.get('runtime', show_details.get('episode_run_time', [45])[0]) * 60,
					'unaired': episode_details.get('unaired', ''),
					'traktProgress': True,  # Flag for UI
				}

				return result
			except:
				return None

		# Process all shows with ThreadPoolExecutor
		final_list = []
		with ThreadPoolExecutor(max_workers=10) as executor:
			results = executor.map(process_show, progress_items)
			final_list = [r for r in results if r is not None]

		return final_list if final_list else None

	except Exception as e:
		control.log('TRAKT: getProgressWatching Error: %s' % str(e))
		return None

# =============================
# RECOMMENDATIONS (Phase 1.8)
# =============================

def getRecommendedMovies():
	"""
	Get recommended movies
	API: /recommendations/movies
	"""
	try:
		return getTraktAsJson('/recommendations/movies?limit=40&extended=full')
	except Exception as e:
		control.log('TRAKT: getRecommendedMovies Error: %s' % str(e))
		return None

def getRecommendedShows():
	"""
	Get recommended TV shows
	API: /recommendations/shows
	"""
	try:
		return getTraktAsJson('/recommendations/shows?limit=40&extended=full')
	except Exception as e:
		control.log('TRAKT: getRecommendedShows Error: %s' % str(e))
		return None

# =============================
# LIKED LISTS (Phase 1.9)
# =============================

def getLikedLists():
	"""
	Get lists user has liked
	API: /users/likes/lists
	"""
	try:
		return getTraktAsJson('/users/likes/lists?limit=1000')
	except Exception as e:
		control.log('TRAKT: getLikedLists Error: %s' % str(e))
		return None

def getListItems(list_owner, list_id, content_type='movies'):
	"""
	Get items from a specific Trakt list
	API: /users/{owner}/lists/{id}/items/{type}
	Based on Umbrella's list_link pattern

	Args:
		list_owner: Username of list owner (slug)
		list_id: List ID (slug)
		content_type: 'movies' or 'shows'
	"""
	try:
		import xbmc

		# Build API endpoint
		endpoint = '/users/%s/lists/%s/items/%s?extended=full' % (list_owner, list_id, content_type)
		xbmc.log('[Eternity-Trakt] getListItems: Fetching %s' % endpoint, xbmc.LOGINFO)

		# Direct API call
		items = getTraktAsJson(endpoint)
		if not items:
			return None

		# Return list with IDs extracted (same format as getMovieWatchlist)
		result = []
		for i in items:
			try:
				if content_type == 'movies':
					movie = i.get('movie', {})
					ids = movie.get('ids', {})
					result.append({
						'title': movie.get('title', ''),
						'year': movie.get('year', ''),
						'imdb': ids.get('imdb', ''),
						'tmdb': ids.get('tmdb', ''),
						'trakt': ids.get('trakt', '')
					})
				elif content_type == 'shows':
					show = i.get('show', {})
					ids = show.get('ids', {})
					result.append({
						'title': show.get('title', ''),
						'year': show.get('year', ''),
						'imdb': ids.get('imdb', ''),
						'tmdb': ids.get('tmdb', ''),
						'tvdb': ids.get('tvdb', ''),
						'trakt': ids.get('trakt', '')
					})
			except:
				pass

		xbmc.log('[Eternity-Trakt] getListItems: Returned %d items' % len(result), xbmc.LOGINFO)
		return result if result else None

	except Exception as e:
		import xbmc
		xbmc.log('[Eternity-Trakt] getListItems Error: %s' % str(e), xbmc.LOGERROR)
		return None

def likeList(list_owner, list_name, list_id):
	"""
	Like a public list
	API: POST /users/{owner}/lists/{id}/like
	"""
	try:
		headers_copy = headers.copy()
		if getTraktCredentialsInfo():
			headers_copy['Authorization'] = 'Bearer %s' % getSetting('trakt.user.token')

		url = urljoin(BASE_URL, '/users/%s/lists/%s/like' % (list_owner, list_id))
		resp_code = session.post(url, headers=headers_copy).status_code

		if resp_code == 204:
			control.infoDialog(title='Trakt', message='Successfully Liked list: %s' % list_name)
			return True
		else:
			control.infoDialog(title='Trakt', message='Failed to Like list %s' % list_name)
			return False
	except Exception as e:
		control.log('TRAKT: likeList Error: %s' % str(e))
		return False

def unlikeList(list_owner, list_name, list_id):
	"""
	Unlike a public list
	API: DELETE /users/{owner}/lists/{id}/like
	"""
	try:
		headers_copy = headers.copy()
		if getTraktCredentialsInfo():
			headers_copy['Authorization'] = 'Bearer %s' % getSetting('trakt.user.token')

		url = urljoin(BASE_URL, '/users/%s/lists/%s/like' % (list_owner, list_id))
		resp_code = session.delete(url, headers=headers_copy).status_code

		if resp_code == 204:
			control.infoDialog(title='Trakt', message='Successfully Unliked list: %s' % list_name)
			return True
		else:
			control.infoDialog(title='Trakt', message='Failed to Unlike list %s' % list_name)
			return False
	except Exception as e:
		control.log('TRAKT: unlikeList Error: %s' % str(e))
		return False

# =============================
# ACTIVITY SYNC (Phase 1.10)
# =============================

def getActivity():
	"""
	Get all activity timestamps (for efficient sync)
	API: /sync/last_activities
	"""
	try:
		i = getTraktAsJson('/sync/last_activities')
		if not i: return 0

		activity = []
		activity.append(i['movies']['watched_at'])
		activity.append(i['movies']['collected_at'])
		activity.append(i['movies']['watchlisted_at'])
		activity.append(i['movies']['paused_at'])
		activity.append(i['movies']['hidden_at'])
		activity.append(i['episodes']['watched_at'])
		activity.append(i['episodes']['collected_at'])
		activity.append(i['episodes']['watchlisted_at'])
		activity.append(i['episodes']['paused_at'])
		activity.append(i['shows']['watchlisted_at'])
		activity.append(i['shows']['hidden_at'])
		activity.append(i['seasons']['watchlisted_at'])
		activity.append(i['seasons']['hidden_at'])
		activity.append(i['lists']['liked_at'])
		activity.append(i['lists']['updated_at'])

		# Convert ISO dates to Unix timestamps and get latest
		from datetime import datetime
		activity = [int(datetime.fromisoformat(a.replace('Z', '+00:00')).timestamp()) for a in activity]
		activity = sorted(activity, key=int)[-1]
		return activity
	except Exception as e:
		control.log('TRAKT: getActivity Error: %s' % str(e))
		return 0

def getHiddenActivity(activities=None):
	"""Get hidden items activity"""
	try:
		if activities:
			i = activities
		else:
			i = getTraktAsJson('/sync/last_activities')
		if not i: return 0

		activity = []
		activity.append(i['movies']['hidden_at'])
		activity.append(i['shows']['hidden_at'])
		activity.append(i['seasons']['hidden_at'])

		from datetime import datetime
		activity = [int(datetime.fromisoformat(a.replace('Z', '+00:00')).timestamp()) for a in activity]
		activity = sorted(activity, key=int)[-1]
		return activity
	except:
		return 0

def getWatchedActivity(activities=None):
	"""Get watched activity (movies + episodes)"""
	try:
		if activities:
			i = activities
		else:
			i = getTraktAsJson('/sync/last_activities')
		if not i: return 0

		activity = []
		activity.append(i['movies']['watched_at'])
		activity.append(i['episodes']['watched_at'])

		from datetime import datetime
		activity = [int(datetime.fromisoformat(a.replace('Z', '+00:00')).timestamp()) for a in activity]
		activity = sorted(activity, key=int)[-1]
		return activity
	except:
		return 0

def getCollectedActivity(activities=None):
	"""Get collection activity"""
	try:
		if activities:
			i = activities
		else:
			i = getTraktAsJson('/sync/last_activities')
		if not i: return 0

		activity = []
		activity.append(i['movies']['collected_at'])
		activity.append(i['episodes']['collected_at'])

		from datetime import datetime
		activity = [int(datetime.fromisoformat(a.replace('Z', '+00:00')).timestamp()) for a in activity]
		activity = sorted(activity, key=int)[-1]
		return activity
	except:
		return 0

def getWatchlistedActivity(activities=None):
	"""Get watchlist activity"""
	try:
		if activities:
			i = activities
		else:
			i = getTraktAsJson('/sync/last_activities')
		if not i: return 0

		activity = []
		activity.append(i['movies']['watchlisted_at'])
		activity.append(i['shows']['watchlisted_at'])
		activity.append(i['seasons']['watchlisted_at'])
		activity.append(i['episodes']['watchlisted_at'])

		from datetime import datetime
		activity = [int(datetime.fromisoformat(a.replace('Z', '+00:00')).timestamp()) for a in activity]
		activity = sorted(activity, key=int)[-1]
		return activity
	except:
		return 0

def getPausedActivity(activities=None):
	"""Get paused/playback activity"""
	try:
		if activities:
			i = activities
		else:
			i = getTraktAsJson('/sync/last_activities')
		if not i: return 0

		activity = []
		activity.append(i['movies']['paused_at'])
		activity.append(i['episodes']['paused_at'])

		from datetime import datetime
		activity = [int(datetime.fromisoformat(a.replace('Z', '+00:00')).timestamp()) for a in activity]
		activity = sorted(activity, key=int)[-1]
		return activity
	except:
		return 0

def getListActivity(activities=None):
	"""Get list activity"""
	try:
		if activities:
			i = activities
		else:
			i = getTraktAsJson('/sync/last_activities')
		if not i: return 0

		activity = []
		activity.append(i['lists']['liked_at'])
		activity.append(i['lists']['updated_at'])

		from datetime import datetime
		activity = [int(datetime.fromisoformat(a.replace('Z', '+00:00')).timestamp()) for a in activity]
		activity = sorted(activity, key=int)[-1]
		return activity
	except:
		return 0

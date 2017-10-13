import threading
from time import sleep
import hmac
from hashlib import sha256
import requests
import sys

def threaded(fn):
    def wrapper(*args, **kwargs):
        thread = threading.Thread(target=fn, args=args, kwargs=kwargs)
        thread.setDaemon(True)
        thread.start()
        return thread
    return wrapper

# 34 page not found
# 44 invalid parameter
# 50 user not found
# 87 not permitted to access user
# 500 internal server error
# 403 out of scope
class InstagramError(Exception):
    def __init__(self,*args,**kwargs):
        self.code = kwargs.pop('code', 500)
        Exception.__init__(self,*args,**kwargs)

class InstaPy:
    
    def __init__(self, tokens, client_secret, *args, **kwargs):
        self.tokens = tokens
        self.client_secret = client_secret
        self.maxCalls = kwargs.pop('maxCalls', float('inf'))
        self.maxTries = kwargs.pop('maxTries', 3)
        self.limited = [False for _ in self.tokens]
        self.timers = [False for _ in self.tokens]
        self.cycle = 0
        self.calls = 0
        self.available = threading.Event()

    # timer begins running as soon as the token is used, rate limits are refreshed after an hour
    @threaded
    def cycleTimer(self, limitedCycle, available):
        self.timers[limitedCycle] = True
        sleep(60*60+1)
        self.limited[limitedCycle] = False
        self.timers[limitedCycle] = False
        available.set()
    
    # called when getting the currently active token
    @property
    def token(self):
        if (self.calls > self.maxCalls):
            print("Used token  over {} times, cycling".format(self.maxCalls))
            self.cycleTokens()
        if (not self.timers[self.cycle]):
            self.cycleTimer(self.cycle, self.available)
        self.calls +=1
        return(self.tokens[self.cycle])

    def hitLimit(self):
        print("Attempting to cycle tokens")
        self.limited[self.cycle] = True
        return self.cycleTokens()

    def cycleTokens(self):
        # if all the tokens are limited wait for one to open
        if (not False in self.limited):
            print("Waiting for a token to open")
            self.available.clear()
            while not self.available.wait(1):
                pass
        # find the open token
        for c, limit in enumerate(self.limited):
            if (not limit):
                self.cycle = c
                break
        self.calls = 0
        print("Token cycled")
    
    # generates a signed request url
    def _generateUrl(self, endpoint, params = {}, *args, **kwargs):
        token = kwargs.pop('token', self.token)
        params['access_token'] = token
        url_base = kwargs.pop('url_base', 'https://api.instagram.com/v1/')
        sig = endpoint
        for key in sorted(params.keys()):
            sig += '|%s=%s' % (key, params[key])
        final_sig = hmac.new(self.client_secret, sig, sha256).hexdigest()
        return '{}{}?{}&sig={}'.format(url_base,
                                       endpoint,
                                       '&'.join(['{}={}'.format(key, params[key]) for key in params]),
                                       final_sig)
    
    # makes each request `maxTries` times then returns the result
    def _makeRequest(self, endpoint, params = None, *args, **kwargs):
        sus = kwargs.get('sus', 60)
        headers = kwargs.pop('headers', {})
        token = kwargs.pop('token', False)
        if not params:
            params = {}
        params.update(kwargs)
        url = self._generateUrl(endpoint, params, *args, **kwargs)
        t = 0
        while t < self.maxTries:
            t += 1
            try:
                r = requests.get(url, headers = headers)
            except requests.exceptions.SSLError as e:
                print("SSLError, trying again")
                continue
            except requests.exceptions.ConnectionError as e:
                print("ConnectionError, trying again")
                continue

            if (r.status_code == 200):
                break
            elif (r.status_code == 429):
                print('Hit rate limit')
                # if the request includes a set `token` do not cycle tokens when limited
                if token:
                    break
                else:
                    if (self.hitLimit()):
                        continue
                    else:
                        break
            elif (r.status_code == 400):
                if (r.json()['meta']['error_type'] == 'OAuthPermissionsException'):
                    raise InstagramError('The current authentication token ({}) is not permitted to perform this action.'.format(), code = 403)
                if (r.json()['meta']['error_type'] == 'APINotAllowedError'):
                    raise InstagramError('Instagram will not allow you to view this resource', code = 87)
                elif (r.json()['meta']['error_type'] == 'APINotFoundError'):
                    raise InstagramError('Instagram cannot find this resource ', code = 34)
                elif (r.json()['meta']['error_type'] == 'APIInvalidParametersError'):
                    raise InstagramError('One or more of your parameters was invalid: {}'.format(r.json()['meta']['error_message']), code = 44)
                else:
                    print r.json()
                    print('Instagram is getting suspicious, waiting {} seconds then trying again.'.format(sus))
                # wait `sus` seconds then make the same call again
                sleep(sus)
                continue
        return r
    
    def self_followed_by(self, token, count = float('inf'), *args, **kwargs):
        # start from the cursor in case a collection was interrupted
        cursor = kwargs.pop('cursor', None)
        breakOnLimit = kwargs.pop('breakOnLimit', True)
        followers = []
        endpoint = "users/self/followed-by"
        params = {}

        while True:
            if (cursor):
                params['cursor'] = cursor

            r = self._makeRequest(endpoint, params, token = token, *args, **kwargs)
            if (r.status_code == 429):
                if (cursor):
                    print('Current Cursor: {}'.format(cursor))
                if (breakOnLimit):
                    return(followers)
                else:
                    sleep(60*60+1)
                    continue
            elif (r.status_code != 200):
                raise InstagramError('Could not connect to {} endpoint (Code: {})'.format(endpoint, r.status_code), code = 500)

            results = r.json()
            followers.extend(results['data'])
            if (len(followers) < count and results.get('pagination', False) and results['pagination'].get('next_cursor', False)):
                cursor = results['pagination']['next_cursor']
            else:
                break

        if (count < float('inf')):
            return(followers[:count])
        else:
            return(followers)
    
    def handle_to_id(self, handle, *args, **kwargs):
        endpoint = 'users/search'
        # returns 50 results, max
        params = {
            'count': 50,
            'q': handle
        }
        r = self._makeRequest(endpoint, params, *args, **kwargs)
        if (r.status_code != 200):
            raise InstagramError('Could not connect to {} endpoint (Code: {})'.format(endpoint, r.status_code), code = 500)
        results = r.json()
        for result in results['data']:
            if (handle.lower() == result['username'].lower()):
                return(result['id'])
        raise InstagramError('Could not find user: {}'.format(handle), code = 50)
        
    def recent_media(self, *args, **kwargs):
        self.media_recent(*args, **kwargs)
    
    def media_recent(self, user, count = 33, *args, **kwargs):
        # start from the cursor in case a collection was interrupted
        cursor = kwargs.pop('cursor', None)
        media = []
        endpoint = 'users/{}/media/recent'.format(user)
        # returns 33 results, max--rounding to 35
        params = {
            'count': 35,
        }
        while True:
            if (cursor):
                params['max_id'] = cursor
                
            try:
                r = self._makeRequest(endpoint, params, *args, **kwargs)
            except KeyboardInterrupt:
                print("Exiting...")
                break
            if (r.status_code != 200):
                raise InstagramError('Could not connect to {} endpoint (Code: {})'.format(endpoint, r.status_code), code = 500)
            
            results = r.json()
            media.extend(results['data'])
            if (len(media) < count and results.get('pagination', False) and results['pagination'].get('next_max_id', False)):
                cursor = results['pagination']['next_max_id']
            else:
                break
                
        if (count < float('inf')):
            return(media[:count])
        else:
            return(media)
        
    def media_comments(self, media_id, *args, **kwargs):
        endpoint = 'media/{}/comments'.format(media_id)
        r = self._makeRequest(endpoint, *args, **kwargs)
        if (r.status_code != 200):
            raise InstagramError('Could not connect to {} endpoint (Code: {})'.format(endpoint, r.status_code), code = 500)
        
        results = r.json()
        return(results['data'])
    
    def media_likes(self, media_id, *args, **kwargs):
        endpoint = 'media/{}/likes'.format(media_id)
        r = self._makeRequest(endpoint, *args, **kwargs)
        if (r.status_code != 200):
            raise InstagramError('Could not connect to {} endpoint (Code: {})'.format(endpoint, r.status_code), code = 500)
        
        results = r.json()
        return(results['data'])
    
    def media(self, media_id, *args, **kwargs):
        endpoint = 'media/shortcode/{}'.format(media_id)
        if (media_id.isdigit() and len(media_id) > 11):
            endpoint = 'media/{}'.format(media_id)
        r = self._makeRequest(endpoint, *args, **kwargs)
        if (r.status_code != 200):
            raise InstagramError('Could not connect to {} endpoint (Code: {})'.format(endpoint, r.status_code), code = 500)
        
        results = r.json()
        return(results['data'])

    def locations_search(self, lat, lng, distance = 500, *args, **kwargs):
        endpoint = 'locations/search'
        params = {
            'lat': lat,
            'lng': lng,
            'distance': distance,
            'facebook_places_id': kwargs.pop('facebook_places_id', None)
        }
        r = self._makeRequest(endpoint, params, *args, **kwargs)
        if (r.status_code != 200):
            raise InstagramError('Could not connect to {} endpoint (Code: {})'.format(endpoint, r.status_code), code = 500)
        
        results = r.json()
        return(results['data'])

    def locations_media_recent(self, location_id, count = 15, *args, **kwargs):
        # start from the cursor in case a collection was interrupted
        cursor = kwargs.pop('cursor', None)
        media = []
        params = {}
        endpoint = 'locations/{}/media/recent'.format(location_id)
        while True:
            if (cursor):
                params['max_id'] = cursor
            
            try:
                r = self._makeRequest(endpoint, params, *args, **kwargs)
            except KeyboardInterrupt:
                print("Exiting...")
                break

            if (r.status_code != 200):
                raise InstagramError('Could not connect to {} endpoint (Code: {})'.format(endpoint, r.status_code), code = 500)
            
            results = r.json()
            media.extend(results['data'])
            if len(media) < count and results.get('pagination', False) and results['pagination'].get('next_max_id', False) and len(results['data']) > 0:
                cursor = results['pagination']['next_max_id']
            else:
                break
                
        if (count < float('inf')):
            return(media[:count])
        else:
            return(media)

    def locations(self, location_id, *args, **kwargs):
        endpoint = 'locations/{}'.format(location_id)
        r = self._makeRequest(endpoint, *args, **kwargs)
        if (r.status_code != 200):
            raise InstagramError('Could not connect to {} endpoint (Code: {})'.format(endpoint, r.status_code), code = 500)
        
        results = r.json()
        return(results['data'])

    def tag_media_recent(self, tag, count = 33, *args, **kwargs):
        # start from the cursor in case a collection was interrupted
        cursor = kwargs.pop('cursor', None)
        media = []
        endpoint = 'tags/{}/media/recent'.format(tag)
        # returns 33 results, max--rounding to 35
        params = {
            'count': 35,
        }
        while True:
            if (cursor):
                params['max_id'] = cursor
                
            try:
                r = self._makeRequest(endpoint, params, *args, **kwargs)
            except KeyboardInterrupt:
                print("Exiting...")
                break
            if (r.status_code != 200):
                raise InstagramError('Could not connect to {} endpoint (Code: {})'.format(endpoint, r.status_code), code = 500)
            
            results = r.json()
            media.extend(results['data'])
            if (len(media) < count and results.get('pagination', False) and results['pagination'].get('next_max_id', False)):
                cursor = results['pagination']['next_max_id']
            else:
                break
                
        if (count < float('inf')):
            return(media[:count])
        else:
            return(media)
    
    # experimental story endpoints
    def all_stories(self, session_id, *args, **kwargs):
        headers = {
            'cookie' : 'sessionid={}'.format(session_id),
            'user-agent' : 'Instagram 10.26.0 (iPhone7,2; iOS 10_1_1; en_US; en-US; scale=2.00; gamut=normal; 750x1334) AppleWebKit/420+',
            'x-ig-capabilities': '36oD'
        }
        endpoint = 'feed/reels_tray'
        r = self._makeRequest(endpoint, url_base = 'https://i.instagram.com/api/v1/', headers = headers, *args, **kwargs)
        if (r.status_code != 200):
            raise InstagramError('Could not connect to {} endpoint (Code: {})'.format(endpoint, r.status_code), code = 500)
        
        results = r.json()
        return(results)


    def user_story(self, user_id, session_id, *args, **kwargs):
        headers = {
            'cookie' : 'sessionid={}'.format(session_id),
            'user-agent' : 'Instagram 10.26.0 (iPhone7,2; iOS 10_1_1; en_US; en-US; scale=2.00; gamut=normal; 750x1334) AppleWebKit/420+',
            'x-ig-capabilities': '36oD'
        }
        endpoint = 'feed/user/{}/reel_media'.format(user_id)
        r = self._makeRequest(endpoint, url_base = 'https://i.instagram.com/api/v1/', headers = headers, *args, **kwargs)
        if (r.status_code != 200):
            raise InstagramError('Could not connect to {} endpoint (Code: {})'.format(endpoint, r.status_code), code = 500)
        
        results = r.json()
        return(results)

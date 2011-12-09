import cookielib
import getpass
import sys
from urllib import urlencode
import urllib2


CLIENT_LOGIN = 'https://www.google.com/accounts/ClientLogin'
SITE_COOKIE_AUTH_URL = 'http://persistent-cal.appspot.com/_ah/login?auth=%s'


def get_auth_val():
  params = {'accountType': 'GOOGLE',
            'service': 'ah',
            'source': 'persistent-cal'}
  params['Email'] = raw_input('Email address: ')
  params['Passwd'] = getpass.getpass('Password: ')
  params = urlencode(params)

  auth_cnxn = urllib2.urlopen(CLIENT_LOGIN, params)
  auth_val = auth_cnxn.read()
  auth_cnxn.close()
  return auth_val


def parse_auth_message(auth_val):
  # SID=<some text>
  # LSID=<some text>
  # Auth=<some text>
  success = True
  auth_cookie = None

  result = ['Authentication failed.']
  if 'Error=BadAuthentication' in auth_val:
    success = False
    if 'Info=InvalidSecondFactor' in auth_val:
      result.extend(['',
                     'Two factor authorization is not supported.',
                     'Please use an application specific password.'])

  auth_rows = [row for row in auth_val.split('\n') if row]
  if (len(auth_rows) != 3 or not auth_rows[0].startswith('SID=')
      or not auth_rows[1].startswith('LSID=')
      or not auth_rows[2].startswith('Auth=')):
    success = False
  else:
    auth_cookie = auth_rows[2].lstrip('Auth=')

  length = max(len(line) for line in result)
  result = ['| %s |' % line.ljust(length) for line in result]
  header = '+%s+' % ('-' * (length + 2))
  result = [header] + result + [header]

  return (success, auth_cookie, '\n'.join(result))


def get_site_cookie(auth_cookie):
  request_url = SITE_COOKIE_AUTH_URL % auth_cookie
  cookie_jar = cookielib.CookieJar()
  opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookie_jar))

  opener.open(request_url)
  acsid_cookie = None
  for cookie in cookie_jar:
    if cookie.name == 'ACSID':
      acsid_cookie = cookie
      break

  cookie_val = '' if acsid_cookie is None else acsid_cookie.value
  valid = acsid_cookie is not None
  return (valid, cookie_val)

def add_subscription(cookie_val, calendar_link):
  request = urllib2.Request('http://persistent-cal.appspot.com/add')
  request.add_header('Cookie', cookie_val)
  params = urlencode({'calendar-link': calendar_link})

  add_subs_cnxn = urllib2.urlopen(request, params)
  response_val = add_subs_cnxn.read()
  add_subs_cnxn.close()
  return response_val


success, auth_cookie, result = parse_auth_message(get_auth_val())
if not success or auth_cookie is None:
  print result
  sys.exit(1)

valid, cookie_val = get_site_cookie(auth_cookie)
if not valid:
  print 'BAD THING HAPPENED'
  sys.exit(2)

calendar_link = 'a'
response_val = add_subscription(cookie_val, calendar_link)
print response_val

#!/usr/bin/env python

# Copyright (C) 2010-2011 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Command Line Tool for persistent-cal."""


__author__ = 'dhermes@google.com (Daniel Hermes)'


import sys


# Constants
APP_ID = 'persistent-cal'
ADD_ENDPOINT = 'http://%s.appspot.com/add' % APP_ID
FREQ_ENDPOINT = 'http://%s.appspot.com/freq' % APP_ID
GETINFO_ENDPOINT = 'http://%s.appspot.com/getinfo' % APP_ID
LOGIN_ENDPOINT = 'http://%s.appspot.com/_ah/login?auth=' % APP_ID
CLIENT_LOGIN = 'https://www.google.com/accounts/ClientLogin'
APPLICATION_AUTH_URL_TEMPLATE = LOGIN_ENDPOINT + '%s'
REQUIRED_LIBRARIES = ['argparse',
                      'cookielib',
                      'getpass',
                      'simplejson',
                      'urllib',
                      'urllib2']
FREQUENCY_MAP = {56: 'three-hrs',
                 28: 'six-hrs',
                 14: 'half-day',
                 7: 'day',
                 4: 'two-day',
                 1: 'week'}
FREQUENCY_CHOICES = [str(key) for key in sorted(FREQUENCY_MAP.keys())]
ERROR_RESPONSES = {
    'add': {'whitelist:fail': ['Feed is not on whitelist.', '',
                               'See http://%s.appspot.com/about.' % APP_ID],
            'limit:fail': ['You have reached the maximum number of feeds.', '',
                           'See http://%s.appspot.com/about.' % APP_ID],
            'contained:fail': ('You are already subscribed to this '
                               'calendar feed.'),
            'no_user:fail': 'No user was provided.'},
    'chg': {'no_cal:fail': 'You have no calendar to update.',
            'wrong_freq:fail':
            ['The value given is not a valid frequency.', '',
             'This value represents the number of times per week that your',
             'personal calendar will be synced with your subscribed calendars.',
             'Choices are: %s.' % (', '.join(FREQUENCY_CHOICES))],
            'no_user:fail': 'No user was provided.'},
    'getinfo': {'no_user:fail': 'No user was provided.',
                'no_cal:fail': 'You have never used %s.' % APP_ID}}


class MessageException(Exception):
  """Base exception for holding a printable message."""
  message = None

  def __init__(self, message, *args, **kwargs):
    super(MessageException, self).__init__(*args, **kwargs)
    self.message = message


class AuthException(MessageException):
  """Thrown when an authentication error occurs."""


class APIUseException(MessageException):
  """Thrown when the API is used incorrectly or returns an error."""


class APIAuthManager(object):
  """Class for handling AppEngine application auth via Client Login."""

  client_auth = None
  application_auth = None

  def __init__(self, email, application_id=APP_ID):
    self.email = email
    self.application_id = application_id

  def __repr__(self):
    return 'APIAuthManager(%s, app=%s, state=%s)' % (self.email,
                                                     self.application_id,
                                                     self.status)

  @property
  def state(self):
    """State value using client auth as 1st binary bit and app auth as 2nd."""
    if self.client_auth is None:
      return 0 if self.application_auth is None else 1
    else:
      return 2 if self.application_auth is None else 3

  @property
  def status(self):
    """Verbose status message for each auth state."""
    state_map = {0: 'No Auth Completed',
                 1: 'Login Corrupted',
                 2: 'Client Login Completed',
                 3: 'Auth Complete'}
    return state_map[self.state]

  def _GetClientAuthResponse(self, password, client_login=CLIENT_LOGIN):
    """Submit client login request and return response body.

    Args:
      password: the password of the user
      client_login: the url used to make client login requests, defaults to the
          global value CLIENT_LOGIN

    Returns:
      auth_response: The body of the client login response if successful,
          else None

    Raises:
      AuthException: in the case that the auth_response is not set
    """
    params = urllib.urlencode(  # pylint:disable-msg=E0602
        {'accountType': 'GOOGLE',
         'service': 'ah',
         'source': self.application_id,
         'Email': self.email,
         'Passwd': password})

    auth_response = None
    try:
      auth_cnxn = urllib2.urlopen(  # pylint:disable-msg=E0602
          client_login, params)
      auth_response = auth_cnxn.read()
      auth_cnxn.close()
    except urllib2.HTTPError as exc:  # pylint:disable-msg=E0602
      if exc.code in (401, 403):
        auth_response = exc.read()

    if auth_response is None:
      raise AuthException('Could not connect to Google.')

    return auth_response

  def GetClientAuth(self, client_login=CLIENT_LOGIN):
    """Get Auth Token for user from client login.

    The body of the response is expected to be three lines, beginning
    with SID=, LSID= and Auth=, and in that order. If the authentication
    was not successful, we expect 'Error=BadAuthentication' to be in the
    response. If the failure was caused by a user having two factor
    authentication activated, we expect 'Info=InvalidSecondFactor' to
    be in the response as well

    In the case that the method is called after login has completed, we
    reset all auth values and rely on the method to reset the client auth.

    Args:
      client_login: the url used to make client login requests, defaults to the
          global value CLIENT_LOGIN

    Returns:
      self.client_auth: the final value of client auth. If by the end of the
          method, it has not been set, AuthException will be raised.

    Raises:
      AuthException: in the case that _GetClientAuthResponse returns None, the
          response contains BadAuthentication or is an unexpected format.
    """
    self.client_auth = None
    self.application_auth = None

    password = getpass.getpass('Password: ')  # pylint:disable-msg=E0602
    auth_response = self._GetClientAuthResponse(password, client_login)

    if 'Error=BadAuthentication' in auth_response:
      to_raise = ['Authentication failed.']
      if 'Info=InvalidSecondFactor' in auth_response:
        to_raise.extend(['',
                         'Two factor authorization is not supported.',
                         'Please use an application specific password.'])
      raise AuthException(to_raise)

    auth_rows = [row for row in auth_response.split('\n') if row]
    if len(auth_rows) == 3:
      sid_row, lsid_row, auth_row = auth_rows
      if (sid_row.startswith('SID=') and lsid_row.startswith('LSID=') and
          auth_row.startswith('Auth=')):
        self.client_auth = auth_row.lstrip('Auth=')

    if self.client_auth is None:
      raise AuthException('Client login failed.')

    return self.client_auth

  def GetApplicationAuth(self, request_url=None, client_login=CLIENT_LOGIN):
    """Obtain application specific cookie by using self.client_auth.

    In order to make API requests, we need to use the Google account cookie to
    authenticate with the application and then keep the application specific
    cookie for later use.

    In the case that the method is called after login has completed, we
    reset the application auth value and rely on the method to reset it.

    Args:
      request_url: application specific url to request a cookie given a
          client auth token has been obtained. In default case, is set to None,
          and the script will set it with the client auth token and a url
          template.
      client_login: the url used to make client login requests, defaults to the
          global value CLIENT_LOGIN

    Returns:
      self.application_auth: the final value of the application cookie. If by
          the end of the method, it has not been set, AuthException
          will be raised.

    Raises:
      AuthException: in the case that GetClientAuth raises it, the inital
          request fails, or no ACSID= cookie is returned
    """
    self.application_auth = None
    if self.state < 2:
      self.GetClientAuth(client_login)

    if request_url is None:
      request_url = APPLICATION_AUTH_URL_TEMPLATE % self.client_auth

    cookie_jar = cookielib.CookieJar()  # pylint:disable-msg=E0602
    opener = urllib2.build_opener(  # pylint:disable-msg=E0602
        urllib2.HTTPCookieProcessor(cookie_jar))  # pylint:disable-msg=E0602

    try:
      opener.open(request_url)
    except urllib2.HTTPError:  # pylint:disable-msg=E0602
      raise AuthException(
          ['Connection error.', '',
           'Could not reach %s to obtain a cookie.' % self.application_id])

    for cookie in cookie_jar:
      if cookie.name == 'ACSID':
        self.application_auth = cookie.value
        break

    if self.application_auth is None:
      raise AuthException(
          ['Authentication error.', '',
           'Could not retrieve cookie from %s.' % self.application_id])

    return self.application_auth


def PrintMessageList(msg_list):
  """Print a list with a nice box format.

  The input is surrounded by a box with | on edges, - across the top and
  + in each corner.

  Args:
    msg_list: A string or a list of strings.
  """
  if isinstance(msg_list, str) or isinstance(msg_list, unicode):
    msg_list = [msg_list]

  length = max(len(line) for line in msg_list)
  result = ['| %s |' % line.ljust(length) for line in msg_list]
  header = '+%s+' % ('-' * (length + 2))
  result = [header] + result + [header]

  print('\n'.join(result))


def AddSubscription(application_auth, payload, add_endpoint=ADD_ENDPOINT):
  """Attempts to add a calendar link for the authenticated user via the API.

  If the payload dictionary  does not contain the key 'calendar-link', we return
  an error message. If it does, the calendar link is sent to the API and either
  the new subscription list is returned by the API or an JSON error message
  is returned explaining why the link was rejected.

  Args:
    application_auth: the ACSID cookie specific to the application and the user
    payload: a dictionary corresponding to the necessary data to make an API
        request. For this function, we expect the key 'calendar-link' and the
        value we expect to be any string.
    add_endpoint: The API endpoint for making add requests. By default this is
        set to the global ADD_ENDPOINT.

  Returns:
    A list of lines or a string instance to be passed to PrintMessageList to
        alert the user of failure or success

  Raises:
    APIUseException: in the case that no link is in the http payload, the
        request times out, the API returns an error in ERROR_RESPONSES
        or the response is not a list of length 4 or less
  """
  calendar_link = payload.get('calendar-link', None)
  if calendar_link is None:
    raise APIUseException(['Unexpected behavior: library error.', '',
                           'No calendar link was specified in the payload.'])

  request = urllib2.Request(add_endpoint)  # pylint:disable-msg=E0602
  request.add_header('Cookie', 'ACSID=%s' % application_auth)
  params = urllib.urlencode(  # pylint:disable-msg=E0602
      {'calendar-link': calendar_link})

  try:
    add_subs_cnxn = urllib2.urlopen(request, params)  # pylint:disable-msg=E0602
    response_val = simplejson.loads(  # pylint:disable-msg=E0602
        add_subs_cnxn.read())
    add_subs_cnxn.close()
  except urllib2.HTTPError:  # pylint:disable-msg=E0602
    raise APIUseException([
        'Connection error.', '',
        'Could not reach %s to add %s.' % (APP_ID, calendar_link)])

  # Output may be a list, which is unhashable
  if response_val in ERROR_RESPONSES['add'].keys():
    raise APIUseException(ERROR_RESPONSES['add'][response_val])

  if type(response_val) != list or len(response_val) > 4:
    raise APIUseException('An unexpected error occurred.')

  return ['Success!', '', 'Your current subscriptions are:'] + response_val


def ChangeFrequency(application_auth, payload, freq_endpoint=FREQ_ENDPOINT):
  """Attempts to change the frequency for the authenticated user via the API.

  If the payload dictionary  does not contain the key 'frequency', we return an
  error message. If the frequency provided is contained in FREQUENCY_MAP, we
  transform the value and let the API determine if the transformed value is
  valid. If the cookie value is not valid or the server can't be reached, an
  error message is returned to be printed by the caller.

  In the case of success, the API returns a JSON tuple (verbose, short) where
  verbose if the human readable version of the frequency and short is the
  version used as a shorthand.

  Args:
    application_auth: the ACSID cookie specific to the application and the user
    payload: a dictionary corresponding to the necessary data to make an API
        request. For this function, we expect the key 'frequency' and the value
        we expect to be a key in the constant FREQUENCY_MAP.
    freq_endpoint: The API endpoint for making frequency change requests. By
        default this is set to the global FREQ_ENDPOINT.

  Returns:
    A list of lines or a string instance to be passed to PrintMessageList to
        alert the user of failure or success

  Raises:
    APIUseException: in the case that frequency is not in the http payload, the
        request times out, the API returns an error in ERROR_RESPONSES
        or the response is not a list of length 2
  """
  frequency = payload.get('frequency', None)
  if frequency is None:
    raise APIUseException(['Unexpected behavior: library error.', '',
                           'No frequency was specified in the HTTP payload.'])

  if frequency in FREQUENCY_MAP:
    frequency = FREQUENCY_MAP[frequency]

  request = urllib2.Request(freq_endpoint)  # pylint:disable-msg=E0602
  request.add_header('Cookie', 'ACSID=%s' % application_auth)
  request.get_method = lambda: 'PUT'
  params = urllib.urlencode(  # pylint:disable-msg=E0602
      {'frequency': frequency})

  try:
    add_subs_cnxn = urllib2.urlopen(request, params)  # pylint:disable-msg=E0602
    response_val = simplejson.loads(  # pylint:disable-msg=E0602
        add_subs_cnxn.read())
    add_subs_cnxn.close()
  except urllib2.HTTPError:  # pylint:disable-msg=E0602
    raise APIUseException(
        ['Connection error.', '',
         'Could not reach %s to change freq to %s.' % (APP_ID, frequency)])

  # Output may be a list, which is unhashable
  if response_val in ERROR_RESPONSES['chg'].keys():
    raise APIUseException(ERROR_RESPONSES['chg'][response_val])

  if (type(response_val) != list or len(response_val) != 2 or
      response_val[1] != frequency):
    raise APIUseException('An unexpected error occurred.')

  return ['Success!', '',
          'Your subscriptions will be updated %s.' % response_val[0]]


def GetInfo(application_auth, getinfo_endpoint=GETINFO_ENDPOINT):
  """Attempts to get subscription info for the authenticated user via the API.

  If the cookie value is not valid or the server can't be reached, an
  error message is returned to be printed by the caller.

  In the case of success, the API returns a JSON tuple (calendars, frequency)
  where calendars is a list of calendar subscriptions and frequency is the
  the human readable version of the frequency.

  Args:
    application_auth: the ACSID cookie specific to the application and the user
    getinfo_endpoint: The API endpoint for making information requests. By
        default this is set to the global FREQ_ENDPOINT.

  Returns:
    A list of lines or a string instance to be passed to PrintMessageList to
        alert the user of failure or success

  Raises:
    APIUseException: in the case that the request times out, the API returns an
        error in ERROR_RESPONSES or the response is not a list of length 2
        with first value a list as well
  """
  request = urllib2.Request(getinfo_endpoint)  # pylint:disable-msg=E0602
  request.add_header('Cookie', 'ACSID=%s' % application_auth)

  try:
    add_subs_cnxn = urllib2.urlopen(request)  # pylint:disable-msg=E0602
    response_val = simplejson.loads(  # pylint:disable-msg=E0602
        add_subs_cnxn.read())
    add_subs_cnxn.close()
  except urllib2.HTTPError:  # pylint:disable-msg=E0602
    raise APIUseException(['Connection error.', '',
                           'Could not reach %s to get info.' % APP_ID])

  # Output may be a list, which is unhashable
  if response_val in ERROR_RESPONSES['getinfo'].keys():
    raise APIUseException(ERROR_RESPONSES['getinfo'][response_val])

  if (type(response_val) != list or len(response_val) != 2 or
      type(response_val[0]) != list):
    raise APIUseException('An unexpected error occurred.')

  calendars, verbose_freq = response_val
  return ['Your subscriptions will be updated %s.' % verbose_freq,
          '', 'Your current subscriptions are:'] + calendars


def MakeRequest(parsed_args):
  """Attempts to perform a requested action via the API.

  This is intended to be used with the results of parsed arguments (via
  argparse). This will handle all authentication steps and will prompt
  the user for email and password. Only the actions 'add', 'frequency' and
  'getinfo' are accepted and mapped to the relevant subfunctions with the
  relevant authentication cookie and payload data. If the action succeeds, a
  response message from the relevant subfunction is returned.

  Args:
    parsed_args: an ArgumentParser object.

  Returns:
    A list of lines or a string instance to be passed to PrintMessageList to
        alert the user of success

  Raises:
    APIUseException: when none of the predefined API actions have been
        sent with the parsed args
  """
  auth_manager = APIAuthManager(raw_input('Email address: '))
  application_auth = auth_manager.GetApplicationAuth()

  api_actions = [('add', AddSubscription, 'calendar-link'),
                 ('chg', ChangeFrequency, 'frequency'),
                 ('getinfo', GetInfo, None)]

  for action, method, attr in api_actions:
    value = getattr(parsed_args, action, None)
    if value is None:
      continue

    method_args = (application_auth,)
    if attr is not None:
      method_args += ({attr: value},)

    return method(*method_args)

  raise APIUseException('Request attempted without valid arguments.')


def ImportOrFail(scope=locals()):
  """Attempts to import the needed Python packages or fail with message.

  Since a command line tool, this is included to give the users an informative
  message that will allow them to get their environment configured correctly.
  This will attempt to import each library in REQUIRED_LIBRARIES. If any fail,
  a message describing how to install is returned.

  Args:
    scope: A scope dictionary (intended to be locals()) to add the imports to

  Returns:
    A tuple (success, msg_list) where
      success: Boolean indicating whether all imports succeeded
      msg_list: a list of strings to be printed by PrintMessageList in the case
          of import failure
  """
  imports_needed = []
  for library in REQUIRED_LIBRARIES:
    try:
      scope[library] = __import__(library)
    except ImportError:
      imports_needed.append(library)

  if imports_needed:
    msg_list = ['Failed to import necessary libraries.', '',
                'To successfully use the %s command line tool,' % APP_ID,
                'consider installing the missing libraries via:']

    for library in imports_needed:
      msg_list.append('sudo pip install %s' % library)

    msg_list.extend(['', 'If you do not have pip installed, easy_install is a',
                     'worthy replacement, but you should get pip though.',
                     '', 'If you have neither, visit;',
                     'http://www.pip-installer.org/en/latest/installing.html'])
    return (False, msg_list)

  return (True, None)


def GetParser(app_id=APP_ID):
  """Create arg parser specific to the API to allow script to be used in CLI.

  Args:
    app_id: application ID, with default as to the global value

  Returns:
    An argparse.ArgumentParser object with mappings to the subfunctions relevant
        to the API as well as help text
  """
  parser = argparse.ArgumentParser(  # pylint:disable-msg=E0602
      prog=app_id, description='Command Line Tool for persistent-cal')
  subparsers = parser.add_subparsers(help='persistent-cal subcommands')

  parser_add = subparsers.add_parser('add', help='Add subscription to calendar')
  parser_add.add_argument(
      'add', metavar='link', type=unicode,
      help='external calendar link to add as a subscription')

  parser_chg = subparsers.add_parser(
      'chg', help='Change frequency of calendar updates')

  parser_chg.add_argument(
      'chg', metavar='freq', type=int,
      help=('number of times per week that your personal '
            'calendar will be synced with your subscribed calendars'))

  parser_getinfo = subparsers.add_parser(
      'getinfo', help='Get existing calendar info')
  parser_getinfo.add_argument('getinfo', action='store_true')

  return parser


def main():
  args = GetParser().parse_args()

  try:
    result = MakeRequest(args)
    PrintMessageList(result)
  except (AuthException, APIUseException) as exc:
    PrintMessageList(exc.message)
  except KeyboardInterrupt:
    print('\n')
    PrintMessageList(['Sorry I couldn\'t be more helpful.',
                      'That hurts when you cancel me!'])


parent_scope = locals()
success, msg_list = ImportOrFail(parent_scope)
if not success:
  PrintMessageList(msg_list)
  sys.exit(1)


if __name__ == '__main__':
  main()

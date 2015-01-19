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


"""Test persistent-cal CLI tool."""


__author__ = 'daniel.j.hermes@gmail.com (Dan Hermes)'


# General libraries
import argparse
import cookielib
import cStringIO
import getpass
import simplejson
import sys
import unittest
import urllib
import urllib2

# App specific libraries
import persistent_cal


ACSID_VAL = 'A'
ADD = '/add'
ADD_ERROR_MAP = {'contained': 'contained:fail',
                 'limit': 'limit:fail',
                 'user': 'no_user:fail',
                 'whitelist': 'whitelist:fail'}
ADD_UNEXPECTED_MAP = {'not_list': None,
                      'too_long_list': range(5)}
APPLICATION_AUTH_CORRECT_URL = 'application_auth'
APPLICATION_AUTH_NO_COOKIE_URL = 'not_application_auth'
AUTH_VAL = 'c'
CALENDAR_LINK_VALID = 'calendar_link_valid'
CLIENT_AUTH_BAD_CONTENT_URL = 'client_login_bad_content'
CLIENT_AUTH_BAD_ROWS_URL = 'client_login_bad_rows'
CLIENT_AUTH_CORRECT_URL = 'client_login'
CLIENT_LOGIN_BAD_AUTH = 'Error=BadAuthentication\n'
CLIENT_LOGIN_BAD_SECOND_FACTOR = 'Info=InvalidSecondFactor\n'
CLIENT_LOGIN_VALID_AUTH = {'valid': 'SID=a\nLSID=b\nAuth=%s\n' % AUTH_VAL,
                           'bad_rows': 'LSID=b\nAuth=%s\n' % AUTH_VAL,
                           'bad_content': 'row1\nrow2\nrow3\n'}
EMAIL = 'test@example.com'
EMAIL_ASP = 'specific'
EMAIL_NOT_VALID_PASSWORD = 'not_valid'
EMAIL_PASSWORD = 'password'
FREQUENCY = '/freq'
FREQUENCY_ERROR_MAP = {'none': 'no_cal:fail',
                       'user': 'no_user:fail',
                       'wrong': 'wrong_freq:fail'}
FREQUENCY_RESPONSES = {'week': 'once a week',
                       'two-day': 'every two days',
                       'day': 'once a day',
                       'half-day': 'twice a day',
                       'six-hrs': 'every six hours',
                       'three-hrs': 'every three hours'}
FREQUENCY_UNEXPECTED_MAP = {'not_list': None,
                            'too_long_list': range(3),
                            'incongruous_list': ['a', 'b']}
GETINFO = '/getinfo'
GETINFO_ERROR_MAP = {'cal': 'no_cal:fail',
                     'user': 'no_user:fail'}
GETINFO_SUCCESS = [[CALENDAR_LINK_VALID], 'once a week']
GETINFO_UNEXPECTED_MAP = {'not_list': None,
                          'too_long_list': range(3),
                          'first_arg_not_list': ['', '']}


def RaiseHTTPError(url='', code=200, msg='', response_data=''):
  """Raises a mock HTTPError with crucial named arguments.

  This error will be a minimal mock, with headers set to None and
  a cStringIO object used as the body (fp).

  Args:
    url: A url to cite in HTTP error
    code: HTTP response code
    msg: exception message passed to urllib2.HTTPError
    response_data: data to be placed in cStringIO object for body

  Raises:
    urllib2.HTTPError: uses args (or defaults values) to raise error
  """
  hdrs = None
  fp = cStringIO.StringIO(response_data)
  raise urllib2.HTTPError(url, code, msg, hdrs, fp)


def CookieBuilder(name='ACSID', value=ACSID_VAL):
  """Mock cookie builder.

  For the purposes of the library we are testing, only the
  name and value attributes are used from the cookie, so
  we only require them and provide False-y values for all the
  remaining 15 required attributes.

  Args:
    name: cookie name
    value: cookie value

  Returns:
    cookielib.Cookie object with mostly False-y attributes, name
        and value set
  """
  return cookielib.Cookie(
      version=None, name=name, value=value,
      port=None, port_specified=False,
      domain='', domain_specified=False, domain_initial_dot=False,
      path=None, path_specified=False, secure=False, expires=None,
      discard=False, comment=None, comment_url=None, rest={})


def MockCookieProcessor(cookie_jar):
  """Mock cookie processor to be used with MockBuildOpener.

  Uses external scope to add cookies to the cookie_jar in the processor.
  The mock CookieBuilder function is used to set only name and value in the
  cookie(s) added.

  Args:
    cookie_jar: a cookielib.CookieJar object

  Returns:
    function which uses external scope to set a cookie
  """

  def Update(name, value):
    """Function to be returned, changes cookie_jar from external scope."""
    cookie = CookieBuilder(name=name, value=value)
    cookie_jar.set_cookie(cookie)

  return Update


def ClientLoginOpener(pw_dict, url, data, response_key='valid'):
  """Mock urlopen to be used to test Client Login functions.

  Args:
    pw_dict: A dictionary of password data, with usernames as keys
        and values equal to passwords or (ASP, password) pairs
    url: string value of requested url
    data: POST data sent with urlopen
    response_key: a key used with the global CLIENT_LOGIN_VALID_AUTH
        to determine what the response body will be in the case of
        a successful request

  Returns:
    cStringIO object containing either a BadAuthentication message, one
        or the valid responses in CLIENT_LOGIN_VALID_AUTH

  Raises:
    urllib2.HTTPError: in the case that an unexpected error causes a response
        not to be set or a request is sent without a matching email/password
        combination.
  """
  for email, password in pw_dict.items():
    email_enc = urllib.urlencode({'Email': email})
    asp_enc = None
    if isinstance(password, tuple):
      app_specific_pass, password = password
      asp_enc = urllib.urlencode({'Passwd': app_specific_pass})
    pw_enc = urllib.urlencode({'Passwd': password})

    if data is not None and email_enc in data:
      response = None
      if asp_enc is not None:
        if asp_enc in data:
          return cStringIO.StringIO(CLIENT_LOGIN_VALID_AUTH[response_key])
        else:
          response = CLIENT_LOGIN_BAD_AUTH
          if pw_enc in data:
            response += CLIENT_LOGIN_BAD_SECOND_FACTOR
      elif pw_enc in data:
        return cStringIO.StringIO(CLIENT_LOGIN_VALID_AUTH[response_key])
      else:
        response = CLIENT_LOGIN_BAD_AUTH

      if response is not None:
        RaiseHTTPError(url=url, code=403,
                       msg='Forbidden', response_data=response)

  RaiseHTTPError(url=url, code=403,
                 msg='Forbidden', response_data=CLIENT_LOGIN_BAD_AUTH)


def AddSubscriptionOpener(request, data):
  """Mock urlopen to be used to test with AddSubscription endpoint.

  Args:
    request: a urllib2.Request object with header and url data
    data: post data sent with request

  Returns:
    cStringIO object containing either an API error message from the globals
        ADD_ERROR_MAP or ADD_UNEXPECTED_MAP or a valid response.

  Raises:
    urllib2.HTTPError: in the case that the correct cookie is not set or the
        necessary data is not sent to trigger a 200 response
  """
  correct_cookie = 'ACSID=%s' % AUTH_VAL
  calendar_link_enc = urllib.urlencode({'calendar-link': CALENDAR_LINK_VALID})

  if request.get_header('Cookie', '') == correct_cookie:
    if calendar_link_enc in data:
      response = simplejson.dumps([CALENDAR_LINK_VALID])
      return cStringIO.StringIO(response)
    else:
      for add_error in ADD_ERROR_MAP:
        add_error_enc = urllib.urlencode({'calendar-link': add_error})
        if add_error_enc in data:
          response = simplejson.dumps(ADD_ERROR_MAP[add_error])
          return cStringIO.StringIO(response)

      for add_unexpected in ADD_UNEXPECTED_MAP:
        add_unexpected_enc = urllib.urlencode({'calendar-link': add_unexpected})
        if add_unexpected_enc in data:
          response = simplejson.dumps(ADD_UNEXPECTED_MAP[add_unexpected])
          return cStringIO.StringIO(response)

  RaiseHTTPError(url=request, code=404)


def ChangeFrequencyOpener(request, data):
  """Mock urlopen to be used to test with ChangeFrequency endpoint.

  Args:
    request: a urllib2.Request object with header and url data
    data: post data sent with request

  Returns:
    cStringIO object containing either an API error message from the globals
        FREQUENCY_ERROR_MAP or FREQUENCY_UNEXPECTED_MAP or a valid response.

  Raises:
    urllib2.HTTPError: in the case that the correct cookie is not set, the
        necessary data is not sent to trigger a 200 response or the method
        of the request is not PUT.
  """
  correct_cookie = 'ACSID=%s' % AUTH_VAL

  if (request.get_header('Cookie', '') == correct_cookie and
      request.get_method() == 'PUT'):
    for value in FREQUENCY_RESPONSES:
      value_enc = urllib.urlencode({'frequency': value})
      if value_enc in data:
        response = simplejson.dumps([FREQUENCY_RESPONSES[value], value])
        return cStringIO.StringIO(response)

    for freq_error in FREQUENCY_ERROR_MAP:
      freq_error_enc = urllib.urlencode({'frequency': freq_error})
      if freq_error_enc in data:
        response = simplejson.dumps(FREQUENCY_ERROR_MAP[freq_error])
        return cStringIO.StringIO(response)

    for freq_unexpected in FREQUENCY_UNEXPECTED_MAP:
      freq_unexpected_enc = urllib.urlencode({'frequency': freq_unexpected})
      if freq_unexpected_enc in data:
        response = simplejson.dumps(FREQUENCY_UNEXPECTED_MAP[freq_unexpected])
        return cStringIO.StringIO(response)

  RaiseHTTPError(url=request, code=404)


def GetInfoOpener(request, error=None):
  """Mock urlopen to be used to test with GetInfo endpoint.

  Args:
    request: a urllib2.Request object with header and url data
    error: An error to trigger a mock API error response

  Returns:
    cStringIO object containing either an API error message from the globals
        GETINFO_ERROR_MAP or GETINFO_UNEXPECTED_MAP or a valid response.

  Raises:
    urllib2.HTTPError: in the case that the correct cookie is not set or
        error is set to an unexpected value
  """
  correct_cookie = 'ACSID=%s' % AUTH_VAL

  if request.get_header('Cookie', '') == correct_cookie:
    if error is None:
      response = simplejson.dumps(GETINFO_SUCCESS)
      return cStringIO.StringIO(response)
    elif error in GETINFO_ERROR_MAP or error in GETINFO_UNEXPECTED_MAP:
      if error in GETINFO_ERROR_MAP:
        response = simplejson.dumps(GETINFO_ERROR_MAP[error])
      else:
        response = simplejson.dumps(GETINFO_UNEXPECTED_MAP[error])
      return cStringIO.StringIO(response)

  RaiseHTTPError(url=request, code=404)


def MockOpener(pw_dict):
  """Returns mock urlopen function which accounts for user credentials."""

  def URLOpen(url, data=None):
    """Mock urlopen function to be returned."""
    if url == CLIENT_AUTH_CORRECT_URL:
      return ClientLoginOpener(pw_dict, url, data)
    elif url == CLIENT_AUTH_BAD_ROWS_URL:
      return ClientLoginOpener(pw_dict, url, data, response_key='bad_rows')
    elif url == CLIENT_AUTH_BAD_CONTENT_URL:
      return ClientLoginOpener(pw_dict, url, data, response_key='bad_content')
    elif isinstance(url, urllib2.Request):
      full_url = url.get_full_url()
      if full_url == ADD:
        return AddSubscriptionOpener(url, data)
      elif full_url == FREQUENCY:
        return ChangeFrequencyOpener(url, data)
      elif full_url == GETINFO:
        return GetInfoOpener(url)
      elif full_url in GETINFO_ERROR_MAP or full_url in GETINFO_UNEXPECTED_MAP:
        return GetInfoOpener(url, error=full_url)

    RaiseHTTPError(url=url, code=404,
                   msg='Resource not found.', response_data='')

  return URLOpen


class MockBuildOpener(object):
  """Mock urllib2.build_opener class, interacts with MockCookieProcessor."""

  def __init__(self, cookie_processor):
    self.cookie_processor = cookie_processor

  def open(self, request_url):  # pylint: disable-msg=C6409
    if request_url == APPLICATION_AUTH_CORRECT_URL:
      self.cookie_processor(name='ACSID', value=ACSID_VAL)
    elif request_url == APPLICATION_AUTH_NO_COOKIE_URL:
      pass
    else:
      RaiseHTTPError(url=request_url, code=404)


class MockAPIAuthManager(object):
  """Mock APIAuthManager class for testing MakeRequest."""

  def __init__(self, value):
    self.value = value

  def GetApplicationAuth(self):
    return self.value


class TestPrintMessageList(unittest.TestCase):
  """Test PrintMessageList helper function."""

  sys_out = None

  def setUp(self):  # pylint: disable-msg=C6409
    """Configure the test case so stdout can be read."""
    self.sys_out = sys.stdout
    sys.stdout = cStringIO.StringIO()

  def testList(self):  # pylint: disable-msg=C6409
    """Tests list input."""
    msg_list = ['line1', 'line2 extra length']
    actual_value = ('+--------------------+\n'
                    '| line1              |\n'
                    '| line2 extra length |\n'
                    '+--------------------+\n')
    persistent_cal.PrintMessageList(msg_list)
    self.assertEqual(sys.stdout.getvalue(),  # pylint: disable-msg=E1103
                     actual_value)

  def testString(self):
    """Tests string input."""
    msg = 'txt'
    actual_value = ('+-----+\n'
                    '| txt |\n'
                    '+-----+\n')
    persistent_cal.PrintMessageList(msg)
    self.assertEqual(sys.stdout.getvalue(),  # pylint: disable-msg=E1103
                     actual_value)

  def tearDown(self):  # pylint: disable-msg=C6409
    sys.stdout = self.sys_out


class TestGetParser(unittest.TestCase):
  """Test GetParser helper function."""

  def setUp(self):  # pylint: disable-msg=C6409
    self.parser = persistent_cal.GetParser('test')

  def assertAttrsNotSet(self, obj, attrs):
    """Helper method to make sure each attr in attrs is not set on obj."""
    for attr in attrs:
      self.assertFalse(hasattr(obj, attr))

  def testInvalidArgs(self):  # pylint: disable-msg=C6409
    """Tests invalid arguments passed to GetParser."""
    self.assertRaises(SystemExit, self.parser.parse_args, [])
    self.assertRaises(SystemExit, self.parser.parse_args, ['a'])

    self.assertRaises(SystemExit, self.parser.parse_args, ['add'])
    self.assertRaises(SystemExit, self.parser.parse_args, ['add',
                                                           'link',
                                                           'extra'])

    self.assertRaises(SystemExit, self.parser.parse_args, ['chg'])
    self.assertRaises(SystemExit, self.parser.parse_args, ['chg', 'a'])

    self.assertRaises(SystemExit, self.parser.parse_args, ['getinfo', 'a'])

    # Only one subcommand should work at once
    self.assertRaises(SystemExit, self.parser.parse_args, ['add',
                                                           'link',
                                                           'chg',
                                                           '1'])
    self.assertRaises(SystemExit, self.parser.parse_args, ['getinfo',
                                                           'add',
                                                           'link'])

  def testValidArgs(self):  # pylint: disable-msg=C6409
    """Tests valid arguments passed to GetParser."""
    parsed = self.parser.parse_args(['add', 'link'])
    self.assertTrue(isinstance(parsed, argparse.Namespace))
    self.assertAttrsNotSet(parsed, ['chg', 'getinfo'])
    self.assertEqual(parsed.add, 'link')

    parsed = self.parser.parse_args(['chg', '1'])
    self.assertTrue(isinstance(parsed, argparse.Namespace))
    self.assertAttrsNotSet(parsed, ['add', 'getinfo'])
    self.assertEqual(parsed.chg, 1)

    parsed = self.parser.parse_args(['getinfo'])
    self.assertTrue(isinstance(parsed, argparse.Namespace))
    self.assertAttrsNotSet(parsed, ['add', 'chg'])
    self.assertEqual(parsed.getinfo, True)


class TestAPIAuthManagerBasic(unittest.TestCase):
  """Test APIAuthManager instance init and state functions."""

  def setUp(self):  # pylint: disable-msg=C6409
    self.auth_manager = persistent_cal.APIAuthManager(EMAIL,
                                                      application_id='test')

  def testInit(self):  # pylint: disable-msg=C6409
    """Tests init for APIAuthManager."""
    self.assertEqual(self.auth_manager.state, 0)
    self.assertEqual(self.auth_manager.client_auth, None)
    self.assertEqual(self.auth_manager.application_auth, None)
    self.assertEqual(self.auth_manager.email, EMAIL)
    self.assertEqual(self.auth_manager.application_id, 'test')

  def testState(self):  # pylint: disable-msg=C6409
    """Tests derived property state."""
    self.assertEqual(self.auth_manager.state, 0)

    self.auth_manager.client_auth = 'mock'
    self.assertEqual(self.auth_manager.state, 2)

    self.auth_manager.application_auth = 'mock'
    self.assertEqual(self.auth_manager.state, 3)

    self.auth_manager.client_auth = None
    self.assertEqual(self.auth_manager.state, 1)


class TestAPIAuthManagerClientAuthHelper(unittest.TestCase):
  """Test APIAuthManager instance Client Auth Helper function."""

  urlopen = None

  def setUp(self):  # pylint: disable-msg=C6409
    """Configure the test case.

    We replace urlopen with a MockOpener that authenticates with the global
    constant EMAIL and has an ASP and regular password to simulate the possible
    auth errors that can occur.
    """
    self.urlopen = urllib2.urlopen
    urllib2.urlopen = MockOpener({EMAIL: (EMAIL_ASP, EMAIL_PASSWORD)})

    self.auth_manager = persistent_cal.APIAuthManager(EMAIL,
                                                      application_id='test')

  def testGetClientAuthResponseValid(self):  # pylint: disable-msg=C6409
    """Test valid request to _GetClientAuthResponse."""
    auth_response = self.auth_manager._GetClientAuthResponse(
        EMAIL_ASP, client_login=CLIENT_AUTH_CORRECT_URL)
    self.assertEqual(CLIENT_LOGIN_VALID_AUTH['valid'], auth_response)

  def testGetClientAuthResponseASPNeeded(self):  # pylint: disable-msg=C6409
    """Test request with password when ASP is needed."""
    auth_response = self.auth_manager._GetClientAuthResponse(
        EMAIL_PASSWORD, client_login=CLIENT_AUTH_CORRECT_URL)
    self.assertEqual(CLIENT_LOGIN_BAD_AUTH + CLIENT_LOGIN_BAD_SECOND_FACTOR,
                     auth_response)

  def testGetClientAuthResponseWrongPassword(self):  # pylint: disable-msg=C6409
    """Test request with wrong password sent."""
    auth_response = self.auth_manager._GetClientAuthResponse(
        EMAIL_NOT_VALID_PASSWORD, client_login=CLIENT_AUTH_CORRECT_URL)
    self.assertEqual(CLIENT_LOGIN_BAD_AUTH, auth_response)

  def testGetClientAuthResponseNoCnxn(self):  # pylint: disable-msg=C6409
    """Test request when no connection can be made."""
    self.assertRaises(persistent_cal.AuthException,
                      self.auth_manager._GetClientAuthResponse,
                      EMAIL_ASP, client_login=None)
    try:
      self.auth_manager._GetClientAuthResponse(EMAIL_ASP, client_login=None)
    except persistent_cal.AuthException as exc:
      self.assertEqual(exc.message, 'Could not connect to Google.')

  def tearDown(self):  # pylint: disable-msg=C6409
    urllib2.urlopen = self.urlopen


class TestAPIAuthManagerClientAuth(unittest.TestCase):
  """Test APIAuthManager instance Client Auth function."""

  urlopen = None
  getpass_fn = None

  def setUp(self):  # pylint: disable-msg=C6409
    self.urlopen = urllib2.urlopen
    urllib2.urlopen = MockOpener({EMAIL: (EMAIL_ASP, EMAIL_PASSWORD)})

    self.getpass_fn = getpass.getpass
    getpass.getpass = lambda prompt: EMAIL_PASSWORD

    self.auth_manager = persistent_cal.APIAuthManager(EMAIL,
                                                      application_id='test')

  def testGetClientAuthValid(self):  # pylint: disable-msg=C6409
    """Test valid request to GetClientAuth."""
    getpass.getpass = lambda prompt: EMAIL_ASP  # correct password from setUp

    client_auth = self.auth_manager.GetClientAuth(
        client_login=CLIENT_AUTH_CORRECT_URL)
    self.assertEqual(AUTH_VAL, client_auth)
    self.assertEqual(self.auth_manager.client_auth, client_auth)

  def testGetClientAuthASPNeeded(self):  # pylint: disable-msg=C6409
    """Request made to correct URL with password when ASP is needed.

    Since the actual password is given and an ASP is needed, the error
    message is longer and more descriptive.
    """
    getpass.getpass = lambda prompt: EMAIL_PASSWORD

    self.assertRaises(persistent_cal.AuthException,
                      self.auth_manager.GetClientAuth,
                      client_login=CLIENT_AUTH_CORRECT_URL)
    try:
      self.auth_manager.GetClientAuth(client_login=CLIENT_AUTH_CORRECT_URL)
    except persistent_cal.AuthException as exc:
      self.assertEqual(len(exc.message), 4)
      self.assertEqual(exc.message[:2], ['Authentication failed.', ''])

    self.assertEqual(self.auth_manager.client_auth, None)

  def testGetClientAuthWrongPassword(self):  # pylint: disable-msg=C6409
    """Request made to correct URL with invalid password."""
    getpass.getpass = lambda prompt: EMAIL_NOT_VALID_PASSWORD

    self.assertRaises(persistent_cal.AuthException,
                      self.auth_manager.GetClientAuth,
                      client_login=CLIENT_AUTH_CORRECT_URL)
    try:
      self.auth_manager.GetClientAuth(client_login=CLIENT_AUTH_CORRECT_URL)
    except persistent_cal.AuthException as exc:
      self.assertEqual(exc.message, ['Authentication failed.'])

    self.assertEqual(self.auth_manager.client_auth, None)

  def testGetClientAuthInvalidContent(self):  # pylint: disable-msg=C6409
    """Request with correct password, bad content returned.

    In the MockOpener, we set up two URLs that will execute the same
    authentication steps, but will return content that will not
    be successfully parsed. The first will be a response with the
    correct value Auth= contained, but which does not have 3 rows;
    this will be at CLIENT_AUTH_BAD_ROWS_URL. The second will be a response
    with 3 rows, but no correct {val}= at the beginning of each row; this
    will be at CLIENT_AUTH_BAD_CONTENT_URL.
    """
    getpass.getpass = lambda prompt: EMAIL_ASP

    self.assertRaises(persistent_cal.AuthException,
                      self.auth_manager.GetClientAuth,
                      client_login=CLIENT_AUTH_BAD_ROWS_URL)
    try:
      self.auth_manager.GetClientAuth(client_login=CLIENT_AUTH_BAD_ROWS_URL)
    except persistent_cal.AuthException as exc:
      self.assertEqual(exc.message, 'Client login failed.')

    self.assertEqual(self.auth_manager.client_auth, None)

    self.assertRaises(persistent_cal.AuthException,
                      self.auth_manager.GetClientAuth,
                      client_login=CLIENT_AUTH_BAD_CONTENT_URL)
    try:
      self.auth_manager.GetClientAuth(client_login=CLIENT_AUTH_BAD_CONTENT_URL)
    except persistent_cal.AuthException as exc:
      self.assertEqual(exc.message, 'Client login failed.')

    self.assertEqual(self.auth_manager.client_auth, None)

  def tearDown(self):  # pylint: disable-msg=C6409
    urllib2.urlopen = self.urlopen
    getpass.getpass = self.getpass_fn


class TestAPIAuthManagerApplicationAuth(unittest.TestCase):
  """Test APIAuthManager instance Application Auth functions."""

  urlopen = None
  getpass_fn = None
  build_opener = None
  cookie_processor = None

  def setUp(self):  # pylint: disable-msg=C6409
    self.auth_manager = persistent_cal.APIAuthManager(EMAIL,
                                                      application_id='test')

    self.urlopen = urllib2.urlopen
    urllib2.urlopen = MockOpener({EMAIL: EMAIL_PASSWORD})

    self.getpass_fn = getpass.getpass
    getpass.getpass = lambda prompt: EMAIL_PASSWORD  # Will be valid throughout

    self.build_opener = urllib2.build_opener
    urllib2.build_opener = MockBuildOpener
    self.cookie_processor = urllib2.HTTPCookieProcessor
    urllib2.HTTPCookieProcessor = MockCookieProcessor

  def testGetApplicationAuthValid(self):  # pylint: disable-msg=C6409
    """Test request to valid request url."""
    request_url = APPLICATION_AUTH_CORRECT_URL
    application_auth = self.auth_manager.GetApplicationAuth(
        request_url=request_url, client_login=CLIENT_AUTH_CORRECT_URL)
    self.assertEqual(ACSID_VAL, application_auth)
    self.assertEqual(self.auth_manager.application_auth, application_auth)

  def testGetApplicationAuthNoCookie(self):  # pylint: disable-msg=C6409
    """Test request to valid request url that doesn't set cookie."""
    request_url = APPLICATION_AUTH_NO_COOKIE_URL
    self.assertRaises(persistent_cal.AuthException,
                      self.auth_manager.GetApplicationAuth,
                      request_url=request_url,
                      client_login=CLIENT_AUTH_CORRECT_URL)
    try:
      self.auth_manager.GetApplicationAuth(
          request_url=request_url, client_login=CLIENT_AUTH_CORRECT_URL)
    except persistent_cal.AuthException as exc:
      self.assertEqual(len(exc.message), 3)
      self.assertEqual(exc.message[:2], ['Authentication error.', ''])

  def testGetApplicationAuthInvalid(self):  # pylint: disable-msg=C6409
    """Test request to invalid request url with valid credentials."""
    request_url = ''
    self.assertRaises(persistent_cal.AuthException,
                      self.auth_manager.GetApplicationAuth,
                      request_url=request_url,
                      client_login=CLIENT_AUTH_CORRECT_URL)
    try:
      self.auth_manager.GetApplicationAuth(
          request_url=request_url, client_login=CLIENT_AUTH_CORRECT_URL)
    except persistent_cal.AuthException as exc:
      self.assertEqual(len(exc.message), 3)
      self.assertEqual(exc.message[:2], ['Connection error.', ''])

  def tearDown(self):  # pylint: disable-msg=C6409
    urllib2.urlopen = self.urlopen
    getpass.getpass = self.getpass_fn

    urllib2.build_opener = self.build_opener
    urllib2.HTTPCookieProcessor = self.cookie_processor


class TestAddSubscription(unittest.TestCase):
  """Test AddSubscription function for authenticated API calls."""

  urlopen = None

  def setUp(self):  # pylint: disable-msg=C6409
    self.application_auth = AUTH_VAL

    self.urlopen = urllib2.urlopen
    urllib2.urlopen = MockOpener({EMAIL: EMAIL_PASSWORD})

  def testIncorrectPayload(self):  # pylint: disable-msg=C6409
    """Test correct add endpoint with bad payload data."""
    payload = {}

    self.assertRaises(persistent_cal.APIUseException,
                      persistent_cal.AddSubscription,
                      self.application_auth, payload, add_endpoint=ADD)

    try:
      persistent_cal.AddSubscription(self.application_auth,
                                     payload, add_endpoint=ADD)
    except persistent_cal.APIUseException as exc:
      self.assertEqual(exc.message,
                       ['Unexpected behavior: library error.', '',
                        'No calendar link was specified in the payload.'])

  def testValidRequest(self):  # pylint: disable-msg=C6409
    """Valid request sent to valid URL.

    By default, the mock opener will only accept add requests at the global ADD
    and will behave correctly given the calendar-link value CALENDAR_LINK_VALID.
    """
    payload = {'calendar-link': CALENDAR_LINK_VALID}

    api_response = persistent_cal.AddSubscription(self.application_auth,
                                                  payload,
                                                  add_endpoint=ADD)
    self.assertEqual(api_response, ['Success!', '',
                                    'Your current subscriptions are:',
                                    CALENDAR_LINK_VALID])

  def testBadRequest(self):  # pylint: disable-msg=C6409
    """Valid request sent to invalid URL.

    We send two requests: one to the URL '' which is Invalid and another with
    the cookie value set to ''.
    """
    bad_add_endpoint = ''
    payload = {'calendar-link': CALENDAR_LINK_VALID}

    self.assertRaises(persistent_cal.APIUseException,
                      persistent_cal.AddSubscription,
                      self.application_auth, payload,
                      add_endpoint=bad_add_endpoint)

    try:
      persistent_cal.AddSubscription(self.application_auth,
                                     payload, add_endpoint=bad_add_endpoint)
    except persistent_cal.APIUseException as exc:
      self.assertEqual(len(exc.message), 3)
      self.assertEqual(exc.message[:2], ['Connection error.', ''])

    bad_application_auth = ''
    self.assertRaises(persistent_cal.APIUseException,
                      persistent_cal.AddSubscription,
                      bad_application_auth, payload,
                      add_endpoint=ADD)

    try:
      persistent_cal.AddSubscription(bad_application_auth,
                                     payload, add_endpoint=ADD)
    except persistent_cal.APIUseException as exc:
      self.assertEqual(len(exc.message), 3)
      self.assertEqual(exc.message[:2], ['Connection error.', ''])

  def testBadAPIResponses(self):  # pylint: disable-msg=C6409
    """Valid API request sent with data that the API rejects.

    The AddSubscriptionOpener has predefined values that it will explicitly
    reject, defined in ADD_ERROR_MAP. By sending a valid request with the keys
    for ADD_ERROR_MAP in the payload, we can stub out the validation
    done server side by the API.
    """
    actual_error_response_map = persistent_cal.ERROR_RESPONSES['add']

    for add_error in ADD_ERROR_MAP:
      payload = {'calendar-link': add_error}
      self.assertRaises(persistent_cal.APIUseException,
                        persistent_cal.AddSubscription,
                        self.application_auth, payload,
                        add_endpoint=ADD)

      try:
        persistent_cal.AddSubscription(self.application_auth,
                                       payload, add_endpoint=ADD)
      except persistent_cal.APIUseException as exc:
        api_add_error = ADD_ERROR_MAP[add_error]
        self.assertEqual(exc.message, actual_error_response_map[api_add_error])

  def testUnexpectedAPIResponses(self):  # pylint: disable-msg=C6409
    """Valid API request with unexpected response.

    We use the AddSubscriptionOpener to return JSON objects which are not
    expected as responses by the API. Explicitly, objects which are either
    not a list or are a list of length greater than 4. The object and keys
    are in the global ADD_UNEXPECTED_MAP.
    """
    for add_unexpected in ADD_UNEXPECTED_MAP:
      payload = {'calendar-link': add_unexpected}
      self.assertRaises(persistent_cal.APIUseException,
                        persistent_cal.AddSubscription,
                        self.application_auth, payload,
                        add_endpoint=ADD)

      try:
        persistent_cal.AddSubscription(self.application_auth,
                                       payload, add_endpoint=ADD)
      except persistent_cal.APIUseException as exc:
        self.assertEqual(exc.message, 'An unexpected error occurred.')

  def tearDown(self):  # pylint: disable-msg=C6409
    urllib2.urlopen = self.urlopen


class TestChangeFrequency(unittest.TestCase):
  """Test ChangeFrequency function for authenticated API calls."""

  urlopen = None

  def setUp(self):  # pylint: disable-msg=C6409
    self.application_auth = AUTH_VAL

    self.urlopen = urllib2.urlopen
    urllib2.urlopen = MockOpener({EMAIL: EMAIL_PASSWORD})

  def testIncorrectPayload(self):  # pylint: disable-msg=C6409
    """Test correct frequency endpoint with bad payload data."""
    payload = {}

    self.assertRaises(persistent_cal.APIUseException,
                      persistent_cal.ChangeFrequency,
                      self.application_auth, payload, freq_endpoint=FREQUENCY)

    try:
      persistent_cal.ChangeFrequency(self.application_auth,
                                     payload, freq_endpoint=FREQUENCY)
    except persistent_cal.APIUseException as exc:
      self.assertEqual(exc.message,
                       ['Unexpected behavior: library error.', '',
                        'No frequency was specified in the HTTP payload.'])

  def testValidRequest(self):  # pylint: disable-msg=C6409
    """Valid request sent to valid URL.

    By default, the mock opener will only accept add requests at the global
    FREQUENCY.
    """
    for frequency, desc in persistent_cal.FREQUENCY_MAP.items():
      update_line = ('Your subscriptions will be updated %s.' %
                     FREQUENCY_RESPONSES[desc])

      payload = {'frequency': frequency}
      api_response = persistent_cal.ChangeFrequency(self.application_auth,
                                                    payload,
                                                    freq_endpoint=FREQUENCY)
      self.assertEqual(api_response, ['Success!', '', update_line])

      payload = {'frequency': desc}
      api_response = persistent_cal.ChangeFrequency(self.application_auth,
                                                    payload,
                                                    freq_endpoint=FREQUENCY)
      self.assertEqual(api_response, ['Success!', '', update_line])

  def testBadRequest(self):  # pylint: disable-msg=C6409
    """Valid request sent to invalid URL or with wrong method.

    We send two requests: one to the URL '' which is Invalid and another
    with the cookie value set to ''.
    """
    payload = {'frequency': 1}

    bad_freq_endpoint = ''
    self.assertRaises(persistent_cal.APIUseException,
                      persistent_cal.ChangeFrequency,
                      self.application_auth, payload,
                      freq_endpoint=bad_freq_endpoint)

    try:
      persistent_cal.ChangeFrequency(self.application_auth,
                                     payload, freq_endpoint=bad_freq_endpoint)
    except persistent_cal.APIUseException as exc:
      self.assertEqual(len(exc.message), 3)
      self.assertEqual(exc.message[:2], ['Connection error.', ''])

    bad_application_auth = ''
    self.assertRaises(persistent_cal.APIUseException,
                      persistent_cal.ChangeFrequency,
                      bad_application_auth, payload,
                      freq_endpoint=FREQUENCY)

    try:
      persistent_cal.ChangeFrequency(bad_application_auth,
                                     payload, freq_endpoint=FREQUENCY)
    except persistent_cal.APIUseException as exc:
      self.assertEqual(len(exc.message), 3)
      self.assertEqual(exc.message[:2], ['Connection error.', ''])

  def testBadAPIResponses(self):  # pylint: disable-msg=C6409
    """Valid API request sent with data that the API rejects.

    The ChangeFrequencyOpener has predefined values that it will explicitly
    reject, defined in FREQUENCY_ERROR_MAP. By sending a valid request with the
    keys for FREQUENCY_ERROR_MAP in the payload, we can stub out the validation
    done server side by the API.
    """
    actual_error_response_map = persistent_cal.ERROR_RESPONSES['chg']

    for freq_error in FREQUENCY_ERROR_MAP:
      payload = {'frequency': freq_error}
      self.assertRaises(persistent_cal.APIUseException,
                        persistent_cal.ChangeFrequency,
                        self.application_auth, payload,
                        freq_endpoint=FREQUENCY)

      try:
        persistent_cal.ChangeFrequency(self.application_auth,
                                       payload, freq_endpoint=FREQUENCY)
      except persistent_cal.APIUseException as exc:
        api_freq_error = FREQUENCY_ERROR_MAP[freq_error]
        self.assertEqual(exc.message, actual_error_response_map[api_freq_error])

  def testUnexpectedAPIResponses(self):  # pylint: disable-msg=C6409
    """Valid API request with unexpected response.

    We use the ChangeFrequencyOpener to return JSON objects which are not
    expected as responses by the API. Explicitly, objects which are either
    not a list, are a list of length not equal to 2 or a list of length 2
    with second element not equal to the frequency. The object and keys
    are in the global FREQUENCY_UNEXPECTED_MAP.
    """
    for freq_unexpected in FREQUENCY_UNEXPECTED_MAP:
      payload = {'frequency': freq_unexpected}
      self.assertRaises(persistent_cal.APIUseException,
                        persistent_cal.ChangeFrequency,
                        self.application_auth, payload,
                        freq_endpoint=FREQUENCY)

      try:
        persistent_cal.ChangeFrequency(self.application_auth,
                                       payload, freq_endpoint=FREQUENCY)
      except persistent_cal.APIUseException as exc:
        self.assertEqual(exc.message, 'An unexpected error occurred.')

  def tearDown(self):  # pylint: disable-msg=C6409
    urllib2.urlopen = self.urlopen


class TestGetInfo(unittest.TestCase):
  """Test GetInfo function for authenticated API calls."""

  urlopen = None

  def setUp(self):  # pylint: disable-msg=C6409
    self.application_auth = AUTH_VAL

    self.urlopen = urllib2.urlopen
    urllib2.urlopen = MockOpener({EMAIL: EMAIL_PASSWORD})

  def testValidRequest(self):  # pylint: disable-msg=C6409
    """Valid request sent to valid URL.

    By default, the mock opener will only accept add requests at the global
    GETINFO or to the keys in GETINFO_ERROR_MAP and GETINFO_UNEXPECTED_MAP.
    (It turns the keys into the error keyword and will not give a valid
    response, so only GETINFO will be valid.)
    """
    api_response = persistent_cal.GetInfo(self.application_auth,
                                          getinfo_endpoint=GETINFO)
    calendars, verbose_freq = GETINFO_SUCCESS
    result = ['Your subscriptions will be updated %s.' % verbose_freq,
              '', 'Your current subscriptions are:'] + calendars
    self.assertEqual(api_response, result)

  def testBadRequest(self):  # pylint: disable-msg=C6409
    """Valid request sent to invalid URL or with bad cookie.

    We send two requests: one to the URL '' which is Invalid and another to
    with the cookie value set to ''.
    """
    bad_getinfo_endpoint = ''
    self.assertRaises(persistent_cal.APIUseException,
                      persistent_cal.GetInfo,
                      self.application_auth,
                      getinfo_endpoint=bad_getinfo_endpoint)

    try:
      persistent_cal.GetInfo(self.application_auth,
                             getinfo_endpoint=bad_getinfo_endpoint)
    except persistent_cal.APIUseException as exc:
      self.assertEqual(len(exc.message), 3)
      self.assertEqual(exc.message[:2], ['Connection error.', ''])

    bad_application_auth = ''
    self.assertRaises(persistent_cal.APIUseException,
                      persistent_cal.GetInfo,
                      bad_application_auth,
                      getinfo_endpoint=GETINFO)

    try:
      persistent_cal.GetInfo(bad_application_auth,
                             getinfo_endpoint=GETINFO)
    except persistent_cal.APIUseException as exc:
      self.assertEqual(len(exc.message), 3)
      self.assertEqual(exc.message[:2], ['Connection error.', ''])

  def testBadAPIResponses(self):  # pylint: disable-msg=C6409
    """Valid API request sent with data that the API rejects.

    The MockOpener will direct requests to special error links which are
    defined in GETINFO_ERROR_MAP. This are passed to GetInfoOpener as a keyword
    argument.  By sending a valid request with the, we can stub out the
    validation done server side by the API.
    """
    actual_error_response_map = persistent_cal.ERROR_RESPONSES['getinfo']

    for getinfo_error_endpoint in GETINFO_ERROR_MAP:
      self.assertRaises(persistent_cal.APIUseException,
                        persistent_cal.GetInfo,
                        self.application_auth,
                        getinfo_endpoint=getinfo_error_endpoint)

      try:
        persistent_cal.GetInfo(self.application_auth,
                               getinfo_endpoint=getinfo_error_endpoint)
      except persistent_cal.APIUseException as exc:
        api_getinfo_error = GETINFO_ERROR_MAP[getinfo_error_endpoint]
        self.assertEqual(exc.message,
                         actual_error_response_map[api_getinfo_error])

  def testUnexpectedAPIResponses(self):  # pylint: disable-msg=C6409
    """Valid API request with unexpected response.

    The MockOpener will direct requests to special error links which are
    defined in GETINFO_UNEXPECTED_MAP. From there, we use the GetInfoOpener to
    return JSON objects which are not expected as responses by the API.
    Explicitly, objects which are either not a list, are a list of length not
    equal to 2 or a list of length 2 with first element not equal to the a list.
    The object and keys are in the global GETINFO_UNEXPECTED_MAP.
    """
    for getinfo_unexpected_endpoint in GETINFO_UNEXPECTED_MAP:
      self.assertRaises(persistent_cal.APIUseException,
                        persistent_cal.GetInfo,
                        self.application_auth,
                        getinfo_endpoint=getinfo_unexpected_endpoint)

      try:
        persistent_cal.GetInfo(self.application_auth,
                               getinfo_endpoint=getinfo_unexpected_endpoint)
      except persistent_cal.APIUseException as exc:
        self.assertEqual(exc.message, 'An unexpected error occurred.')

  def tearDown(self):  # pylint: disable-msg=C6409
    urllib2.urlopen = self.urlopen


class TestMakeRequest(unittest.TestCase):
  """Test MakeRequest function for authenticated API calls."""

  def setUp(self):  # pylint: disable-msg=C6409
    """Configure the test case.

    We replace the API specific functions with a function which returns the
    arguments. In addition, we simulate raw_input in each test with a constant
    function. Finally, the APIAuthManager object is mocked to as well, since
    we aren't relying on authentication to test the API specific functions.
    """
    self.add_subscription = persistent_cal.AddSubscription
    persistent_cal.AddSubscription = lambda *args: ('add',) + args
    self.change_frequency = persistent_cal.ChangeFrequency
    persistent_cal.ChangeFrequency = lambda *args: ('chg',) + args
    self.get_info = persistent_cal.GetInfo
    persistent_cal.GetInfo = lambda *args: ('getinfo',) + args

    self.raw_input = __builtins__.raw_input

    self.api_auth_manager = persistent_cal.APIAuthManager
    persistent_cal.APIAuthManager = MockAPIAuthManager

  def testAddSubscription(self):  # pylint: disable-msg=C6409
    """Test valid arguments passed to AddSubscription."""
    first_arg = 'a'
    __builtins__.raw_input = lambda prompt: first_arg

    add_value = 'link'
    parsed_args = argparse.Namespace(add=add_value)

    request_result = persistent_cal.MakeRequest(parsed_args)
    self.assertEqual(request_result, ('add',
                                      first_arg,
                                      {'calendar-link': add_value}))

  def testChangeFrequency(self):  # pylint: disable-msg=C6409
    """Test valid arguments passed to ChangeFrequency."""
    first_arg = 'b'
    __builtins__.raw_input = lambda prompt: first_arg

    freq_value = 1
    parsed_args = argparse.Namespace(chg=freq_value)

    request_result = persistent_cal.MakeRequest(parsed_args)
    self.assertEqual(request_result, ('chg',
                                      first_arg,
                                      {'frequency': freq_value}))

  def testGetInfo(self):  # pylint: disable-msg=C6409
    """Test valid arguments passed to GetInfo."""
    first_arg = 'c'
    __builtins__.raw_input = lambda prompt: first_arg

    parsed_args = argparse.Namespace(getinfo=True)

    request_result = persistent_cal.MakeRequest(parsed_args)
    self.assertEqual(request_result, ('getinfo', first_arg))

  def testInvalidArguments(self):  # pylint: disable-msg=C6409
    """Test invalid arguments."""
    first_arg = 'd'
    __builtins__.raw_input = lambda prompt: first_arg

    parsed_args = argparse.Namespace()

    self.assertRaises(persistent_cal.APIUseException,
                      persistent_cal.MakeRequest, parsed_args)
    try:
      persistent_cal.MakeRequest(parsed_args)
    except persistent_cal.APIUseException as exc:
      self.assertEqual(exc.message,
                       'Request attempted without valid arguments.')

  def tearDown(self):  # pylint: disable-msg=C6409
    persistent_cal.AddSubscription = self.add_subscription
    persistent_cal.ChangeFrequency = self.change_frequency
    persistent_cal.GetInfo = self.get_info

    __builtins__.raw_input = self.raw_input

    persistent_cal.APIAuthManager = self.api_auth_manager


if __name__ == '__main__':
  unittest.main()

#!/usr/bin/python

# Copyright (C) 2010-2012 Google Inc.
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


"""Google API utility library for persistent-cal."""


__author__ = 'dhermes@google.com (Daniel Hermes)'


# General libraries
import json
import logging
import time

# Third-party libraries
from apiclient.discovery import DISCOVERY_URI
from apiclient.discovery import build_from_document
from apiclient.errors import HttpError
import httplib2
from oauth2client.appengine import CredentialsProperty
from oauth2client.appengine import StorageByKeyName
import uritemplate

# App engine specific libraries
from google.appengine.ext import db
from google.appengine.ext.deferred import defer

# App specific libraries
from custom_exceptions import CredentialsLoadError
from handler_utils import EmailAdmins
import secret_key


CREDENTIALS_KEYNAME = 'calendar.dat'
DISCOVERY_DOC_FILENAME = 'calendar_discovery.json'
DISCOVERY_DOC_PARAMS = {'api': 'calendar', 'apiVersion': 'v3'}
FUTURE_LOCATION = ('http://code.google.com/p/google-api-python-client/source/'
                   'browse/apiclient/contrib/calendar/future.json')


class Credentials(db.Model):  # pylint:disable-msg=R0904
  """A Credentials class for storing calendar credentials."""
  credentials = CredentialsProperty()


def InitCredentials(keyname=CREDENTIALS_KEYNAME):
  """Initializes an OAuth2Credentials object from a file.

  Args:
    keyname: The key name of the credentials object in the data store. Defaults
        to CREDENTIALS_KEYNAME.

  Returns:
    An OAuth2Credentials object.
  """
  storage = StorageByKeyName(Credentials, keyname, 'credentials')
  credentials = storage.get()

  if credentials is None or credentials.invalid == True:
    raise CredentialsLoadError('No credentials retrieved.')

  return credentials


def InitService(credentials=None, keyname=CREDENTIALS_KEYNAME):
  """Initializes a service object to make calendar requests.

  Args:
    credentials: An OAuth2Credentials object used to build a service object.
        In the case the credentials is None, attempt to get credentials using
        the credentials found at key {keyname}.
    keyname: The key name of the credentials object in the data store. Defaults
        to CREDENTIALS_KEYNAME.

  Returns:
    A Resource object intended for making calls to an Apiary API.

  Raises:
    CredentialsLoadError in the case that no credentials are passed in and they
        can't be loaded from the specified file
  """
  if credentials is None:
    credentials = InitCredentials(keyname=keyname)

  http = httplib2.Http()
  http = credentials.authorize(http)

  with open(DISCOVERY_DOC_FILENAME, 'rU') as fh:
    cached_discovery_doc = fh.read()

  return build_from_document(cached_discovery_doc,
                             DISCOVERY_URI,
                             http=http,
                             developerKey=secret_key.DEVELOPER_KEY)


def RetrieveCalendarDiscoveryDoc(credentials=None):
  """Retrieves the discovery doc for the calendar API service.

  Args:
    credentials: An OAuth2Credentials object used to build a service object.
        In the case the credentials is None, attempt to get the default
        credentials.

  Returns:
    A tuple (success, content) where success is a boolean describing if the doc
        was retrieved successfully and content (if success) contains the JSON
        string contents of the discovery doc
  """
  if credentials is None:
    credentials = InitCredentials()

  http = httplib2.Http()
  http = credentials.authorize(http)

  requested_url = uritemplate.expand(DISCOVERY_URI, DISCOVERY_DOC_PARAMS)
  resp, content = http.request(requested_url)

  success = False
  if resp.status < 400:
    try:
      json.loads(content)
      success = True
    except ValueError:
      pass

  return success, content


def CheckCalendarDiscoveryDoc(credentials=None, defer_now=False):
  """Checks a cached discovery doc against the current doc for calendar service.

  If the discovery can't be retrieved or the cached copy disagrees with the
  current version, an email is sent to the administrators.

  Args:
    credentials: An OAuth2Credentials object used to build a service object.
        In the case the credentials is None, attempt to get credentials from
        the default credentials.
    defer_now: Boolean to determine whether or not a task should be spawned, by
        default this is False.
  """
  logging.info('CheckCalendarDiscoveryDoc called with: {!r}'.format(locals()))

  if defer_now:
    defer(CheckCalendarDiscoveryDoc, credentials=credentials,
          defer_now=False, _url='/workers')
    return

  success, current_discovery_doc = RetrieveCalendarDiscoveryDoc(
      credentials=credentials)

  if not success:
    EmailAdmins('Couldn\'t retrieve discovery doc.', defer_now=True)
    return

  with open(DISCOVERY_DOC_FILENAME, 'rU') as fh:
    cached_discovery_doc = fh.read()

  if cached_discovery_doc != current_discovery_doc:
    EmailAdmins('Current discovery doc disagrees with cached version.',
                defer_now=True)


def CheckFutureFeaturesDoc(future_location=FUTURE_LOCATION, defer_now=False):
  """Checks if a future features doc for the calendar service exists.

  If a future features doc is detected, an email is sent to the administrators.

  Args:
    future_location: A string URL where the future features doc would reside if
        it existed. This defaults to the constant FUTURE_LOCATION.
    defer_now: Boolean to determine whether or not a task should be spawned, by
        default this is False.
  """
  logging.info('CheckFutureFeaturesDoc called with: {!r}'.format(locals()))

  if defer_now:
    defer(CheckFutureFeaturesDoc, future_location=future_location,
          defer_now=False, _url='/workers')
    return

  http = httplib2.Http()
  resp, _ = http.request(future_location)

  if resp.status != 404:
    EmailAdmins('Future features JSON responded with {}.'.format(resp.status),
                defer_now=True)


def AttemptAPIAction(http_verb, num_attempts=3, log_msg=None,
                     credentials=None, **kwargs):
  """Attempt an API action a predetermined number of times before failing.

  Args:
    http_verb: The HTTP verb of the intended request. Examle: get, update.
    num_attempts: The number of attempts to make before failing the request.
        Defaults to 3.
    log_msg: The log message to report upon success. Defaults to None.
    credentials: An OAuth2Credentials object used to build a service object.
    kwargs: The keyword arguments to be passed to the API request.

  Returns:
    The result of the API request
  """
  service = InitService(credentials=credentials)

  # pylint:disable-msg=E1101
  api_action = getattr(service.events(), http_verb, None)
  if api_action is None:
    return None

  attempts = int(num_attempts) if int(num_attempts) > 0 else 0
  while attempts:
    try:
      result = api_action(**kwargs).execute()

      if log_msg is None:
        log_msg = '{id_} changed via {verb}'.format(id_=result['id'],
                                                    verb=http_verb)
      logging.info(log_msg)

      return result
    except (httplib2.HttpLib2Error, HttpError) as exc:
      logging.info(exc)
      attempts -= 1
      time.sleep(3)

  return None

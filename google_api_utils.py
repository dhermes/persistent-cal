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


__author__ = 'daniel.j.hermes@gmail.com (Daniel Hermes)'


# General libraries
import datetime
import json
import logging
import os
import time

# Third-party libraries
from apiclient.discovery import DISCOVERY_URI
from apiclient.discovery import _add_query_parameter
from apiclient.discovery import build_from_document
from apiclient.errors import HttpError
from apiclient.errors import InvalidJsonError
import httplib2
from oauth2client.appengine import CredentialsModel
from oauth2client.appengine import StorageByKeyName
import uritemplate

# App engine specific libraries
from google.appengine.ext import ndb

# App specific libraries
from custom_exceptions import CredentialsLoadError


CALENDAR_API_NAME = 'calendar'
CALENDAR_API_VERSION = 'v3'
CREDENTIALS_KEYNAME = 'calendar.dat'
DISCOVERY_DOC_MAX_AGE = datetime.timedelta(days=7)
SECRET_KEY = {}
SECRET_KEY_DB_KEY = 'secret_key'


class SecretKey(ndb.Model):
  """Model for representing a project secret keys."""
  client_id = ndb.StringProperty(required=True)
  client_secret = ndb.StringProperty(required=True)
  developer_key = ndb.StringProperty(required=True)


class DiscoveryDocument(ndb.Model):
  """Model for representing a discovery document."""
  document = ndb.StringProperty(required=True, indexed=False)
  updated = ndb.DateTimeProperty(auto_now=True, indexed=False)

  @property
  def expired(self):
    now = datetime.datetime.utcnow()
    return now - self.updated > DISCOVERY_DOC_MAX_AGE

  @classmethod
  def build(cls, serviceName, version, credentials, **kwargs):
    discoveryServiceUrl = kwargs.pop('discoveryServiceUrl', DISCOVERY_URI)
    key = ndb.Key(cls, serviceName, cls, version, cls, discoveryServiceUrl)
    discovery_doc = key.get()

    if discovery_doc is None or discovery_doc.expired:
      # If None, RetrieveDiscoveryDoc() will use Defaults
      document = RetrieveDiscoveryDoc(
          serviceName, version, credentials=credentials,
          discoveryServiceUrl=discoveryServiceUrl)
      discovery_doc = cls(key=key, document=document)
      discovery_doc.put()

    http = kwargs.get('http', None)
    if http is None:
      http = httplib2.Http()
      kwargs['http'] = credentials.authorize(http)
    return build_from_document(
        discovery_doc.document, discoveryServiceUrl, **kwargs)


def InitCredentials(keyname=CREDENTIALS_KEYNAME):
  """Initializes an OAuth2Credentials object from a file.

  Args:
    keyname: The key name of the credentials object in the data store. Defaults
        to CREDENTIALS_KEYNAME.

  Returns:
    An OAuth2Credentials object.
  """
  storage = StorageByKeyName(CredentialsModel, keyname, 'credentials')
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

  if 'DEVELOPER_KEY' not in SECRET_KEY:
    secret_key = ndb.Key(SecretKey, SECRET_KEY_DB_KEY).get()
    SECRET_KEY['DEVELOPER_KEY'] = secret_key.developer_key

  return DiscoveryDocument.build(CALENDAR_API_NAME,
                                 CALENDAR_API_VERSION,
                                 credentials,
                                 developerKey=SECRET_KEY['DEVELOPER_KEY'])


def RetrieveDiscoveryDoc(serviceName, version, credentials=None,
                         discoveryServiceUrl=DISCOVERY_URI):
  params = {'api': serviceName, 'apiVersion': version}
  requested_url = uritemplate.expand(discoveryServiceUrl, params)

  # REMOTE_ADDR is defined by the CGI spec [RFC3875] as the environment
  # variable that contains the network address of the client sending the
  # request. If it exists then add that to the request for the discovery
  # document to avoid exceeding the quota on discovery requests.
  if 'REMOTE_ADDR' in os.environ:
    requested_url = _add_query_parameter(requested_url, 'userIp',
                                         os.environ['REMOTE_ADDR'])

  if credentials is None:
    credentials = InitCredentials()
  http = httplib2.Http()
  http = credentials.authorize(http)

  resp, content = http.request(requested_url)

  if resp.status >= 400:
    raise HttpError(resp, content, uri=requested_url)

  try:
    service = json.loads(content)
  except ValueError:
    raise InvalidJsonError(
        'Bad JSON: {} from {}'.format(content, requested_url))

  return content


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

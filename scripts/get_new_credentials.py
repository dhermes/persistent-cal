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


"""Gets new credentials using the keys in secret_key.py.

From Sample in project source wiki:
http://code.google.com/p/google-api-python-client/wiki/OAuth2#Command-Line
"""


# General libraries
import os

# Third-party libraries
from apiclient.discovery import build
import httplib2
from oauth2client.appengine import StorageByKeyName
from oauth2client.client import OAuth2WebServerFlow
from oauth2client.tools import run

# App specific libraries
from models import Credentials
import secret_key


os.environ['HTTP_HOST'] = 'persistent-cal.appspot.com'


def main():
  storage = StorageByKeyName(Credentials, 'calendar.dat', 'credentials')
  credentials = storage.get()

  if credentials is None or credentials.invalid == True:
    flow = OAuth2WebServerFlow(
        client_id=secret_key.CLIENT_ID,
        client_secret=secret_key.CLIENT_SECRET,
        scope='https://www.googleapis.com/auth/calendar',
        user_agent='persistent-cal-auth')

    credentials = run(flow, storage)


if __name__ == '__main__':
  main()

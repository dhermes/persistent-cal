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


"""DB migration for Calendar v2 to v3 upgrade on 2012-03-03.

Intended to be run through the remote API:

remote_api_shell.py -s persistent-cal.appspot.com

s~persistent-cal> import sys
s~persistent-cal> sys.path.append('/path/to/persistent-cal')
s~persistent-cal> from db_migration_2012_03_03 import UpdateEvents
s~persistent-cal> UpdateEvents()

Note:
  We are transforming the gcal_edit value from the full link to the link
  id at the end of url:

    https://www.google.com/calendar/feeds/{CAL_ID}/private/full/{EVENT_ID}
"""


__author__ = 'dhermes@google.com (Daniel Hermes)'


# General imports
import httplib2

# Third Party Imports
from apiclient.discovery import build
from apiclient.errors import HttpError
from oauth2client.file import Storage

# App specific libraries
from models import Event
from secret_key import DEVELOPER_KEY


def UpdateEvents():
  # OAuth2 credentials already stored
  storage = Storage('calendar.dat')
  credentials = storage.get()

  http = httplib2.Http()
  http = credentials.authorize(http)
  service = build(serviceName='calendar', version='v3', http=http,
      developerKey=DEVELOPER_KEY)

  cal_id = 'vhoam1gb7uqqoqevu91liidi80@group.calendar.google.com'
  events = Event.all()
  for event in events:
    event.gcal_edit = event.gcal_edit.split('/')[-1]

    event_id = event.gcal_edit
    try:
      service.events().get(calendarId=cal_id, eventId=event_id).execute()
      event.put()
    except HttpError as e:
      print('%s failed with: %s %s' % (event_id, type(e), e))


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


"""DB migration for Model Update on 2012-04-25.

Intended to be run through the remote API:

remote_api_shell.py -s persistent-cal.appspot.com

s~persistent-cal> import sys
s~persistent-cal> sys.path.append('/path/to/persistent-cal')
s~persistent-cal> from db_migration_2012_04_25 import UpdateEvents
s~persistent-cal> UpdateEvents()

Note:
  We may move gcal_edit into event_data as the 'id' key, but not here.
"""


__author__ = 'dhermes@google.com (Daniel Hermes)'


# General libraries
import json

# App engine specific libraries
from google.appengine.ext import db

# App specific libraries
from library import JsonAscii
from models import Event


def TransformEventData(event_data):
  """Takes Event object to new specification."""
  new_event_data = {}

  new_event_data['summary'] = event_data['summary']
  new_event_data['description'] = event_data['description']

  # Where
  new_event_data['location'] = event_data['location']

  # When
  start = event_data['when:from']
  if start.endswith('Z'):
    new_event_data['start'] = {'dateTime': start}
  else:
    new_event_data['start'] = {'date': start}

  end = event_data['when:to']
  if end.endswith('Z'):
    new_event_data['end'] = {'dateTime': end}
  else:
    new_event_data['end'] = {'date': end}

  return new_event_data


def UpdateEvents():
  events = Event.all()
  for event in events:
    event_data = json.loads(event.event_data)
    new_event_data = TransformEventData(event_data)

    event.event_data_old = db.Text(JsonAscii(event_data))
    event.event_data = db.Text(JsonAscii(new_event_data))

    event.put()
